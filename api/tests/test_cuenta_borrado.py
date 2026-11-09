"""CUENTA-BORRADO (BUILD 367): eliminacion de cuenta en la app, cascada verificada tabla por
tabla contra el mapa POLICY, tokens revocados y pagina publica."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

from api import account_deletion as ad
from api.auth import hash_password
from api.database import Base
from api.models import (
    AccountDeletionRequest, AuditLog, CoachAthlete, CommunityNotification, FlowPaymentEvent,
    FlowSubscription, GarminActivity, GarminOAuthToken, InjuryRiskSnapshot, Message,
    PlanSession, ProviderConnection, User, WellnessLog,
)
from .conftest import auth_headers, login

ROOT = Path(__file__).resolve().parents[2]


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ask(client, token, password="AthlPass123"):
    return client.request("DELETE", "/api/auth/account", json={"password": password},
                          headers=auth_headers(token))


def _refs(db, uid):
    """Filas que aun apuntan a uid, por 'tabla.columna' (cualquier FK a users + tablas sin FK)."""
    out = {}
    for t, c in ad.fk_user_columns():
        n = db.execute(select(func.count()).select_from(Base.metadata.tables[t])
                       .where(Base.metadata.tables[t].c[c] == uid)).scalar()
        if n:
            out[f"{t}.{c}"] = n
    return out


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(ad, "_strava_deauthorize", lambda tok: None)


@pytest.fixture
def world(db, athlete_user, coach_user):
    """Un atleta con datos en varias tablas, ligado a un coach, con integraciones y un pago."""
    now = _now()
    uid = athlete_user.id
    athlete_user.strava_access_token = "tok-strava"
    athlete_user.strava_athlete_id = "99"
    athlete_user.intervals_access_token = "tok-int"
    athlete_user.weight_kg = 70
    athlete_user.stripe_customer_id = "cus_1"
    db.add_all([
        WellnessLog(user_id=uid, date_iso="2026-11-01"),
        InjuryRiskSnapshot(user_id=uid, date_iso="2026-11-01"),
        GarminOAuthToken(user_id=uid, access_token="x", refresh_token="y",
                         expires_at=now + timedelta(days=1)),
        ProviderConnection(user_id=uid, provider="polar", access_token="p"),
        CoachAthlete(coach_id=coach_user.id, athlete_id=uid, activo=True, status="active"),
        Message(from_user_id=uid, to_user_id=coach_user.id, body="hola"),
        Message(from_user_id=coach_user.id, to_user_id=uid, body="chao"),
        # notificacion de OTRO usuario generada por el atleta: sobrevive con actor NULL
        CommunityNotification(user_id=coach_user.id, actor_id=uid, notif_type="follow", created_at=now),
        FlowSubscription(user_id=uid, product="esencial", plan_nivel="agegroup", status="activa",
                         flow_customer_id="cus_flow", register_token="rt", flow_subscription_id="sub_1"),
        FlowPaymentEvent(flow_order="ord-1", pay_status=2, user_id=uid),
        AuditLog(user_id=uid, action="auth.login.success", ip="1.2.3.4", user_agent="UA", detail="{\"x\":1}"),
    ])
    db.commit()
    return {"uid": uid, "coach": coach_user.id}


def test_policy_cubre_todas_las_fk_a_users():
    assert ad.unmapped_columns() == [], "FK a users sin destino en el mapa de cascada"
    assert set(ad.POLICY) <= {f"{t}.{c}" for t, c in ad.fk_user_columns()}, "mapa con columnas inexistentes"


def test_login_imposible_tras_pedir_el_borrado(client, db, world):
    token = login(client, "athlete@test.com", "AthlPass123")
    r = _ask(client, token)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["max_days"] == 30 and body["grace_days"] <= 30
    # el token que ya tenia deja de servir (sesiones invalidadas) y no puede volver a entrar
    assert client.get("/api/auth/me", headers=auth_headers(token)).status_code in (401, 403)
    r2 = client.post("/api/auth/login", json={"email": "athlete@test.com", "password": "AthlPass123"})
    assert r2.status_code == 403
    assert "desactivada" in json.dumps(r2.json()).lower() or "account_inactive" in json.dumps(r2.json())


def test_requiere_contrasena_correcta_y_no_desactiva_si_falla(client, db, world):
    token = login(client, "athlete@test.com", "AthlPass123")
    for bad in ("", "otra"):
        r = client.request("DELETE", "/api/auth/account", json={"password": bad}, headers=auth_headers(token))
        assert r.status_code == 400
    r = client.request("DELETE", "/api/auth/account", headers=auth_headers(token))   # sin cuerpo
    assert r.status_code == 400
    db.expire_all()
    assert db.get(User, world["uid"]).activo is True
    assert db.query(AccountDeletionRequest).count() == 0


def test_todas_las_rutas_de_borrado_exigen_contrasena(client, db, world):
    token = login(client, "athlete@test.com", "AthlPass123")
    h = auth_headers(token)
    assert client.delete("/api/athlete/me", headers=h).status_code == 400
    assert client.request("DELETE", "/api/athlete/account", json={}, headers=h).status_code == 400
    assert client.post("/api/account/deletion-request", json={}, headers=h).status_code == 400
    client.cookies.clear()
    assert client.post("/api/account/deletion-request", json={"password": "AthlPass123"}).status_code == 401


def test_un_usuario_no_puede_borrar_la_cuenta_de_otro(client, db, world, coach_user):
    # el id jamas se toma del cuerpo: el coach pidiendo con el id del atleta borra SOLO la suya
    ctoken = login(client, "coach@test.com", "CoachPass123")
    r = client.post("/api/account/deletion-request",
                    json={"password": "CoachPass123", "user_id": world["uid"], "athlete_id": world["uid"]},
                    headers=auth_headers(ctoken))
    assert r.status_code == 200
    db.expire_all()
    assert db.get(User, world["uid"]).activo is True
    assert db.get(User, world["coach"]).activo is False
    # con la contrasena del atleta pero la sesion del coach (ya desactivada): no pasa
    assert client.post("/api/account/deletion-request", json={"password": "AthlPass123"},
                       headers=auth_headers(ctoken)).status_code in (400, 401, 403)
    reqs = db.query(AccountDeletionRequest).all()
    assert len(reqs) == 1 and reqs[0].user_id == world["coach"]


def test_solicitud_revoca_integraciones_cierra_coach_y_es_idempotente(client, db, world):
    token = login(client, "athlete@test.com", "AthlPass123")
    # (credenciales Garmin legacy despues del login: el login dispara un sync en segundo plano)
    u = db.get(User, world["uid"])
    u.garmin_email, u.garmin_password = "a@garmin.test", "secret"
    db.commit()
    assert _ask(client, token).status_code == 200
    db.expire_all()
    u = db.get(User, world["uid"])
    assert u.activo is False
    assert (u.garmin_email, u.garmin_password, u.strava_access_token, u.intervals_access_token) == (None,) * 4
    assert db.query(GarminOAuthToken).filter_by(user_id=world["uid"]).count() == 0
    assert db.query(ProviderConnection).filter_by(user_id=world["uid"]).count() == 0
    rel = db.query(CoachAthlete).filter_by(athlete_id=world["uid"]).one()
    assert rel.activo is False and rel.status == "ended"
    assert db.query(FlowSubscription).filter_by(user_id=world["uid"]).one().status == "cancelada"
    # datos AUN no purgados: la purga ocurre en el job, tras la gracia
    assert db.query(WellnessLog).filter_by(user_id=world["uid"]).count() == 1
    req = db.query(AccountDeletionRequest).one()
    assert req.status == "pendiente" and req.purge_after > req.requested_at
    assert (req.deadline_at - req.requested_at).days == 30
    # segunda solicitud (p.ej. otro dispositivo): misma solicitud, sin duplicar
    from api.routes.account_routes import confirm_and_request
    from fastapi import Response
    confirm_and_request(db, u, "AthlPass123", Response())
    assert db.query(AccountDeletionRequest).count() == 1


def test_el_job_no_purga_antes_de_la_gracia(client, db, world):
    token = login(client, "athlete@test.com", "AthlPass123")
    _ask(client, token)
    assert ad.process_due_requests(db) == {"purged": 0, "failed": 0}
    assert db.query(WellnessLog).filter_by(user_id=world["uid"]).count() == 1


def test_cascada_completa_tabla_por_tabla(client, db, world, tmp_path, monkeypatch):
    from api import storage as st
    local = st.LocalStorage(tmp_path)
    monkeypatch.setattr(st, "storage", local)
    uid = world["uid"]
    local.save(f"blood_lab_files/{uid}/e1.pdf", b"pdf")
    local.save(f"blood_lab_pending/{uid}/tok.pdf", b"pdf")
    local.save(f"blood_lab_files/otro-usuario/e9.pdf", b"ajeno")
    local.save("avatars/av1.jpg", b"img")
    db.get(User, uid).avatar_photo_path = "avatars/av1.jpg"
    db.commit()

    token = login(client, "athlete@test.com", "AthlPass123")
    _ask(client, token)
    res = ad.process_due_requests(db, now=_now() + timedelta(days=8))
    assert res == {"purged": 1, "failed": 0}
    db.expire_all()

    # 1) ninguna fila "delete"/"null" apunta ya al usuario
    left = _refs(db, uid)
    expected_left = {k for k, v in ad.POLICY.items() if v in ("keep", "scrub")}
    assert set(left) <= expected_left, f"quedaron filas fuera de keep/scrub: {set(left) - expected_left}"
    # 2) lo que se conserva, conserva exactamente lo esperado y sin datos personales
    assert db.query(FlowSubscription).filter_by(user_id=uid).one().flow_customer_id is None
    assert db.query(FlowSubscription).filter_by(user_id=uid).one().register_token is None
    assert db.query(FlowSubscription).filter_by(user_id=uid).one().status == "cancelada"
    assert db.query(FlowPaymentEvent).filter_by(user_id=uid).count() == 1
    logs = db.query(AuditLog).filter(AuditLog.user_id == uid).all()
    assert logs and all((a.ip, a.user_agent, a.detail, a.resource) == (None,) * 4 for a in logs)
    # 3) el tercero conserva su fila, desvinculada
    n = db.query(CommunityNotification).filter_by(user_id=world["coach"]).one()
    assert n.actor_id is None
    # 4) mensajes de ambos sentidos fuera
    assert db.query(Message).count() == 0
    # 5) la cuenta queda como tumba anonima
    u = db.get(User, uid)
    assert u.activo is False and u.nombre == "Cuenta eliminada"
    assert u.email.endswith("@deleted.invalid") and "athlete" not in u.email
    assert u.password_hash == "!" and u.weight_kg is None and u.stripe_customer_id is None
    assert u.avatar_photo_path is None
    # 6) archivos: los del usuario fuera, los ajenos intactos
    assert not local.exists(f"blood_lab_files/{uid}/e1.pdf")
    assert not local.exists(f"blood_lab_pending/{uid}/tok.pdf")
    assert not local.exists("avatars/av1.jpg")
    assert local.exists("blood_lab_files/otro-usuario/e9.pdf")
    # 7) la coach sigue existiendo y sin la relacion
    assert db.get(User, world["coach"]).activo is True
    assert db.query(CoachAthlete).filter_by(coach_id=world["coach"]).count() == 0


def test_registro_auditable_sin_datos_personales(client, db, world):
    token = login(client, "athlete@test.com", "AthlPass123")
    _ask(client, token)
    ad.process_due_requests(db, now=_now() + timedelta(days=8))
    db.expire_all()
    req = db.query(AccountDeletionRequest).one()
    assert req.status == "completada" and req.completed_at and req.user_id is None
    assert req.user_ref and req.user_ref != world["uid"] and len(req.user_ref) == 16
    blob = json.dumps({c.name: str(getattr(req, c.name)) for c in req.__table__.columns})
    for pii in ("athlete@test.com", "Athlete", "AthlPass123", world["uid"]):
        assert pii not in blob
    summary = json.loads(req.summary_json)
    assert "purged" in summary and "revoked" in summary
    assert all(isinstance(v, int) for v in summary["purged"].values())
    assert db.query(AuditLog).filter(AuditLog.action == "account.deletion.requested").count() == 1


def test_purga_con_datos_de_terceros_dependientes_no_rompe_fk(client, db, world, coach_user):
    """Actividad del atleta con sesion del plan del coach apuntandola: debe purgar sin error de FK."""
    uid = world["uid"]
    act = GarminActivity(user_id=uid, activity_id="g-1", name="x", date_iso="2026-11-01")
    db.add(act)
    db.commit()
    db.add(PlanSession(athlete_id=uid, garmin_activity_id=act.id, date_iso="2026-11-01", sport="run",
                       title="Rodaje", plan_id=_plan_for(db, coach_user.id, uid)))
    db.commit()
    token = login(client, "athlete@test.com", "AthlPass123")
    _ask(client, token)
    res = ad.process_due_requests(db, now=_now() + timedelta(days=8))
    assert res == {"purged": 1, "failed": 0}
    db.expire_all()
    assert db.query(GarminActivity).filter_by(user_id=uid).count() == 0
    assert db.query(PlanSession).filter_by(athlete_id=uid).count() == 0


def _plan_for(db, coach_id, athlete_id):
    from api.models import TrainingPlan
    p = TrainingPlan(coach_id=coach_id, athlete_id=athlete_id, name="Plan",
                     start_date="2026-11-01", end_date="2026-12-01", weeks=4)
    db.add(p)
    db.commit()
    return p.id


def test_purga_fallida_se_reintenta(client, db, world, monkeypatch):
    token = login(client, "athlete@test.com", "AthlPass123")
    _ask(client, token)
    boom = {"n": 0}
    real = ad.purge_user

    def flaky(d, r):
        boom["n"] += 1
        if boom["n"] == 1:
            raise RuntimeError("falla")
        return real(d, r)

    monkeypatch.setattr(ad, "purge_user", flaky)
    later = _now() + timedelta(days=8)
    assert ad.process_due_requests(db, now=later) == {"purged": 0, "failed": 1}
    req = db.query(AccountDeletionRequest).one()
    assert req.status == "error" and req.last_error == "RuntimeError"
    assert ad.process_due_requests(db, now=later) == {"purged": 1, "failed": 0}
    db.expire_all()
    assert db.query(AccountDeletionRequest).one().status == "completada"


def test_cuenta_borrada_no_recupera_acceso_por_reset_de_contrasena(client, db, world):
    token = login(client, "athlete@test.com", "AthlPass123")
    _ask(client, token)
    ad.process_due_requests(db, now=_now() + timedelta(days=8))
    r = client.post("/api/auth/login", json={"email": "athlete@test.com", "password": "AthlPass123"})
    assert r.status_code == 401   # el correo ya no existe en el sistema


def test_job_registrado_en_el_scheduler():
    src = (ROOT / "api" / "scheduler.py").read_text(encoding="utf-8")
    assert "_process_account_deletions" in src and 'id="account_deletions"' in src


# ── pagina publica y enlaces ──────────────────────────────────────

def test_pagina_publica_responde_200_sin_sesion(client):
    r = client.get("/eliminar-cuenta.html")
    assert r.status_code == 200
    html = r.text
    assert "partnerships@labxperformanceapp.com" in html
    assert "athlete_profile.html" in html          # enlace al flujo con sesion
    assert "30" in html


def test_privacy_enlaza_a_la_pagina_de_eliminacion():
    html = (ROOT / "privacy.html").read_text(encoding="utf-8")
    assert 'href="eliminar-cuenta.html"' in html


def test_pagina_publica_precacheada_y_sin_guardia_de_sesion():
    html = (ROOT / "eliminar-cuenta.html").read_text(encoding="utf-8")
    assert "auth.js" not in html and "routes.config.js" not in html   # pagina publica: sin guard
    assert "'/eliminar-cuenta.html'" in (ROOT / "sw.js").read_text(encoding="utf-8")
