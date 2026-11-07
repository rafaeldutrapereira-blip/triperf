"""A4: GET /api/onboarding/status -- 4 booleanos calculados de datos reales."""
from datetime import date, timedelta

from .conftest import login, auth_headers
from ..auth import hash_password
from ..models import (
    AssignedWorkout, GarminActivity, GarminOAuthToken, GarminPlannedWorkout,
    OwnPlanSession, ProviderConnection, User, WorkoutTemplate,
)

URL = "/api/onboarding/status"
PW = "A4Pass-12345"
FULL = dict(ftp=250, weight_kg=70.0, fcmax=185, css="1:45", run_pace="4:30", sexo="m")


def _user(db, email, plan="basico", **kw):
    u = User(email=email, nombre=email, password_hash=hash_password(PW),
             rol="atleta", plan_nivel=plan, activo=True, **kw)
    db.add(u)
    db.commit()
    return u


def _status(client, email):
    h = auth_headers(login(client, email, PW))
    client.cookies.clear()
    r = client.get(URL, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_requires_auth(client):
    client.cookies.clear()
    assert client.get(URL).status_code in (401, 403)


def test_atleta_nuevo_todo_falso(client, db):
    _user(db, "a4new@test.com")
    d = _status(client, "a4new@test.com")
    assert d["steps"] == {"connect": False, "history": False, "plan": False, "profile": False}
    assert d["all_done"] is False and d["activities_count"] == 0
    assert set(d["profile_missing"]) == set(FULL)


def test_connect_cada_proveedor(client, db):
    casos = {
        "strava": dict(strava_access_token="x"),
        "intervals": dict(intervals_access_token="x"),
    }
    for name, kw in casos.items():
        _user(db, f"a4c-{name}@test.com", **kw)
        assert _status(client, f"a4c-{name}@test.com")["steps"]["connect"] is True, name
    # Garmin legacy: un login con credenciales dispara un sync real en background,
    # asi que se cargan DESPUES de iniciar sesion.
    for name, creds, esperado in (("half", dict(garmin_email="a@b.c"), False),
                                  ("legacy", dict(garmin_email="a@b.c", garmin_password="enc"), True)):
        u = _user(db, f"a4c-{name}@test.com")
        h = auth_headers(login(client, u.email, PW))
        client.cookies.clear()
        for k, v in creds.items():
            setattr(u, k, v)
        db.commit()
        assert client.get(URL, headers=h).json()["steps"]["connect"] is esperado, name
    u = _user(db, "a4c-oficial@test.com")
    db.add(GarminOAuthToken(user_id=u.id, access_token="t"))
    db.commit()
    assert _status(client, "a4c-oficial@test.com")["steps"]["connect"] is True
    u = _user(db, "a4c-polar@test.com")
    db.add(ProviderConnection(user_id=u.id, provider="polar", access_token="t"))
    db.commit()
    assert _status(client, "a4c-polar@test.com")["steps"]["connect"] is True


def test_history_por_actividades(client, db):
    u = _user(db, "a4h@test.com")
    assert _status(client, "a4h@test.com")["steps"]["history"] is False
    db.add(GarminActivity(user_id=u.id, activity_id="1", date_iso="2026-10-01", sport="run"))
    db.commit()
    d = _status(client, "a4h@test.com")
    assert d["steps"]["history"] is True and d["activities_count"] == 1
    # actividades ajenas no cuentan
    _user(db, "a4h2@test.com")
    assert _status(client, "a4h2@test.com")["steps"]["history"] is False


def test_plan_propio_y_planificado_futuro(client, db):
    u = _user(db, "a4p@test.com")
    assert _status(client, "a4p@test.com")["steps"]["plan"] is False
    db.add(OwnPlanSession(user_id=u.id, date_iso="2026-11-01", sport="run", name="Rodaje"))
    db.commit()
    assert _status(client, "a4p@test.com")["steps"]["plan"] is True

    fut = (date.today() + timedelta(days=3)).isoformat()
    past = (date.today() - timedelta(days=3)).isoformat()
    u2 = _user(db, "a4p2@test.com")
    db.add(GarminPlannedWorkout(user_id=u2.id, date_iso=past, title="viejo"))
    db.commit()
    assert _status(client, "a4p2@test.com")["steps"]["plan"] is False  # pasado no cuenta
    db.add(GarminPlannedWorkout(user_id=u2.id, date_iso=fut, title="futuro"))
    db.commit()
    assert _status(client, "a4p2@test.com")["steps"]["plan"] is True

    coach = _user(db, "a4coach@test.com")
    u3 = _user(db, "a4p3@test.com")
    t = WorkoutTemplate(coach_id=coach.id, sport="run", nombre="T")
    db.add(t)
    db.commit()
    aw = AssignedWorkout(template_id=t.id, athlete_id=u3.id, date_iso=fut)
    db.add(aw)
    db.commit()
    assert _status(client, "a4p3@test.com")["steps"]["plan"] is True
    from datetime import datetime
    aw.deleted_at = datetime.utcnow()
    db.commit()
    assert _status(client, "a4p3@test.com")["steps"]["plan"] is False  # borrada


def test_profile_completo_y_cada_campo(client, db):
    _user(db, "a4pf@test.com", **FULL)
    d = _status(client, "a4pf@test.com")
    assert d["steps"]["profile"] is True and d["profile_missing"] == []
    # falta un solo campo -> incompleto, y lo nombra
    for i, (k, empty) in enumerate([("ftp", None), ("weight_kg", None), ("fcmax", 0),
                                    ("css", " "), ("run_pace", None), ("sexo", None)]):
        _user(db, f"a4pf{i}@test.com", **{**FULL, k: empty})
        d = _status(client, f"a4pf{i}@test.com")
        assert d["steps"]["profile"] is False and d["profile_missing"] == [k], k


def test_all_done(client, db):
    u = _user(db, "a4all@test.com", strava_access_token="x", **FULL)
    db.add(GarminActivity(user_id=u.id, activity_id="9", date_iso="2026-10-01", sport="run"))
    db.add(OwnPlanSession(user_id=u.id, date_iso="2026-11-01", sport="run", name="R"))
    db.commit()
    d = _status(client, "a4all@test.com")
    assert all(d["steps"].values()) and d["all_done"] is True


# --- frontend / i18n / build --------------------------------------------------
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_I18N = (_ROOT / "i18n.js").read_text(encoding="utf-8")
_DASH = (_ROOT / "dashboard.html").read_text(encoding="utf-8-sig")
_KEYS = "onb_title onb_progress onb_step_connect onb_step_history onb_step_plan onb_step_profile onb_dismiss".split()


def test_i18n_tres_idiomas_y_placeholders():
    for k in _KEYS:
        assert len(re.findall(rf"\b{k}:", _I18N)) == 3, k
    found = re.findall(r"onb_progress: '([^']*)'", _I18N)
    assert all(set(re.findall(r"\{(\w+)\}", f)) == {"done", "total"} for f in found)


def test_tarjeta_oculta_por_defecto_y_endpoint_usado():
    assert 'id="onb-card"' in _DASH and 'id="onb-card" class="w13-front" style="display: none"' in _DASH
    assert "/onboarding/status" in _DASH and "onbDismiss()" in _DASH


def test_sw_build_327():
    sw = (_ROOT / "sw.js").read_text(encoding="utf-8")
    assert int(re.search(r"BUILD_VERSION = '(\d+)'", sw).group(1)) >= 327
