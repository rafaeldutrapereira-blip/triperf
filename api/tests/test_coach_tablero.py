"""COACH-TABLERO (BUILD 382): reglas de alertas por coach + endpoints del tablero."""
import re
from datetime import date, datetime, timedelta, timezone

from .conftest import login, auth_headers
from api.auth import hash_password
from api.models import (
    User, CoachAthlete, WellnessLog, CoachAlertRule, AIAthleteContext,
)


def _h(client):
    return auth_headers(login(client, "coach@test.com", "CoachPass123"))


def _athlete(db, coach, email="a1@test.com", nombre="Ana"):
    u = User(email=email, nombre=nombre, password_hash=hash_password("Passw0rd123"),
             rol="athlete", plan_nivel="basico", activo=True)
    db.add(u)
    db.flush()
    db.add(CoachAthlete(coach_id=coach.id, athlete_id=u.id, status="active"))
    db.commit()
    return u


def _wellness(db, user, fatigue=None, soreness=None, day=None):
    db.add(WellnessLog(user_id=user.id, date_iso=(day or date.today()).isoformat(),
                       fatigue=fatigue, soreness=soreness))
    db.commit()


DEFAULTS = {"fatigue": 4, "soreness": 4, "rpe": 8, "window_hours": 48}


def test_reglas_defaults_sin_fila(client, coach_user):
    r = client.get("/api/coach/alert-rules", headers=_h(client))
    assert r.status_code == 200
    j = r.json()
    assert {k: j[k] for k in DEFAULTS} == DEFAULTS
    assert j["defaults"] == DEFAULTS


def test_reglas_put_y_get_persisten(client, db, coach_user):
    h = _h(client)
    body = {"fatigue": 3, "soreness": 2, "rpe": 6, "window_hours": 72}
    assert client.put("/api/coach/alert-rules", json=body, headers=h).status_code == 200
    j = client.get("/api/coach/alert-rules", headers=h).json()
    assert {k: j[k] for k in DEFAULTS} == body
    assert db.query(CoachAlertRule).filter_by(coach_id=coach_user.id).count() == 1
    # segundo PUT actualiza la misma fila (una por coach)
    client.put("/api/coach/alert-rules", json={**body, "rpe": 7}, headers=h)
    assert db.query(CoachAlertRule).filter_by(coach_id=coach_user.id).count() == 1


def test_reglas_validan_rangos(client, coach_user):
    h = _h(client)
    ok = dict(DEFAULTS)
    for k, bad in [("fatigue", 0), ("fatigue", 6), ("soreness", 0), ("soreness", 6),
                   ("rpe", 0), ("rpe", 11), ("window_hours", 11), ("window_hours", 169)]:
        r = client.put("/api/coach/alert-rules", json={**ok, k: bad}, headers=h)
        assert r.status_code == 422, (k, bad, r.text)
    # bordes validos
    assert client.put("/api/coach/alert-rules", json={"fatigue": 1, "soreness": 5, "rpe": 10, "window_hours": 12}, headers=h).status_code == 200
    assert client.put("/api/coach/alert-rules", json={**ok, "window_hours": 168}, headers=h).status_code == 200
    # nada invalido quedo guardado
    assert client.get("/api/coach/alert-rules", headers=h).json()["window_hours"] == 168


def test_reglas_requieren_coach(client, athlete_user):
    t = login(client, "athlete@test.com", "AthlPass123")
    assert client.get("/api/coach/alert-rules", headers=auth_headers(t)).status_code in (401, 403)
    assert client.put("/api/coach/alert-rules", json=DEFAULTS, headers=auth_headers(t)).status_code in (401, 403)
    assert client.get("/api/coach/alert-rules").status_code in (401, 403)


def test_reglas_son_por_coach(client, db, coach_user):
    h = _h(client)
    client.put("/api/coach/alert-rules", json={**DEFAULTS, "fatigue": 2}, headers=h)
    otro = User(email="coach2@test.com", nombre="Otro", password_hash=hash_password("CoachPass123"),
                rol="coach", plan_nivel="agegroup", activo=True)
    db.add(otro)
    db.commit()
    h2 = auth_headers(login(client, "coach2@test.com", "CoachPass123"))
    assert client.get("/api/coach/alert-rules", headers=h2).json()["fatigue"] == 4


