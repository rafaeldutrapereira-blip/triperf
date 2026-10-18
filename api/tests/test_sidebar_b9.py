"""
B9 — Sidebar por tareas: Entrenar, Recuperar, Planear, Analizar, Cuenta y, solo
para entrenadores, Coach. El orden y la pertenencia a cada grupo salen de
routes.config.js (el mismo que usa nav.js).
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")

EXPECTED = [
    ("entrenar", "dashboard"), ("entrenar", "training_plan"),
    ("entrenar", "indoor_workout"), ("entrenar", "ai_coach"),
    ("recuperar", "recovery"), ("recuperar", "mental"),
    ("recuperar", "nutrition"), ("recuperar", "blood_labs"),
    ("planear", "race_day"), ("planear", "huella"),
    ("analizar", "analytics"),
    ("cuenta", "athlete_profile"), ("cuenta", "gear"), ("cuenta", "community"),
    ("coach", "coach"),
]


def _sidebar_modules():
    if not NODE:
        pytest.skip("node no disponible")
    script = (
        "const fs=require('fs');const src=fs.readFileSync(process.argv[1],'utf8');"
        "const w={};new Function('window',src)(w);"
        "console.log(JSON.stringify(w.LX_ROUTES.modules.filter(m=>m.sidebar&&m.id).map(m=>[m.group,m.id])));"
    )
    out = subprocess.run([NODE, "-e", script, str(ROOT / "routes.config.js")],
                         capture_output=True, text=True, check=True).stdout
    return [tuple(x) for x in json.loads(out)]


def test_sidebar_agrupado_por_tarea_en_orden():
    assert _sidebar_modules() == EXPECTED


def test_adaptativo_y_sesion_fuera_del_sidebar():
    # Adaptativo vive en Plan; Sesión es drill-down. Ninguno tiene entrada propia.
    shown = {mid for _, mid in _sidebar_modules()}
    assert "adaptive" not in shown
    assert "training_detail" not in shown


def test_rendimiento_es_el_unico_modulo_de_analizar():
    groups = [g for g, _ in _sidebar_modules()]
    assert groups.count("analizar") == 1


def test_coach_solo_para_rol_entrenador():
    js = (ROOT / "routes.config.js").read_text(encoding="utf-8")
    assert "group:   'coach'" in js
    assert "roles:   ['coach','admin']" in js


def test_grupos_tienen_titulo_en_nav_js():
    nav = (ROOT / "nav.js").read_text(encoding="utf-8")
    for g in ("entrenar", "recuperar", "planear", "analizar", "cuenta", "coach"):
        assert f"{g}:" in nav, g
