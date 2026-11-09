"""FLOW-INTEGRA (BUILD 366) — cliente Flow MOCKEADO: cero llamadas reales, cero credenciales reales."""
from datetime import timedelta

import pytest

from api import flow_billing as fb
from api import flow_client
from api.flow_client import FlowError, sign_params, verify_signature
from api.models import FlowPaymentEvent, FlowSubscription, User
from api.plan_features import has_feature
from .conftest import auth_headers, login

SECRET = "test-secret-no-real"


class FakeFlow:
    """Sustituye a FlowClient. Registra llamadas y devuelve respuestas guionadas."""

    def __init__(self):
        self.calls = []
        self.register_ok = True
        self.pay = {"flowOrder": 1001, "status": 2, "payer": "athlete@test.com"}
        self.sub = {"subscriptionId": "sus_1", "status": 1,
                    "period_start": "2026-11-09 00:00:00", "period_end": "2026-12-09 00:00:00",
                    "cancel_at_period_end": 0}
        self.fail_plan_get = True

    def _rec(self, name, *a):
        self.calls.append((name,) + a)

    def create_customer(self, name, email, external_id):
        self._rec("create_customer", email)
        return {"customerId": "cus_1"}

    def get_plan(self, plan_id):
        self._rec("get_plan", plan_id)
        if self.fail_plan_get:
            raise FlowError("no existe", 400)
        return {}

    def create_plan(self, *a, **k):
        self._rec("create_plan", a[0])
        return {}

    def register_card(self, customer_id, url_return):
        self._rec("register_card", url_return)
        return {"url": "https://sandbox.flow.cl/app/customer/disclaimer.php", "token": "REGTOK"}

    def register_status(self, token):
        self._rec("register_status", token)
        return {"status": "1" if self.register_ok else "0"}

    def create_subscription(self, plan_id, customer_id):
        self._rec("create_subscription", plan_id)
        return {"subscriptionId": "sus_1"}

    def get_subscription(self, sid):
        self._rec("get_subscription", sid)
        return dict(self.sub)

    def payment_status(self, token):
        self._rec("payment_status", token)
        if token == "BAD":
            raise FlowError("token inválido", 400)
        return dict(self.pay)

    def cancel_subscription(self, sid, at_period_end=True):
        self._rec("cancel_subscription", sid, at_period_end)
        return {}


@pytest.fixture
def flow(monkeypatch):
    monkeypatch.setenv("FLOW_ENABLED", "1")
    monkeypatch.setenv("FLOW_SECRET_KEY", SECRET)
    fake = FakeFlow()
    monkeypatch.setattr("api.routes.flow_routes.get_client", lambda: fake)
    return fake


@pytest.fixture
def ath(client, athlete_user):
    return auth_headers(login(client, "athlete@test.com", "AthlPass123"))


def _checkout_and_return(client, ath):
    r = client.post("/api/flow/checkout", json={"product": "esencial"}, headers=ath)
    assert r.status_code == 200, r.text
    return client.post("/api/flow/register-return", data={"token": "REGTOK"}, follow_redirects=False)


# ── Firma ──
def test_firma_orden_alfabetico_y_hmac():
    p = {"currency": "CLP", "apiKey": "KEY", "amount": 5000}
    import hashlib, hmac
    esperado = hmac.new(b"sec", b"amount5000apiKeyKEYcurrencyCLP", hashlib.sha256).hexdigest()
    assert sign_params(p, "sec") == esperado


def test_firma_ignora_s_y_valida_o_rechaza():
    p = {"token": "abc"}
    p["s"] = sign_params(p, SECRET)
    assert verify_signature(p, SECRET)
    assert not verify_signature({**p, "token": "otro"}, SECRET)
    assert not verify_signature({"token": "abc", "s": "x"}, SECRET)
    assert not verify_signature({"token": "abc"}, SECRET)


def test_cliente_exige_credenciales_del_entorno(monkeypatch):
    monkeypatch.delenv("FLOW_API_KEY", raising=False)
    monkeypatch.delenv("FLOW_SECRET_KEY", raising=False)
    with pytest.raises(FlowError):
        flow_client.FlowClient()


def test_cliente_firma_y_apunta_a_sandbox_por_defecto(monkeypatch):
    monkeypatch.delenv("FLOW_API_URL", raising=False)
    c = flow_client.FlowClient(api_key="K", secret_key="S")
    assert c.base_url == "https://sandbox.flow.cl/api"
    p = c._signed({"token": "t"})
    assert p["apiKey"] == "K" and verify_signature(p, "S")


