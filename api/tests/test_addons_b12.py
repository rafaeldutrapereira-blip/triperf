"""
B12 — Addons vendibles (compra por módulo) con Stripe. Precios de prueba.

- Catálogo: Labs no está incluido en Elite; el resto de addons sí.
- Flag LABX_ADDONS apagado: no hay checkout ni cambios de acceso.
- Checkout de addon (Stripe simulado): kind=addon, sin tocar plan_nivel.
- Webhook: alta activa el entitlement; cancelación mantiene el acceso hasta el
  fin del período pagado (decisión de Rafael).
- Labs sale de Elite con el flag; la gracia de 90 días la da el backfill.
- Cuota de IA: 50 consultas/día con el flag.
"""
import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api import module_catalog as mc
from api.auth import hash_password
from api.models import AiUsageDaily, Entitlement, User
from api.plan_features import entitlement_features, has_feature
from api.routes import stripe_routes
from api.routes.ai_routes import enforce_ai_quota
from api.services.labs_grace import apply_grace, plan_grace
from .conftest import auth_headers, login


# ── Stripe simulado ──
class FakeStripe:
    class checkout:
        class Session:
            @staticmethod
            def create(**kw):
                FakeStripe.last_checkout = kw
                return SimpleNamespace(id="cs_test_1", url="https://stripe.test/checkout")

    class Customer:
        @staticmethod
        def create(**kw):
            return SimpleNamespace(id="cus_test_1")

        @staticmethod
        def list(**kw):
            return SimpleNamespace(data=[])

    class Webhook:
        @staticmethod
        def construct_event(payload, sig, secret):
            return json.loads(payload)

    last_checkout = None


@pytest.fixture
def fake_stripe(monkeypatch):
    monkeypatch.setattr(stripe_routes, "_stripe", lambda: FakeStripe)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("STRIPE_PRICE_ADDON_INDOOR", "price_test_indoor")
    monkeypatch.setenv("STRIPE_PRICE_ADDON_LABS", "price_test_labs")
    return FakeStripe


@pytest.fixture
def addons_on(monkeypatch):
    monkeypatch.setenv(mc.ADDONS_FLAG_ENV, "1")


def _set_plan(db, user, plan):
    user.plan_nivel = plan
    db.commit()


def _token(client):
    return login(client, "athlete@test.com", "AthlPass123")


# ── catálogo ──
def test_elite_incluye_todo_menos_labs():
    assert "labs" not in mc.ELITE_INCLUDES_ADDONS
    assert {"asistente_ia", "indoor", "ajustes_adaptativos", "retrospectiva"} <= mc.ELITE_INCLUDES_ADDONS


def test_precio_por_addon_env():
    assert mc.addon_price_env("labs") == "STRIPE_PRICE_ADDON_LABS"


# ── flag apagado ──
def test_flag_apagado_no_vende_ni_cambia_acceso(client, db, athlete_user, fake_stripe, monkeypatch):
    monkeypatch.delenv(mc.ADDONS_FLAG_ENV, raising=False)
    h = auth_headers(_token(client))
    assert client.get("/api/stripe/addons", headers=h).json()["enabled"] is False
    r = client.post("/api/stripe/addons/checkout", json={"addon_id": "indoor"}, headers=h)
    assert r.status_code == 503


