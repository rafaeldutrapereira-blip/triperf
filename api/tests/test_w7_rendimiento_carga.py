"""W7 - Rendimiento: tarjeta Carga nativa y pestanas 6 -> 4."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "analytics.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")


def _tabs():
    bar = re.search(r'<div class="an-tab-bar">(.*?)</div>\s*<!--', HTML, re.S).group(1)
    return re.findall(r"switchAnTab\('(\w+)'", bar)


def test_sin_iframe_a_detalle():
    assert "<iframe" not in HTML
    assert "embed=1" not in HTML


def test_cuatro_pestanas_visibles():
    assert _tabs() == ["carga", "power", "vo2max", "more"]


def test_records_distribucion_zonas_bajo_mas_analisis():
    more = HTML[HTML.index('id="pane-more"'):]
    for n in ("records", "distrib", "zones"):
        assert f'id="pane-{n}"' in more
        assert f"switchAnTab('{n}')" in more
    for marker in ("pr-tabs", "dist-sport-bars", "zone-cycling-card"):
        assert marker in more


def test_curva_y_vo2_siguen_en_sus_pestanas():
    assert "cp-canvas" in HTML and "vo2-canvas" in HTML


def test_hash_y_tab_conocidos_resuelven():
    for h in ("carga", "potencia", "vo2max", "mas", "records", "distribucion", "zonas"):
        assert f"'{h}'" in HTML, h
    assert "_anInitialName" in HTML and "get('tab')" in HTML
    m = re.search(r"var AN_TABS = \[(.*?)\];", HTML, re.S).group(1)
    for n in ("carga", "power", "vo2max", "records", "distrib", "zones"):
        assert f"'{n}'" in m


def test_enlace_a_historial_completo():
    assert 'href="detalle.html?metric=pmc"' in HTML


def test_rango_vive_dentro_de_pestanas_y_sin_notas():
    for n in ("power", "vo2max", "distrib"):
        assert f'id="an-range-{n}"' in HTML
    for k in ("an-note-carga", "an-note-records", "an-note-zones"):
        assert k not in HTML
    assert "Reubica el selector de rango" not in HTML


def test_resumen_sin_fila_de_cifras_duplicada():
    assert "T.sessions" not in HTML and "T.hours" not in HTML
    assert "an-sum-headline" in HTML


def test_claves_i18n_nuevas_en_tres_idiomas():
    for k in ("an_tab_more", "an_load_full", "an_load_up", "an_load_fresh", "an_load_empty"):
        assert len(re.findall(r"^\s*" + k + r":", I18N, re.M)) == 3, k
    assert "Potencia en bici" in I18N


def test_build_version_271():
    assert "BUILD_VERSION = '271'" in SW
