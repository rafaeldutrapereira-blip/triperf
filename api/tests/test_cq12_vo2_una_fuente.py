"""CQ12 — VO2max: una sola fuente por cifra/serie (Garmin manda; estimada solo sin Garmin)."""
from datetime import date, timedelta

from api.models import GarminActivity, GarminHealthDaily
from api.services.performance_analytics_service import compute_vo2max_history


def _iso(days_ago):
    return (date.today() - timedelta(days=days_ago)).isoformat()


def _runs(db, user, days):
    for i, d in enumerate(days):
        db.add(GarminActivity(
            user_id=user.id, date_iso=_iso(d), sport="run", avg_hr=150,
            dist_km=10.0, dur_min=55 + i, name=f"r{i}", activity_id=7000 + i,
        ))
    db.commit()


def _garmin(db, user, readings):
    for d, v in readings:
        db.add(GarminHealthDaily(user_id=user.id, date_iso=_iso(d), vo2max_running=v))
    db.commit()


def test_con_ambas_fuentes_manda_garmin_y_tendencia_solo_garmin(db, athlete_user):
    _runs(db, athlete_user, (40, 30, 20, 120, 130))
    _garmin(db, athlete_user, [(150, 50.0), (130, 51.0), (10, 54.0), (5, 56.0)])
    r = compute_vo2max_history(athlete_user.id, db, days_back=365, sport="running")
    assert {t["source"] for t in r["timeline"]} == {"garmin"}
    assert r["vo2max_source"] == "garmin"
    assert r["vo2max_is_estimated"] is False
    assert r["vo2max_current"] == 56.0  # lectura Garmin mas reciente, no promedio
    # recientes (<90d): 54,56 -> 55 ; previas (90-180d): 50,51 -> 50.5
    assert r["vo2max_prev"] == 50.5
    assert r["trend_delta"] == 4.5
    assert r["estimated_readings"] == 0


def test_sin_garmin_la_estimada_sale_marcada(db, athlete_user):
    _runs(db, athlete_user, (40, 30, 20))
    r = compute_vo2max_history(athlete_user.id, db, days_back=365, sport="running")
    assert r["timeline"]
    assert {t["source"] for t in r["timeline"]} == {"estimated"}
    assert r["vo2max_source"] == "estimated"
    assert r["vo2max_is_estimated"] is True
    assert r["vo2max_current"] is not None


def test_ningun_numero_mezcla_fuentes(db, athlete_user):
    _runs(db, athlete_user, (40, 30, 20))
    _garmin(db, athlete_user, [(60, 50.0)])
    r = compute_vo2max_history(athlete_user.id, db, days_back=365, sport="running")
    assert {t["source"] for t in r["timeline"]} == {"garmin"}
    # la unica lectura Garmin es >30d; current no puede ser promedio con estimadas
    assert r["vo2max_current"] == 50.0


def test_sin_datos_no_hay_fuente(db, athlete_user):
    r = compute_vo2max_history(athlete_user.id, db, days_back=365, sport="running")
    assert r["vo2max_source"] is None
    assert r["vo2max_current"] is None
    assert r["timeline"] == []