# ── checkout de addon ──
def test_checkout_addon_para_agegroup(client, db, athlete_user, fake_stripe, addons_on):
    _set_plan(db, athlete_user, "agegroup")
    h = auth_headers(_token(client))
    r = client.post("/api/stripe/addons/checkout", json={"addon_id": "indoor"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["checkout_url"].startswith("https://stripe.test")
    kw = FakeStripe.last_checkout
    assert kw["line_items"] == [{"price": "price_test_indoor", "quantity": 1}]
    assert kw["subscription_data"]["metadata"]["kind"] == "addon"
    assert kw["subscription_data"]["metadata"]["addon_id"] == "indoor"


def test_elite_no_compra_lo_que_ya_incluye(client, db, athlete_user, fake_stripe, addons_on):
    _set_plan(db, athlete_user, "elite")
    h = auth_headers(_token(client))
    r = client.post("/api/stripe/addons/checkout", json={"addon_id": "indoor"}, headers=h)
    assert r.status_code == 400


def test_elite_si_compra_labs(client, db, athlete_user, fake_stripe, addons_on):
    _set_plan(db, athlete_user, "elite")
    h = auth_headers(_token(client))
    r = client.post("/api/stripe/addons/checkout", json={"addon_id": "labs"}, headers=h)
    assert r.status_code == 200, r.text


def test_addon_desconocido_400(client, db, athlete_user, fake_stripe, addons_on):
    h = auth_headers(_token(client))
    r = client.post("/api/stripe/addons/checkout", json={"addon_id": "nope"}, headers=h)
    assert r.status_code == 400


def test_precio_no_configurado_400(client, db, athlete_user, fake_stripe, addons_on, monkeypatch):
    monkeypatch.delenv("STRIPE_PRICE_ADDON_INDOOR", raising=False)
    _set_plan(db, athlete_user, "agegroup")
    h = auth_headers(_token(client))
    r = client.post("/api/stripe/addons/checkout", json={"addon_id": "indoor"}, headers=h)
    assert r.status_code == 400


# ── webhook ──
def _event(evt, status, sid="sub_1", aid="indoor", uid=None, period_end=None, uid_default=None):
    obj = {"id": sid, "status": status,
           "metadata": {"user_id": uid, "kind": "addon", "addon_id": aid}}
    if period_end is not None:
        obj["current_period_end"] = period_end
    return {"type": evt, "data": {"object": obj}}


def _post_webhook(client, event):
    return client.post("/api/stripe/webhook", content=json.dumps(event),
                       headers={"stripe-signature": "t=1,v1=x", "content-type": "application/json"})


def test_webhook_alta_addon_activa_entitlement_sin_tocar_plan(client, db, athlete_user, fake_stripe, addons_on):
    _set_plan(db, athlete_user, "agegroup")
    r = _post_webhook(client, _event("customer.subscription.created", "active", uid=athlete_user.id))
    assert r.status_code == 200, r.text
    ent = db.query(Entitlement).filter_by(user_id=athlete_user.id, addon_id="indoor").one()
    assert ent.status == "active" and ent.expires_at is None and ent.source == "purchase"
    db.refresh(athlete_user)
    assert athlete_user.plan_nivel == "agegroup"  # el addon no cambia el plan


def test_webhook_es_idempotente(client, db, athlete_user, fake_stripe, addons_on):
    _set_plan(db, athlete_user, "agegroup")
    ev = _event("customer.subscription.created", "active", uid=athlete_user.id)
    _post_webhook(client, ev)
    _post_webhook(client, ev)
    assert db.query(Entitlement).filter_by(user_id=athlete_user.id).count() == 1


def test_cancelar_mantiene_acceso_hasta_fin_de_periodo(client, db, athlete_user, fake_stripe, addons_on):
    _set_plan(db, athlete_user, "agegroup")
    _post_webhook(client, _event("customer.subscription.created", "active", uid=athlete_user.id))
    fin = int(time.time()) + 3 * 86400
    _post_webhook(client, _event("customer.subscription.deleted", "canceled", uid=athlete_user.id, period_end=fin))
    ent = db.query(Entitlement).filter_by(user_id=athlete_user.id, addon_id="indoor").one()
    assert ent.status == "canceled"
    assert ent.expires_at == datetime.fromtimestamp(fin, tz=timezone.utc).replace(tzinfo=None)
    db.expire_all()
    u = db.get(User, athlete_user.id)
    assert has_feature(u, "indoor_workout") is True  # aún dentro del período pagado


def test_tras_vencer_el_periodo_se_pierde_el_acceso(client, db, athlete_user, fake_stripe, addons_on):
    _set_plan(db, athlete_user, "agegroup")
    _post_webhook(client, _event("customer.subscription.created", "active", uid=athlete_user.id))
    pasado = int(time.time()) - 60
    _post_webhook(client, _event("customer.subscription.deleted", "canceled", uid=athlete_user.id, period_end=pasado))
    db.expire_all()
    u = db.get(User, athlete_user.id)
    assert has_feature(u, "indoor_workout") is False


def test_webhook_de_plan_no_se_confunde_con_addon(client, db, athlete_user, fake_stripe, addons_on):
    _set_plan(db, athlete_user, "basico")
    ev = {"type": "customer.subscription.created",
          "data": {"object": {"id": "sub_plan", "status": "active",
                              "metadata": {"user_id": athlete_user.id, "plan": "agegroup"}}}}
    _post_webhook(client, ev)
    db.refresh(athlete_user)
    assert athlete_user.plan_nivel == "agegroup"
    assert db.query(Entitlement).count() == 0


# ── acceso por entitlement ──
def test_entitlement_da_la_feature_del_addon(db, athlete_user, addons_on):
    _set_plan(db, athlete_user, "basico")
    db.add(Entitlement(user_id=athlete_user.id, addon_id="asistente_ia", source="purchase", status="active"))
    db.commit()
    assert "ai_coach" in entitlement_features(athlete_user)
    assert has_feature(athlete_user, "ai_coach") is True


# ── Labs: sale de Elite con el flag; gracia por backfill ──
def test_labs_sale_de_elite_con_flag(db, athlete_user, addons_on):
    _set_plan(db, athlete_user, "elite")
    assert has_feature(athlete_user, "blood_labs") is False


def test_labs_en_elite_sin_flag_sigue_igual(db, athlete_user, monkeypatch):
    monkeypatch.delenv(mc.ADDONS_FLAG_ENV, raising=False)
    _set_plan(db, athlete_user, "elite")
    assert has_feature(athlete_user, "blood_labs") is True


def test_gracia_de_labs_para_elite_actuales(db, athlete_user):
    _set_plan(db, athlete_user, "elite")
    assert apply_grace(db) == 1
    ent = db.query(Entitlement).filter_by(user_id=athlete_user.id, addon_id="labs").one()
    assert ent.source == "legacy" and ent.expires_at is not None
    assert ent.expires_at - ent.created_at == timedelta(days=mc.LABS_GRACE_DAYS)
    # idempotente
    assert apply_grace(db) == 0
    assert plan_grace(db) == []


def test_gracia_no_aplica_a_agegroup(db, athlete_user):
    _set_plan(db, athlete_user, "agegroup")
    assert apply_grace(db) == 0


# ── cuota de IA ──
def test_cuota_diaria_de_50(db, athlete_user, addons_on):
    _set_plan(db, athlete_user, "elite")
    for _ in range(mc.AI_DAILY_QUOTA):
        enforce_ai_quota(db, athlete_user)
    with pytest.raises(HTTPException) as exc:
        enforce_ai_quota(db, athlete_user)
    assert exc.value.status_code == 429
    assert db.query(AiUsageDaily).filter_by(user_id=athlete_user.id).one().count == mc.AI_DAILY_QUOTA


def test_cuota_sin_flag_no_limita(db, athlete_user, monkeypatch):
    monkeypatch.delenv(mc.ADDONS_FLAG_ENV, raising=False)
    _set_plan(db, athlete_user, "elite")
    for _ in range(mc.AI_DAILY_QUOTA + 5):
        enforce_ai_quota(db, athlete_user)
    assert db.query(AiUsageDaily).count() == 0


def test_cuota_no_aplica_a_coach(db, coach_user, addons_on):
    for _ in range(mc.AI_DAILY_QUOTA + 3):
        enforce_ai_quota(db, coach_user)
    assert db.query(AiUsageDaily).count() == 0
