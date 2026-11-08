"""TEMA-CLARO-FIX (BUILD 346): semaforos de las bandas 2 y 3 por variables del tema."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "dashboard.html").read_text(encoding="utf-8")
CSS = (ROOT / "theme-vars.css").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")

_A = HTML.index("function drawSparkline(")
_B = HTML.index("MFS_UI") + 1800
REGION = HTML[_A:_B]

LIGHT_HEX = ["#10B981", "#F0A500", "#EF4444", "#0EA5E9", "#FF6535", "#3D6880"]


def test_sin_hex_claros_en_el_js_de_las_tarjetas():
    for hx in LIGHT_HEX:
        assert ("'%s'" % hx) not in REGION, hx
        assert ("'%s'" % hx.lower()) not in REGION, hx
    assert not re.search(r"rgba\(255,\s*255,\s*255", REGION)


def test_sin_sufijo_hex_sobre_colores():
    assert not re.search(r"color \+ '(55|18|2e)'", REGION)
    assert "function lxA(" in HTML and "function lxTone(" in HTML


def test_variable_faint_en_ambos_temas():
    assert len(re.findall(r"--faint:", CSS)) == 2
    assert "--faint: #3d6880;" in CSS  # el oscuro conserva el valor previo


def test_sparkline_usa_style():
    assert 'style="stroke:' in REGION and 'style="fill:' in REGION


def test_build_346():
    assert re.search(r"BUILD_VERSION = '(34[6-9]|3[5-9]\d|[4-9]\d\d)'", SW)