def test_alerts_respeta_umbral_de_fatiga(client, db, coach_user):
    h = _h(client)
    a = _athlete(db, coach_user)
    _wellness(db, a, fatigue=3)
    assert client.get("/api/coach/alerts", headers=h).json() == {"alerts": [], "count": 0}
    client.put("/api/coach/alert-rules", json={**DEFAULTS, "fatigue": 3}, headers=h)
    j = client.get("/api/coach/alerts", headers=h).json()
    assert j["count"] == 1 and set(j) == {"alerts", "count"}
    assert j["alerts"][0]["type"] == "wellness" and "Fatiga 3/5" in j["alerts"][0]["detail"]
    # restaurar defaults revierte
    client.put("/api/coach/alert-rules", json=DEFAULTS, headers=h)
    assert client.get("/api/coach/alerts", headers=h).json()["count"] == 0


def test_alerts_default_mantiene_comportamiento(client, db, coach_user):
    h = _h(client)
    a = _athlete(db, coach_user)
    _wellness(db, a, fatigue=4)
    j = client.get("/api/coach/alerts", headers=h).json()
    assert j["count"] == 1
    assert set(j["alerts"][0]) == {"type", "athlete_id", "athlete_name", "date", "detail", "level"}
    assert j["alerts"][0]["level"] == "warning"


def test_alerts_respeta_umbral_de_dolor(client, db, coach_user):
    h = _h(client)
    a = _athlete(db, coach_user)
    _wellness(db, a, soreness=2)
    assert client.get("/api/coach/alerts", headers=h).json()["count"] == 0
    client.put("/api/coach/alert-rules", json={**DEFAULTS, "soreness": 2}, headers=h)
    assert client.get("/api/coach/alerts", headers=h).json()["count"] == 1


def test_alerts_respeta_ventana_en_horas(client, db, coach_user):
    h = _h(client)
    a = _athlete(db, coach_user)
    _wellness(db, a, fatigue=5, day=date.today() - timedelta(days=4))  # ~96 h
    assert client.get("/api/coach/alerts", headers=h).json()["count"] == 0  # ventana 48 h
    client.put("/api/coach/alert-rules", json={**DEFAULTS, "window_hours": 168}, headers=h)
    assert client.get("/api/coach/alerts", headers=h).json()["count"] == 1


def test_alerts_respeta_umbral_rpe(client, db, coach_user):
    from api.models import WorkoutTemplate, AssignedWorkout, WorkoutLog
    h = _h(client)
    a = _athlete(db, coach_user)
    t = WorkoutTemplate(coach_id=coach_user.id, sport="run", nombre="T", dur_min=30, tss=30)
    db.add(t)
    db.flush()
    aw = AssignedWorkout(template_id=t.id, athlete_id=a.id, date_iso=date.today().isoformat())
    db.add(aw)
    db.flush()
    db.add(WorkoutLog(user_id=a.id, assignment_id=aw.id, rpe=6, completado=True,
                      logged_at=datetime.now(timezone.utc).replace(tzinfo=None)))
    db.commit()
    assert client.get("/api/coach/alerts", headers=h).json()["count"] == 0
    client.put("/api/coach/alert-rules", json={**DEFAULTS, "rpe": 6}, headers=h)
    j = client.get("/api/coach/alerts", headers=h).json()
    assert j["count"] == 1 and j["alerts"][0]["type"] == "rpe"


def test_alerts_sin_atletas_sigue_vacio(client, coach_user):
    assert client.get("/api/coach/alerts", headers=_h(client)).json() == {"alerts": [], "count": 0}


# ---- tablero: status-board / squad-overview / intelligence ----

def test_status_board_y_squad_vacios_sin_atletas(client, coach_user):
    h = _h(client)
    assert client.get("/api/coach/status-board", headers=h).json() == []
    r = client.get("/api/coach/squad-overview", headers=h)
    assert r.status_code == 200
    j = r.json()
    assert j["squad_size"] == 0 and j["athletes"] == []


