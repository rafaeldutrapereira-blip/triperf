"""CQ1 - readiness: calculo honesto y bandas unicas (H1, H7, H5, H2, H3, H4)."""
import json
import re
from datetime import date, timedelta
from pathlib import Path

from ..models import (
    AIAthleteContext, GarminTrainingLoad, MentalFatigueScore, RecoveryScore, User,
)
from ..routes.race_routes import _predict
from ..services import readiness_service as rs


def _iso(days_ago=0):
    return (date.today() - timedelta(days=days_ago)).isoformat()


def _recovery(db, user, days_ago=0, **kw):
    row = RecoveryScore(
        user_id=user.id, date_iso=_iso(days_ago), score=kw.pop("score", 70),
        hrv_factor=kw.pop("hrv_factor", 80.0), sleep_factor=kw.pop("sleep_factor", 60.0),
        tsb_factor=kw.pop("tsb_factor", 5.0),
        weights_json=kw.pop("weights_json", json.dumps(
            {"hrv": 0.3, "sleep": 0.25, "tsb": 0.2, "stress": 0.15, "body_battery": 0.1, "wellness": 0.0})),
        **kw,
    )
    db.add(row)
    db.commit()
    return row


def _mfs(db, user, days_ago=0, checkin_factor=None):
    db.add(MentalFatigueScore(
        user_id=user.id, date_iso=_iso(days_ago), score=60, level="moderate", color="#F59E0B",
        checkin_factor=checkin_factor, recovery_factor=90.0,
    ))
    db.commit()


# ---- H1 ----------------------------------------------------------------
def test_drs_none_sin_datos():
    r = rs.compute_daily_readiness()
    assert r.drs is None
    assert r.drs_label == "Sin datos suficientes"


def test_drs_none_con_completitud_menor_a_mitad():
    assert rs.compute_daily_readiness(recovery_score=90).drs is None
    assert rs.compute_daily_readiness(recovery_score=90, mental_score=80).drs is not None


def test_endpoint_daily_drs_null(client, athlete_user):
    from .conftest import login, auth_headers
    tok = login(client, "athlete@test.com", "AthlPass123")
    r = client.get("/api/readiness/daily", headers=auth_headers(tok))
    assert r.status_code == 200
    assert r.json()["drs"] is None


# ---- H7 ----------------------------------------------------------------
_BASE = dict(ftp=250, css_sec=95, run_pace_sec=300, weight_kg=70, tsb=0, labs_factors={})


def test_prediccion_sin_readiness_omite_multiplicador_y_baja_confianza():
    sin = _predict(dist="703", readiness=None, **_BASE)
    con = _predict(dist="703", readiness=100, **_BASE)
    assert sin["readiness_mult"] == 1.0
    assert sin["readiness_used"] is False
    assert sin["confidence_note"]
    assert sin["confidence_pct"] < con["confidence_pct"]
    assert con["confidence_note"] is None


def test_race_default_ya_no_inventa_70():
    src = (Path(__file__).resolve().parents[1] / "routes" / "race_routes.py").read_text(encoding="utf-8", errors="replace")
    assert "current_readiness or 70" not in src


# ---- H5 ----------------------------------------------------------------
def test_bandas_unicas_backend():
    assert [b[0] for b in rs.DRS_BANDS] == [85, 70, 55, 35, 0]
    for drs, label in [(100, "Óptimo"), (85, "Óptimo"), (84, "Bueno"), (55, "Moderado"), (35, "Bajo"), (0, "Crítico")]:
        assert rs._drs_metadata(drs)[0] == label


def test_lx_info_sin_bandas_propias():
    js = (Path(__file__).resolve().parents[2] / "lx-info.js").read_text(encoding="utf-8")
    block = js[js.index("  readiness: {"): js.index("  pmc: {")]
    assert "rangos" not in block
    assert "Descansar hoy" not in js
    assert "rdData.drs_label" in js


# ---- H2 ----------------------------------------------------------------
def test_mental_sin_checkin_no_disponible(db, athlete_user):
    _mfs(db, athlete_user, checkin_factor=None)  # MFS compuesto sin check-in
    assert rs.get_mental_score(athlete_user.id, db) is None
    r = rs.compute_daily_readiness(recovery_score=70, trs=80, tsb=5, mental_score=None)
    mental = [d for d in r.dimensions if d.name == "Estado Mental"][0]
    assert mental.available is False
    assert r.data_completeness == 0.75  # renormaliza con 3 dimensiones


def test_mental_con_checkin_usa_factor_del_checkin(db, athlete_user):
    _mfs(db, athlete_user, checkin_factor=55.0)
    assert rs.get_mental_score(athlete_user.id, db) == 55.0


def test_recuperacion_sin_tsb(db, athlete_user):
    _recovery(db, athlete_user, hrv_factor=80.0, sleep_factor=60.0, tsb_factor=0.0)
    # hrv .30 y sleep .25 renormalizados; el TSB (0) no entra
    esperado = (80 * 0.30 + 60 * 0.25) / 0.55
    assert abs(rs.get_recovery_score(athlete_user.id, db) - esperado) < 0.01


# ---- H3 ----------------------------------------------------------------
def test_frescura_recuperacion_y_mental_2_dias(db, athlete_user):
    _recovery(db, athlete_user, days_ago=3)
    _mfs(db, athlete_user, days_ago=3, checkin_factor=70.0)
    assert rs.get_recovery_score(athlete_user.id, db) is None
    assert rs.get_mental_score(athlete_user.id, db) is None


def test_tsb_viejo_descartado(db, athlete_user):
    db.add(GarminTrainingLoad(user_id=athlete_user.id, date_iso=_iso(4), tsb=12.0))
    db.commit()
    assert rs.get_tsb(athlete_user.id, db) is None
    db.add(GarminTrainingLoad(user_id=athlete_user.id, date_iso=_iso(3), tsb=7.0))
    db.commit()
    assert rs.get_tsb(athlete_user.id, db) == 7.0


# ---- H4 ----------------------------------------------------------------
def test_refresco_tras_checkin(db, athlete_user):
    from ..routes.mental_routes import CheckinCreate, save_checkin
    _recovery(db, athlete_user)
    db.add(GarminTrainingLoad(user_id=athlete_user.id, date_iso=_iso(0), ctl=40, atl=35, tsb=5.0))
    db.commit()
    save_checkin(CheckinCreate(anxiety=4, motivation=4, focus=4, confidence=4, mood=4),
                 db=db, current_user=athlete_user)
    ctx = db.query(AIAthleteContext).filter(AIAthleteContext.user_id == athlete_user.id).first()
    assert ctx is not None
    assert ctx.current_readiness is not None  # recovery + mental + forma = 3/4 dimensiones
