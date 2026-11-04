"""CQ5 — VO2max rotulado por origen (H18) y paridad de PMC entre superficies (H20)."""
import re
from datetime import date, timedelta
from pathlib import Path

from api.models import GarminActivity, GarminTrainingLoad
from api.services.performance_analytics_service import compute_vo2max_history
from .conftest import login, auth_headers

ROOT = Path(__file__).resolve().parents[2]
ANALYTICS = (ROOT / "analytics.html").read_text(encoding="utf-8")
DASH = (ROOT / "dashboard.html").read_text(encoding="utf-8")
DETALLE = (ROOT / "detalle.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")


def _iso(days_ago):
    return (date.today() - timedelta(days=days_ago)).isoformat()


# ---- H18: serie estimada rotulada ---------------------------------------
def test_vo2_timeline_marca_el_origen_de_cada_lectura(db, athlete_user):
    for i, d in enumerate((40, 30, 20)):
        db.add(GarminActivity(
            user_id=athlete_user.id, date_iso=_iso(d), sport="run",
            avg_hr=150, dist_km=10.0, dur_min=55 + i, name="r" + str(i), activity_id=9000 + i,
        ))
    db.commit()
    r = compute_vo2max_history(athlete_user.id, db, days_back=365, sport="running")
    assert r["timeline"], "debe haber lecturas estimadas"
    assert {t["source"] for t in r["timeline"]} == {"estimated"}
    assert r["estimated_readings"] == len(r["timeline"])
    assert r["garmin_readings"] == 0


def test_analytics_rotula_estimado_en_serie_y_leyenda():
    assert 'id="vo2-legend"' in ANALYTICS
    assert "_renderVo2Legend(d.timeline)" in ANALYTICS
    assert "t.source === 'estimated'" in ANALYTICS
    assert "an_vo2_leg_est" in ANALYTICS


def test_leyenda_vo2_en_los_3_idiomas():
    for key in ("an_vo2_leg_garmin", "an_vo2_leg_est"):
        assert len(re.findall(key + ":", I18N)) == 3, key


# ---- H20: paridad de PMC ------------------------------------------------
def _seed_load(db, user, last_days_ago):
    for k in range(60, last_days_ago - 1, -1):
        ctl = 50 + (60 - k) * 0.1
        db.add(GarminTrainingLoad(
            user_id=user.id, date_iso=_iso(k), ctl=ctl, atl=ctl + 8,
            tsb=-8.0, tss=60.0,
        ))
    db.commit()


def test_dashboard_cabecera_igual_a_pmc_el_dia_sincronizado(client, db, athlete_user):
    _seed_load(db, athlete_user, last_days_ago=0)
    tok = login(client, "athlete@test.com", "AthlPass123")
    d = client.get("/api/athlete/dashboard", headers=auth_headers(tok)).json()
    last = d["pmc"][-1]
    assert last["dt"] == _iso(0)
    assert abs(d["ctl"] - last["ctl"]) < 0.11
    assert abs(d["atl"] - last["atl"]) < 0.11
    assert abs(d["tsb"] - last["tsb"]) < 0.25


def test_cabecera_proyectada_cuando_no_hay_sync_hoy(client, db, athlete_user):
    """Contrato: la cabecera (ctl/atl/tsb) se proyecta a hoy; pmc termina en la
    ultima fila guardada. Las 3 superficies deben mostrar la cabecera."""
    _seed_load(db, athlete_user, last_days_ago=3)
    tok = login(client, "athlete@test.com", "AthlPass123")
    d = client.get("/api/athlete/dashboard", headers=auth_headers(tok)).json()
    last = d["pmc"][-1]
    assert last["dt"] == _iso(3)
    assert d["ctl"] < last["ctl"]
    assert abs(round(d["ctl"] - d["atl"], 1) - d["tsb"]) < 0.11


def test_analytics_usa_la_cabecera_proyectada_como_dashboard_y_detalle():
    assert "series.concat" in ANALYTICS
    assert "ctl: d.ctl" in ANALYTICS and "tsb: d.tsb" in ANALYTICS
    assert "var tsb = typeof d.tsb === 'number' ? d.tsb : last.tsb" in ANALYTICS
    assert "d.tsb != null" in DASH
    for f in ("d.ctl", "d.atl", "d.tsb"):
        assert "value: Math.round(" + f + " * 10) / 10" in DETALLE
    for src in (ANALYTICS, DASH, DETALLE):
        assert "/athlete/dashboard" in src