def test_status_board_sin_contexto_es_unknown_y_nulos_honestos(client, db, coach_user):
    h = _h(client)
    a = _athlete(db, coach_user)
    rows = client.get("/api/coach/status-board", headers=h).json()
    assert len(rows) == 1
    r = rows[0]
    assert r["athlete_id"] == a.id and r["status"] == "unknown"
    for k in ("readiness", "ctl", "atl", "tsb", "acwr", "hrv", "injury_risk", "compliance_pct"):
        assert r[k] is None, k  # nunca 0 ni estimado


def test_status_board_con_atletas_y_filtro_por_grupo(client, db, coach_user):
    from api.models import Group, GroupMember
    h = _h(client)
    a = _athlete(db, coach_user, "a1@test.com", "Ana")
    b = _athlete(db, coach_user, "b1@test.com", "Beto")
    db.add(AIAthleteContext(user_id=a.id, current_readiness=80, current_acwr=1.0))
    db.add(AIAthleteContext(user_id=b.id, current_readiness=30, current_acwr=1.6))
    g = Group(coach_id=coach_user.id, nombre="G")
    db.add(g)
    db.flush()
    db.add(GroupMember(group_id=g.id, athlete_id=a.id))
    db.commit()
    rows = client.get("/api/coach/status-board", headers=h).json()
    assert [r["status"] for r in rows] == ["critical", "optimal"]  # critico primero
    solo = client.get(f"/api/coach/status-board?group_id={g.id}", headers=h).json()
    assert [r["athlete_id"] for r in solo] == [a.id]
    assert client.get("/api/coach/status-board?group_id=nope", headers=h).status_code == 404
    sq = client.get("/api/coach/squad-overview", headers=h).json()
    assert sq["squad_size"] == 2
    ids = {x["athlete_id"] for x in sq["athletes"]}
    assert ids == {a.id, b.id}


def test_intelligence_del_atleta_y_ajeno_prohibido(client, db, coach_user):
    h = _h(client)
    a = _athlete(db, coach_user)
    j = client.get(f"/api/coach/athletes/{a.id}/intelligence", headers=h)
    assert j.status_code == 200 and j.json()["athlete_id"] == a.id
    ajeno = User(email="x@test.com", nombre="X", password_hash=hash_password("Passw0rd123"),
                 rol="athlete", plan_nivel="basico", activo=True)
    db.add(ajeno)
    db.commit()
    assert client.get(f"/api/coach/athletes/{ajeno.id}/intelligence", headers=h).status_code in (403, 404)


# ---- estructura: migracion, borrado de cuenta, UI aditiva ----

def test_migracion_alembic_encadenada():
    import pathlib
    p = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "d5e6f7a8b9c0_coach_alert_rules.py"
    s = p.read_text(encoding="utf-8")
    assert 'down_revision = "c4d5e6f7a8b9"' in s and "coach_alert_rules" in s


def test_borrado_de_cuenta_conoce_la_tabla():
    from api.account_deletion import POLICY
    assert POLICY.get("coach_alert_rules.coach_id") == "delete"


def test_coach_html_tab_aditivo_y_sellos():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    html = (root / "coach.html").read_text(encoding="utf-8")
    for tab in ("overview", "athletes", "groups", "workouts", "mi-atleta", "assign",
                "plan", "adherence", "gantt", "report", "adp-coach", "rec-coach", "tablero"):
        assert f'data-tab="{tab}"' in html and f'id="tab-{tab}"' in html, tab
    sw = (root / "sw.js").read_text(encoding="utf-8")
    assert int(re.search(r"var BUILD_VERSION = '(\d+)';", sw).group(1)) >= 382
    m = re.search(r"'/i18n\.js\?v=(\d+)'", sw)
    assert f"i18n.js?v={m.group(1)}" in html


def test_i18n_claves_nuevas_en_tres_idiomas():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    i18n = (root / "i18n.js").read_text(encoding="utf-8")
    html = (root / "coach.html").read_text(encoding="utf-8")
    keys = set(re.findall(r"data-i18n=\"(tbl_\w+|tab_tablero)\"", html))
    keys |= set(re.findall(r"'(tbl_\w+)'", html))
    assert len(keys) > 50
    for k in keys:
        assert len(re.findall(rf"\b{k}:", i18n)) == 3, k
