"""
B10 — Indoor se mantiene separado de gps_tracker (decisión: no fusionar).

- Indoor (indoor_workout.html): constructor de entrenamientos estructurados,
  en el sidebar, addon para Agegroup/Básico y Elite lo incluye.
- gps_tracker.html: registra una actividad real con GPS, fuera del sidebar,
  con cola offline en sw.js.

El gating de Indoor en servidor ya está desde B1 (test_plan_gating_b1.py).
"""
from pathlib import Path

from api.module_catalog import MODULES

ROOT = Path(__file__).resolve().parents[2]
INDOOR = (ROOT / "indoor_workout.html").read_text(encoding="utf-8")
GPS = (ROOT / "gps_tracker.html").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")
ROUTES = (ROOT / "routes.config.js").read_text(encoding="utf-8")


def test_indoor_y_gps_son_paginas_distintas_con_funcion_distinta():
    assert "indoor_workout.html" in ROUTES
    assert "gps_tracker.html" in ROUTES
    assert "send-to-garmin" in INDOOR          # Indoor construye y envía workouts
    assert "workout-log" in GPS                 # GPS registra una actividad real


def test_gps_no_esta_en_el_sidebar():
    # gps_tracker es utilitaria: no tiene entrada de sidebar ni tier.
    gps_entry = [l for l in ROUTES.split("\n") if "gps_tracker" in l]
    assert gps_entry and all("sidebar:false" in l for l in gps_entry)


def test_indoor_es_addon_con_inclusion_en_elite():
    spec = MODULES["indoor_workout"]
    assert spec.tier == "addon"
    assert spec.addon_id == "indoor"
    assert spec.included_in_elite is True


def test_gps_tracker_sigue_en_el_precache_offline():
    # La cola offline de registros GPS depende de la página precacheada.
    assert "'/gps_tracker.html'" in SW
