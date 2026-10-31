"""
B7 â€” Rendimiento: Analytics + Performance en un solo mÃ³dulo con pestaÃ±as
Carga / Potencia / Records. Carga es la vista PMC de detalle.html embebida
con ?embed=1 (decisiÃ³n aprobada por Rafael).

Los asserts de JS/CSS usan `squash()` (ver text_match.py) porque Prettier
reformateÃ³ esas cadenas (espacios y comillas) sin cambiar el comportamiento.
"""
import re
from pathlib import Path

from .text_match import squash

ROOT = Path(__file__).resolve().parents[2]
ANALYTICS = (ROOT / "analytics.html").read_text(encoding="utf-8")
DETALLE = (ROOT / "detalle.html").read_text(encoding="utf-8")
ROUTES = (ROOT / "routes.config.js").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")


def test_analytics_tiene_pestana_carga_embebida_primero():
    assert squash("switchAnTab('carga',this)") in squash(ANALYTICS)
    assert 'id="pane-carga"' in ANALYTICS
    assert 'src="detalle.html?metric=pmc&amp;embed=1"' in ANALYTICS
    assert ANALYTICS.index("switchAnTab('carga'") < ANALYTICS.index("switchAnTab('power'")


def test_pestanas_potencia_y_records_siguen():
    assert "switchAnTab('power'" in ANALYTICS
    assert "switchAnTab('records'" in ANALYTICS


def test_detalle_soporta_modo_embed_sin_cabecera_ni_sidebar():
    assert squash('get("embed")==="1"') in squash(DETALLE)
    assert squash(".lx-embed #sidebar") in squash(DETALLE)
    assert squash(".lx-embed body{padding-left:0 !important") in squash(DETALLE)


def test_modulo_se_llama_rendimiento_y_performance_sale_del_sidebar():
    assert "label:   'Rendimiento'" in ROUTES
    perf = re.search(r"id:\s*'performance',.*?\},", ROUTES, re.S).group(0)
    assert "sidebar: false" in perf
    # El id del mÃ³dulo no cambia (decisiÃ³n B3): las URLs y el gating siguen.
    assert "id:      'analytics'" in ROUTES


def test_claves_nuevas_en_tres_idiomas():
    for k in ("an_tab_load", "nav_rendimiento"):
        assert len(re.findall(r"^\s*" + k + r":", I18N, re.M)) == 3, k
