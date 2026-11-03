"""A1: GET /athlete/estado-hoy — veredicto unico (peor de Recovery y Mental)."""
from api.models import MentalFatigueScore, RecoveryScore
from api.services.estado_veredicto import mental_sev, pick_governing, recovery_sev

from .conftest import auth_headers, login

D = "2026-11-03"
URL = "/api/athlete/estado-hoy?date_iso=" + D


def _seed(db, user, rec=None, men=None):
    if rec is not None:
        db.add(RecoveryScore(user_id=user.id, date_iso=D, score=rec, level="good",
                             recommendation="texto recovery", data_completeness=0.5))
    if men is not None:
        score, level = men
        db.add(MentalFatigueScore(user_id=user.id, date_iso=D, score=score, level=level,
                                  color="#000000", recommendation="texto mental",
                                  data_completeness=0.5))
    db.commit()


def _get(client, user, db, plan="agegroup"):
    user.plan_nivel = plan
    db.commit()
    token = login(client, "athlete@test.com", "AthlPass123")
    return client.get(URL, headers=auth_headers(token))


# ── Regla pura ──────────────────────────────────────────────────────────────
def test_severidades():
    assert [recovery_sev(s) for s in (90, 70, 69, 40, 39)] == [0, 0, 1, 1, 2]
    assert mental_sev("peak", 0) == 0 and mental_sev("moderate", 99) == 1
    assert mental_sev("critical", 99) == 2 and mental_sev(None, 60) == 1


def test_pick_gana_peor_severidad():
    r = {"src": "rec", "sev": 0, "score": 90}
    m = {"src": "men", "sev": 2, "score": 95}
    assert pick_governing(r, m) is m


def test_pick_empate_severidad_menor_score():
    r = {"src": "rec", "sev": 1, "score": 60}
    m = {"src": "men", "sev": 1, "score": 50}
    assert pick_governing(r, m) is m


def test_pick_empate_total_gobierna_recovery():
    r = {"src": "rec", "sev": 1, "score": 55}
    m = {"src": "men", "sev": 1, "score": 55}
    assert pick_governing(r, m) is r


# ── Endpoint ────────────────────────────────────────────────────────────────
def test_endpoint_peor_severidad_gobierna(client, db, athlete_user):
    _seed(db, athlete_user, rec=85, men=(30, "critical"))
    j = _get(client, athlete_user, db).json()
    assert j["status"] == "ok" and j["governs"] == "men" and j["sev"] == 2
    assert j["score"] == 30 and j["label"] == "Crítico" and j["text"] == "texto mental"
    assert j["recovery"]["sev"] == 0 and j["mental"]["sev"] == 2


def test_endpoint_desempate_por_score(client, db, athlete_user):
    _seed(db, athlete_user, rec=60, men=(50, "moderate"))
    j = _get(client, athlete_user, db).json()
    assert j["sev"] == 1 and j["governs"] == "men" and j["score"] == 50


def test_endpoint_empate_total_gobierna_recovery(client, db, athlete_user):
    _seed(db, athlete_user, rec=50, men=(50, "moderate"))
    j = _get(client, athlete_user, db).json()
    assert j["governs"] == "rec" and j["score"] == 50


def test_endpoint_solo_una_fuente(client, db, athlete_user):
    _seed(db, athlete_user, rec=80)
    j = _get(client, athlete_user, db).json()
    # el MFS se deriva del Recovery real ya existente (comportamiento previo de /mental)
    assert j["governs"] == "rec" and j["sev"] == 0 and j["recovery"]["score"] == 80


def test_endpoint_sin_datos_es_neutro(client, db, athlete_user):
    r = _get(client, athlete_user, db)
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "no_data" and j["sev"] is None and j["score"] is None
    assert j["governs"] is None and j["label"] == "Sin datos de hoy"
    assert j["recovery"] is None and j["mental"] is None


def test_endpoint_gating_basico(client, db, athlete_user):
    _seed(db, athlete_user, rec=20, men=(20, "critical"))
    r = _get(client, athlete_user, db, plan="basico")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "plan_locked" and j["sev"] is None
    assert j["available"] == {"recovery": False, "mental": False}
    assert j["recovery"] is None and j["mental"] is None


def test_endpoint_requiere_auth(client):
    assert client.get(URL).status_code in (401, 403)


def test_endpoint_fecha_invalida(client, db, athlete_user):
    athlete_user.plan_nivel = "agegroup"
    db.commit()
    token = login(client, "athlete@test.com", "AthlPass123")
    r = client.get("/api/athlete/estado-hoy?date_iso=nope", headers=auth_headers(token))
    assert r.status_code == 422
