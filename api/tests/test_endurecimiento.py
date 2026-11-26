"""ENDURECIMIENTO: H6 (/garmin/notify), A4 (borrado vs enlaces publicos), A5 (metricas/salud), A6 (correos)."""
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest

from api import garmin_ingest
from api.models import GarminActivity, GarminPushPayload, TrainingPlan, User

NOTIFY = "/api/integrations/garmin/notify"
SECRET = "s3cret-test-value-123"
BODY = {"dailies": [{"userId": "ghost", "calendarDate": "2026-11-05"}]}


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setenv("GARMIN_NOTIFY_SECRET", SECRET)
    monkeypatch.delenv("GARMIN_NOTIFY_ALLOWED_IPS", raising=False)


# ── H6 ──────────────────────────────────────────────────────────────────────
def test_notify_sin_secreto_configurado_se_rechaza(client, monkeypatch):
    monkeypatch.delenv("GARMIN_NOTIFY_SECRET", raising=False)
    assert client.post(NOTIFY, json=BODY).status_code == 404
    assert client.post(f"{NOTIFY}/{SECRET}", json=BODY).status_code == 404


def test_notify_sin_o_con_mal_secreto_401(client, db, secret):
    assert client.post(NOTIFY, json=BODY).status_code == 401
    assert client.post(NOTIFY, json=BODY, headers={"X-Garmin-Notify-Secret": "x"}).status_code == 401
    assert client.post(f"{NOTIFY}/otro", json=BODY).status_code == 401
    assert db.query(GarminPushPayload).count() == 0


def test_notify_con_secreto_en_cabecera_o_ruta_pasa(client, db, secret):
    assert client.post(NOTIFY, json=BODY, headers={"X-Garmin-Notify-Secret": SECRET}).status_code == 200
    assert client.post(f"{NOTIFY}/{SECRET}", json=BODY).status_code == 200
    assert db.query(GarminPushPayload).count() == 2


def test_notify_lista_de_ip(client, secret, monkeypatch):
    h = {"X-Garmin-Notify-Secret": SECRET}
    monkeypatch.setenv("GARMIN_NOTIFY_ALLOWED_IPS", "203.0.113.0/24, 198.51.100.7")
    assert client.post(NOTIFY, json=BODY, headers={**h, "CF-Connecting-IP": "203.0.113.9"}).status_code == 200
    assert client.post(NOTIFY, json=BODY, headers={**h, "CF-Connecting-IP": "198.51.100.7"}).status_code == 200
    assert client.post(NOTIFY, json=BODY, headers={**h, "CF-Connecting-IP": "8.8.8.8"}).status_code == 403
    # X-Forwarded-For no cuenta
    assert client.post(NOTIFY, json=BODY, headers={**h, "X-Forwarded-For": "203.0.113.9"}).status_code == 403


def test_notify_tope_de_filas(client, db, secret, monkeypatch):
    monkeypatch.setenv("GARMIN_PUSH_MAX_ROWS", "3")
    monkeypatch.setenv("GARMIN_PUSH_MAX_ORPHAN_ROWS", "100")
    for _ in range(6):
        assert client.post(f"{NOTIFY}/{SECRET}", json=BODY).status_code == 200
    assert db.query(GarminPushPayload).count() == 3


def test_notify_tope_de_filas_sin_usuario(client, db, secret, monkeypatch):
    monkeypatch.setenv("GARMIN_PUSH_MAX_ORPHAN_ROWS", "2")
    for _ in range(5):
        client.post(f"{NOTIFY}/{SECRET}", json=BODY)
    assert db.query(GarminPushPayload).count() == 2


def test_notify_body_grande_413(client, secret):
    big = {"dailies": [{"userId": "x", "pad": "a" * 1_100_000}]}
    assert client.post(f"{NOTIFY}/{SECRET}", json=big).status_code == 413


def test_retencion_filas_sin_usuario(db):
    old = garmin_ingest._now() - timedelta(days=10)
    db.add_all([
        GarminPushPayload(payload_type="dailies", user_id=None, payload_json="{}", processed=True, received_at=old),
        GarminPushPayload(payload_type="dailies", user_id=None, payload_json="{}", processed=False),
        GarminPushPayload(payload_type="dailies", user_id="u1", payload_json="{}", processed=True, received_at=old),
    ])
    db.commit()
    assert garmin_ingest.purge_unattributed(db) == 1
    assert db.query(GarminPushPayload).count() == 2


