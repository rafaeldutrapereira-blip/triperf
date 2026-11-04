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
        ("pgr-tab-huella", "huella"),  # W4: deshabilitada para todos
    ]


@pytest.mark.parametrize("module_id", ["race_day"])
def test_modulos_ocultos_son_agegroup_en_la_web(module_id):
    # Básico no los incluye; agegroup y elite sí. Mismo criterio que la web.
    assert _min_plan(module_id) == "agegroup"


@pytest.mark.parametrize("module_id", ["community", "gear"])
def test_comunidad_y_equipo_son_visibles_para_basico(module_id):
    # Free: lectura de Comunidad y 1 par de zapatillas (decisión de Rafael).
    assert _min_plan(module_id) == "basic"


def test_visibilidad_usa_canaccess_de_la_web():
    assert "LX_ROUTES.canAccess(sess, it.mod)" in APP
    assert "_applyPlanVisibility(p.plan_nivel)" in APP


def test_barra_inferior_ajusta_columnas_a_botones_visibles():
    assert "getElementById('bottom-nav')" in APP
    assert "repeat(' + visibles + ', 1fr)" in APP


def _nav_block():
    m = re.search(r'<nav id="bottom-nav">(.*?)</nav>', APP, re.S)
    assert m, "falta #bottom-nav"
    return m.group(1)


def test_b1_barra_de_4_destinos_fijos():
    nav = _nav_block()
    destinos = re.findall(r'onclick="goScreen\(\'([^\']+)\'\)" id="([^"]+)"', nav)
    assert destinos == [
        ("screen-today", "nav-today"),
        ("screen-week", "nav-week"),
        ("screen-community", "nav-community"),
        ("screen-mas", "nav-menu"),
    ]
    assert "repeat(4, 1fr)" in APP
    for gone in ("nav-wellness", "openMenuSheet", "aicoach-fab"):
        assert gone not in APP


def test_b1_mas_es_pantalla_y_lista_destinos_con_gating():
    assert APP.count('id="screen-mas"') == 1
    mas = APP[APP.index('id="screen-mas"'):]
    mas = mas[: mas.index("<!-- /screens -->")]
    for dest in ("progress", "raceday", "mental", "gear", "profile"):
        assert f"goScreen('screen-{dest}')" in mas
    # P2: Recovery ya no es fila de Más (se entra desde el semaforo de Hoy)
    assert "screen-wellness" not in mas
    assert "showNotifications()" in mas and "doLogout()" in mas
    # Race Day y Mi Equipo conservan su gating por plan, ahora dentro de Más
    assert 'id="menu-item-raceday"' in mas and 'id="menu-item-gear"' in mas
    assert 'id="nav-community"' not in mas


def test_b1_goscreen_conserva_pantallas_y_mapea_la_barra():
    for sid in ("today", "week", "wellness", "community", "profile", "mental",
                "raceday", "progress", "gear", "aicoach", "mas"):
        assert APP.count(f'id="screen-{sid}"') == 1
    nav_map = re.search(r"var navMap = \{(.*?)\};", APP, re.S).group(1)
    for sid, nid in (("today", "nav-today"), ("week", "nav-week"),
                     ("community", "nav-community"), ("mas", "nav-menu")):
        assert f"'screen-{sid}': '{nid}'" in nav_map