# ── Flag ──
def test_sin_flag_no_hay_rutas(client, ath, monkeypatch):
    monkeypatch.delenv("FLOW_ENABLED", raising=False)
    assert client.get("/api/flow/config").status_code == 404
    assert client.post("/api/flow/checkout", json={"product": "esencial"}, headers=ath).status_code == 404
    assert client.post("/api/flow/webhook", data={"token": "x"}).status_code == 404


def test_catalogo_completo_definido_no_vendible(client, flow):
    prods = {p["id"]: p for p in client.get("/api/flow/config").json()["products"]}
    assert prods["esencial"]["amount"] == 9900 and prods["esencial"]["available"]
    assert prods["completo"]["amount"] == 15900 and not prods["completo"]["available"]


def test_completo_no_se_puede_comprar(client, flow, ath):
    r = client.post("/api/flow/checkout", json={"product": "completo"}, headers=ath)
    assert r.status_code == 400
    assert not any(c[0] == "register_card" for c in flow.calls)


# ── Flujo ──
def test_checkout_crea_pendiente_sin_activar(client, flow, ath, db):
    r = client.post("/api/flow/checkout", json={"product": "esencial"}, headers=ath)
    assert r.json()["checkout_url"].endswith("?token=REGTOK")
    row = db.query(FlowSubscription).one()
    assert row.status == "pendiente"
    assert db.query(User).filter_by(email="athlete@test.com").one().plan_nivel == "basico"


def test_checkout_idempotente_reusa_pendiente(client, flow, ath, db):
    client.post("/api/flow/checkout", json={"product": "esencial"}, headers=ath)
    client.post("/api/flow/checkout", json={"product": "esencial"}, headers=ath)
    assert db.query(FlowSubscription).count() == 1
    assert [c[0] for c in flow.calls].count("create_customer") == 1


def test_retorno_del_navegador_no_activa_el_plan(client, flow, ath, db):
    r = _checkout_and_return(client, ath)
    assert r.status_code == 303 and "flow=pending" in r.headers["location"]
    db.expire_all()
    assert db.query(FlowSubscription).one().status == "pendiente"
    assert db.query(User).filter_by(email="athlete@test.com").one().plan_nivel == "basico"


def test_retorno_doble_no_crea_dos_suscripciones(client, flow, ath, db):
    _checkout_and_return(client, ath)
    client.post("/api/flow/register-return", data={"token": "REGTOK"}, follow_redirects=False)
    assert [c[0] for c in flow.calls].count("create_subscription") == 1


def test_tarjeta_no_registrada_es_fracaso_honesto(client, flow, ath, db):
    flow.register_ok = False
    r = _checkout_and_return(client, ath)
    assert "flow=fail" in r.headers["location"]
    db.expire_all()
    assert db.query(FlowSubscription).one().status == "fallida"


def test_webhook_pago_confirmado_activa_plan(client, flow, ath, db):
    _checkout_and_return(client, ath)
    r = client.post("/api/flow/webhook", data={"token": "T1"})
    assert r.status_code == 200
    db.expire_all()
    u = db.query(User).filter_by(email="athlete@test.com").one()
    assert u.plan_nivel == "agegroup"
    assert db.query(FlowSubscription).one().status == "activa"
    assert has_feature(u, "nutrition") is True


def test_webhook_duplicado_no_duplica_ni_reactiva(client, flow, ath, db):
    _checkout_and_return(client, ath)
    client.post("/api/flow/webhook", data={"token": "T1"})
    sub_calls = [c for c in flow.calls if c[0] == "get_subscription"]
    row = db.query(FlowSubscription).one()
    row.status = "cancelada"           # lo cancelaron entre medio
    db.commit()
    r = client.post("/api/flow/webhook", data={"token": "T1"})
    assert r.json().get("duplicate") is True
    db.expire_all()
    assert db.query(FlowSubscription).one().status == "cancelada"      # no se reactivó
    assert db.query(FlowPaymentEvent).count() == 1
    assert len([c for c in flow.calls if c[0] == "get_subscription"]) == len(sub_calls)


def test_webhook_pago_rechazado_no_activa(client, flow, ath, db):
    _checkout_and_return(client, ath)
    flow.pay["status"] = 3
    assert client.post("/api/flow/webhook", data={"token": "T2"}).status_code == 200
    db.expire_all()
    assert db.query(FlowSubscription).one().status == "fallida"
    assert db.query(User).filter_by(email="athlete@test.com").one().plan_nivel == "basico"


