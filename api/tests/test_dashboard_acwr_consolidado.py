"""
P11-B parte 2 — ACWR consolidado en el dashboard (contrato estático).

La tarjeta principal muestra el peor ACWR entre deportes, el detalle por
deporte queda en un <details> cerrado por defecto y la frase de lectura tiene
su nodo (#kc-acwr-tip, que antes el JS buscaba sin que existiera).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASH = (ROOT / "dashboard.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")


def test_clave_dash_acwr_detail_en_tres_idiomas():
    assert len(re.findall(r"^\s*dash_acwr_detail:", I18N, re.M)) == 3


def test_detalle_acwr_es_details_cerrado_por_defecto():
    m = re.search(r"<details id=\"acwr-detail\"[^>]*>", DASH)
    assert m, "no existe <details id='acwr-detail'>"
    assert " open" not in m.group(0), "el detalle no debe partir abierto"
    assert 'data-i18n="dash_acwr_detail"' in DASH


def test_detalle_contiene_las_cuatro_filas_por_deporte():
    start = DASH.index('<details id="acwr-detail"')
    end = DASH.index("</details>", start)
    bloque = DASH[start:end]
    for sp in ("swim", "bike", "run", "gym"):
        assert f'id="kc-acwr-{sp}"' in bloque, sp
        assert f'id="kc-acwr-{sp}-val"' in bloque, sp
    # injury no es un deporte: queda fuera del detalle
    assert 'id="kc-injury"' not in bloque


def test_frase_de_lectura_tiene_su_nodo():
    # El JS ya escribía en #kc-acwr-tip; el nodo faltaba en el HTML.
    assert 'id="kc-acwr-tip"' in DASH
    assert "getElementById('kc-acwr-tip')" in DASH


def test_la_tarjeta_principal_usa_el_peor_valor():
    assert "worstAcwr" in DASH
    # mismo mapeo de zonas que el agregado, sin umbrales nuevos
    assert "acwrZones[worstAcwr.zone]" in DASH
    assert "zones[worstAcwr ? worstAcwr.zone : 'no_data']" in DASH
