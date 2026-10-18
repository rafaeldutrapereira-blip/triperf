"""
athlete-app.html oculta Comunidad (barra inferior) y Race Day / Mi Equipo (menú)
para planes que no los incluyen. Usa el mismo catálogo que la web
(routes.config.js). Estos tests verifican el contrato estático: que la página
carga el catálogo, que los ids existen una sola vez, y que el mapeo apunta a
módulos cuyo minPlan es agegroup (el mismo que la web).
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "athlete-app.html").read_text(encoding="utf-8")
CATALOG = (ROOT / "routes.config.js").read_text(encoding="utf-8")


def _min_plan(module_id: str) -> str:
    m = re.search(r"id:\s*'" + re.escape(module_id) + r"'.*?minPlan:\s*'(\w+)'", CATALOG, re.S)
    assert m, f"módulo {module_id} sin minPlan en routes.config.js"
    return m.group(1)


def test_athlete_app_carga_routes_config():
    assert 'src="routes.config.js' in APP


@pytest.mark.parametrize("element_id", ["nav-community", "menu-item-raceday", "menu-item-gear"])
def test_elemento_gated_existe_una_vez(element_id):
    assert APP.count(f'id="{element_id}"') == 1


def test_mapeo_de_visibilidad_por_plan():
    block = re.search(r"var _PLAN_GATED_ITEMS = \[(.*?)\];", APP, re.S)
    assert block, "falta _PLAN_GATED_ITEMS"
    pairs = re.findall(r"el:\s*'([^']+)',\s*mod:\s*'([^']+)'", block.group(1))
    assert pairs == [
        ("nav-community", "community"),
        ("menu-item-raceday", "race_day"),
        ("menu-item-gear", "gear"),
    ]


@pytest.mark.parametrize("module_id", ["community", "race_day", "gear"])
def test_modulos_ocultos_son_agegroup_en_la_web(module_id):
    # Básico no los incluye; agegroup y elite sí. Mismo criterio que la web.
    assert _min_plan(module_id) == "agegroup"


def test_visibilidad_usa_canaccess_de_la_web():
    assert "LX_ROUTES.canAccess(sess, it.mod)" in APP
    assert "_applyPlanVisibility(p.plan_nivel)" in APP


def test_barra_inferior_ajusta_columnas_a_botones_visibles():
    assert "getElementById('bottom-nav')" in APP
    assert "repeat(' + visibles + ', 1fr)" in APP