def test_webhook_token_invalido_400_sin_efectos(client, flow, ath, db):
    _checkout_and_return(client, ath)
    assert client.post("/api/flow/webhook", data={"token": "BAD"}).status_code == 400
    assert client.post("/api/flow/webhook", data={}).status_code == 400
    assert db.query(FlowPaymentEvent).count() == 0


def test_webhook_firma_invalida_rechazada_y_valida_aceptada(client, flow, ath, db):
    _checkout_and_return(client, ath)
    assert client.post("/api/flow/webhook", data={"token": "T1", "s": "mala"}).status_code == 400
    s = sign_params({"token": "T1"}, SECRET)
    assert client.post("/api/flow/webhook", data={"token": "T1", "s": s}).status_code == 200


def test_renovacion_nuevo_flow_order_extiende_periodo(client, flow, ath, db):
    _checkout_and_return(client, ath)
    client.post("/api/flow/webhook", data={"token": "T1"})
    flow.pay["flowOrder"] = 1002
    flow.sub["period_end"] = "2027-01-09 00:00:00"
    client.post("/api/flow/webhook", data={"token": "T3"})
    db.expire_all()
    assert db.query(FlowSubscription).one().period_end.year == 2027
    assert db.query(FlowPaymentEvent).count() == 2


# ── Cancelación y gating ──
def test_cancelar_agenda_fin_y_mantiene_acceso(client, flow, ath, db):
    _checkout_and_return(client, ath)
    client.post("/api/flow/webhook", data={"token": "T1"})
    r = client.post("/api/flow/cancel", headers=ath)
    assert r.status_code == 200 and r.json()["subscription"]["cancel_at_period_end"] is True
    assert ("cancel_subscription", "sus_1", True) in flow.calls
    db.expire_all()
    u = db.query(User).filter_by(email="athlete@test.com").one()
    assert u.plan_nivel == "agegroup" and has_feature(u, "nutrition")
    assert client.post("/api/flow/cancel", headers=ath).status_code == 200   # idempotente


def test_al_vencer_el_periodo_vuelve_a_gratis(client, flow, ath, db):
    _checkout_and_return(client, ath)
    client.post("/api/flow/webhook", data={"token": "T1"})
    client.post("/api/flow/cancel", headers=ath)
    row = db.query(FlowSubscription).one()
    row.period_end = fb.now() - timedelta(hours=1)
    db.commit()
    u = db.query(User).filter_by(email="athlete@test.com").one()
    assert has_feature(u, "nutrition") is False
    db.expire_all()
    assert db.query(FlowSubscription).one().status == "cancelada"
    assert db.query(User).filter_by(email="athlete@test.com").one().plan_nivel == "basico"


def test_sin_renovacion_pasada_la_gracia_baja_el_plan(client, flow, ath, db):
    _checkout_and_return(client, ath)
    client.post("/api/flow/webhook", data={"token": "T1"})
    row = db.query(FlowSubscription).one()
    row.period_end = fb.now() - timedelta(days=fb.GRACE_DAYS + 1)
    db.commit()
    u = db.query(User).filter_by(email="athlete@test.com").one()
    assert has_feature(u, "nutrition") is False
    db.expire_all()
    assert db.query(FlowSubscription).one().status == "fallida"


def test_sin_suscripcion_queda_en_nivel_gratuito(db, athlete_user):
    assert has_feature(athlete_user, "nutrition") is False
    assert has_feature(athlete_user, "dashboard") is True


def test_no_se_vende_a_quien_ya_tiene_plan_de_pago(client, flow, db, athlete_user):
    athlete_user.plan_nivel = "elite"
    db.commit()
    h = auth_headers(login(client, "athlete@test.com", "AthlPass123"))
    assert client.post("/api/flow/checkout", json={"product": "esencial"}, headers=h).status_code == 409


def test_checkout_requiere_login(client, flow):
    assert client.post("/api/flow/checkout", json={"product": "esencial"}).status_code == 401


def test_error_de_flow_en_checkout_no_deja_estado_activo(client, flow, ath, db, monkeypatch):
    def boom(*a, **k):
        raise FlowError("caído", 500)
    monkeypatch.setattr(flow, "register_card", boom)
    assert client.post("/api/flow/checkout", json={"product": "esencial"}, headers=ath).status_code == 502
    assert db.query(FlowSubscription).count() == 0


def test_repo_sin_credenciales_literales():
    import pathlib
    src = (pathlib.Path(flow_client.__file__)).read_text(encoding="utf8")
    assert "getenv(\"FLOW_API_KEY\"" in src and "getenv(\"FLOW_SECRET_KEY\"" in src