# ── A4 ──────────────────────────────────────────────────────────────────────
def test_borrado_anula_enlaces_publicos(client, db, athlete_user):
    from api import account_deletion
    uid = athlete_user.id
    act = GarminActivity(user_id=uid, activity_id=f"a-{uuid.uuid4().hex[:8]}", name="Run", sport="run",
                         date_iso="2026-11-01", share_token="tok-act-1")
    plan = TrainingPlan(coach_id=uid, athlete_id=uid, start_date="2026-11-01", end_date="2026-12-01", name="P", weeks=4, share_token="tok-plan-1")
    db.add_all([act, plan])
    db.commit()
    assert client.get("/api/public/activities/tok-act-1").status_code == 200
    assert client.get("/api/public/plans/tok-plan-1").status_code == 200
    account_deletion.request_deletion(db, db.get(User, uid))
    db.expire_all()
    assert db.query(GarminActivity).filter_by(user_id=uid).one().share_token is None
    assert db.query(TrainingPlan).filter_by(coach_id=uid).one().share_token is None
    assert client.get("/api/public/activities/tok-act-1").status_code == 404
    assert client.get("/api/public/plans/tok-plan-1").status_code == 404


def test_public_404_si_dueno_inactivo_aunque_quede_token(client, db, athlete_user):
    db.add(TrainingPlan(coach_id=athlete_user.id, athlete_id=athlete_user.id, start_date="2026-11-01", end_date="2026-12-01", name="P", weeks=1, share_token="tok-x"))
    db.commit()
    assert client.get("/api/public/plans/tok-x").status_code == 200
    athlete_user.activo = False
    db.commit()
    assert client.get("/api/public/plans/tok-x").status_code == 404


# ── A5 ──────────────────────────────────────────────────────────────────────
def test_api_metrics_protegido(client, monkeypatch):
    monkeypatch.delenv("METRICS_SECRET", raising=False)
    with patch("api.coach_main._METRICS_ALLOWED_IPS", set()):
        assert client.get("/api/metrics").status_code == 404
        monkeypatch.setenv("METRICS_SECRET", "m-secret")
        assert client.get("/api/metrics").status_code == 401
        assert client.get("/api/metrics", headers={"Authorization": "Bearer mal"}).status_code == 401
        r = client.get("/api/metrics", headers={"Authorization": "Bearer m-secret"})
        assert r.status_code == 200 and "labx_up" in r.text


def test_health_recortado(client):
    r = client.get("/health")
    assert r.status_code == 200
    d = r.json()
    assert "version" not in d and "env" not in d
    assert d["status"] in ("ok", "degraded") and "db" in d


# ── A6 ──────────────────────────────────────────────────────────────────────
EVIL = '<a href="https://evil.example">pincha</a>'


def _capture():
    sent = []
    return sent, patch("api.mailer.send_email", side_effect=lambda to, subj, html, **k: sent.append((subj, html)))


def test_correos_escapan_nombre_ip_device_y_gear():
    from api import mailer
    sent, p = _capture()
    with p, patch("api.mailer._geolocate_ip", return_value=None):
        mailer.send_welcome("a@b.c", EVIL)
        mailer.send_day3_drip("a@b.c", EVIL)
        mailer.send_day7_drip("a@b.c", EVIL)
        mailer.send_login_alert("a@b.c", EVIL, '1.2.3.4"><b>x</b>', "Mozilla <i>Chrome/1</i>")
        mailer.send_gear_alert("a@b.c", EVIL, EVIL, "shoe", 90.0, 80)
    assert len(sent) == 5
    for _, html in sent:
        assert EVIL not in html and "<b>x</b>" not in html
        assert "&lt;a href=" in html or "&lt;b&gt;x" in html


def test_geolocate_valida_formato_ip():
    from api import mailer
    with patch("httpx.get") as g:
        assert mailer._geolocate_ip("8.8.8.8/../x?a=b") is None
        assert mailer._geolocate_ip("evil.com#") is None
        g.assert_not_called()
        g.return_value.json.return_value = {"status": "success", "city": "X", "country": "Y"}
        assert mailer._geolocate_ip("8.8.8.8") == "X, Y"
        assert g.call_args[0][0] == "http://ip-api.com/json/8.8.8.8"
