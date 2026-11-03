"""
B10 — Indoor (indoor_workout.html) como constructor de entrenamientos.
W12 — GPS Tracker (gps_tracker.html) RETIRADO del producto: compite con
Garmin/Strava, guardaba en un endpoint inexistente y no tenia enlaces entrantes.

- Indoor: constructor de entrenamientos estructurados, en el sidebar, addon
  para Agegroup/Basico y Elite lo incluye.
- GPS Tracker: sin archivo, sin ruta y sin precache.

El gating de Indoor en servidor ya esta desde B1 (test_plan_gating_b1.py).
"""
from pathlib import Path

from api.module_catalog import MODULES

ROOT = Path(__file__).resolve().parents[2]
INDOOR = (ROOT / "indoor_workout.html").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")
ROUTES = (ROOT / "routes.config.js").read_text(encoding="utf-8")


def test_indoor_sigue_en_rutas_y_envia_workouts():
    assert "indoor_workout.html" in ROUTES
    assert "send-to-watch" in INDOOR  # Indoor construye y envia workouts (S11: via intervals.icu)


def test_gps_tracker_retirado_sin_referencias_vivas():
    assert not (ROOT / "gps_tracker.html").exists()
    assert "gps_tracker" not in ROUTES
    assert "gps_tracker" not in SW


def test_gps_tracker_no_esta_en_html_ni_js_vivos():
    vivos = [
        p
        for ext in ("*.html", "*.js")
        for p in ROOT.glob(ext)
        if "gps_tracker" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    # i18n.js conserva comentarios historicos de secciones; no es una referencia de ruta.
    assert [p.name for p in vivos if p.name != "i18n.js"] == []


def test_indoor_es_addon_con_inclusion_en_elite():
    spec = MODULES["indoor_workout"]
    assert spec.tier == "addon"
    assert spec.addon_id == "indoor"
    assert spec.included_in_elite is True
