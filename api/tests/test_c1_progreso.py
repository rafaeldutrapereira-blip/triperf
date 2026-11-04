"""C1: Progreso en 3 chips (Forma, Records, Potencia/VO2)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "athlete-app.html").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")

_a = HTML.index('<div class="screen" id="screen-progress">')
SCREEN = HTML[_a:HTML.index("<!-- SCREEN 11", _a)]


def test_tres_chips_visibles():
    tabs = re.findall(r'id="pgr-tab-(\w+)"', SCREEN)
    # huella sigue en el HTML (W4, se borra en D1) pero oculta por canAccess
    assert tabs == ["forma", "records", "powervo2", "huella"]


def test_pestanas_retiradas_no_existen():
    for t in ("projection", "distrib", "zones", "insights", "power", "vo2max"):
        assert f'id="pgr-tab-{t}"' not in SCREEN
    for f in ("loadProgressProjection", "renderProgressProjection",
              "loadProgressDistrib", "loadProgressZones"):
        assert f not in HTML
    assert "/analytics/ctl-projection" not in HTML
    assert "/analytics/training-distribution" not in HTML
    assert "/analytics/zone-calibration" not in HTML


def test_potencia_y_vo2_en_un_solo_chip():
    a = SCREEN.index('id="pgr-powervo2-content"')
    seg = SCREEN[a:]
    assert 'id="pgr-power-card"' in seg and 'id="pgr-vo2max-card"' in seg
    i = HTML.index("function progressTab(")
    body = HTML[i:i + 900]
    assert "loadProgressPower(" in body and "loadProgressVo2max(" in body


def test_wpmob_recortado_sin_tooltip():
    assert "wp-mob-tooltip" not in HTML and "_wpMobWireTouch" not in HTML
    assert "function _renderWpMob(" in HTML


def test_goscreen_abre_forma_y_endpoints_intactos():
    assert "progressTab('forma');" in HTML
    for ep in ("/analytics/insights", "/analytics/personal-records",
               "/analytics/power-curve", "/analytics/vo2max"):
        assert ep in HTML


def test_claves_i18n_c1_en_3_idiomas():
    for k in ("c1_tab_forma", "c1_tab_power_vo2"):
        assert I18N.count(k + ":") == 3


def test_build_295():
    m = re.search(r"var BUILD_VERSION = '(\d+)';", SW)
    assert m and int(m.group(1)) >= 295
