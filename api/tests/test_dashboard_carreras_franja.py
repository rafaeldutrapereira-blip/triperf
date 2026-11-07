"""CARRERAS-DASHBOARD: la franja de carreras del año del Dashboard (estructura de página)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASH = (ROOT / "dashboard.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")


def test_fuente_unica_es_athlete_races_sin_legacy():
    assert "/athlete/races" in DASH
    assert "kl_next_race" not in DASH
    assert "kl_athlete_data" not in DASH[DASH.index("function renderRaceStrip"):DASH.index("function tick(")]


def test_el_perfil_ya_no_pinta_la_carrera_en_la_tarjeta():
    # el bloque goal-countdown y el resto del dashboard siguen; solo cae el pintado desde /athlete/profile
    assert "profile.race_goal_date" not in DASH
    assert "_apiRaceSet" not in DASH


def test_estado_vacio_y_enlace_al_perfil_se_mantienen():
    assert 'id="kc-race-empty"' in DASH
    assert 'data-i18n="dash_no_goal"' in DASH
    assert 'data-i18n="dash_races_add"' in DASH
    assert 'id="kc-race-year"' in DASH


def test_hoy_y_manana_tienen_texto_propio():
    t = DASH[DASH.index("function tick("):DASH.index("setInterval(tick")]
    assert "dash_races_today" in t and "dash_races_tomorrow" in t


def test_claves_trilingues_y_build_341():
    for k in ("dash_races_title", "dash_races_main", "dash_races_today", "dash_races_tomorrow",
              "dash_races_days_to", "dash_races_none_next", "dash_races_add"):
        assert I18N.count("    " + k + ":") == 3, k
    assert re.search(r"BUILD_VERSION = '(34[2-9]|3[5-9]\d|[4-9]\d\d)'", SW)


def test_no_toca_goal_countdown():
    assert "/races/goal-countdown" in DASH
