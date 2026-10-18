"""
B4 — Páginas muertas eliminadas: dashboard-alt.html, race_predictor.html,
year_in_review.html. Su contenido vive en Hoy, Race Day y Mi Huella.

dashboard-alt-data.js NO se elimina: huella.html lo carga.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RETIRED = ["dashboard-alt.html", "race_predictor.html", "year_in_review.html"]


def test_paginas_eliminadas_no_existen():
    for name in RETIRED:
        assert not (ROOT / name).exists(), f"{name} debería estar eliminado"


def test_sw_no_precachea_paginas_eliminadas():
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    for name in RETIRED:
        assert f"'/{name}'" not in sw, name


def test_auth_js_sin_referencias_a_paginas_eliminadas():
    auth = (ROOT / "auth.js").read_text(encoding="utf-8")
    assert "race_predictor" not in auth
    assert "year_in_review" not in auth


def test_ninguna_pagina_enlaza_a_paginas_eliminadas():
    # Un enlace o carga aparece con comilla o barra antes del nombre; las menciones
    # en comentarios ("rescatado de race_predictor.html") no cuentan.
    for html in ROOT.glob("*.html"):
        text = html.read_text(encoding="utf-8")
        for name in RETIRED:
            assert not re.search(r"['\"/]" + re.escape(name), text), f"{html.name} enlaza a {name}"


def test_dashboard_alt_data_sigue_en_uso():
    assert (ROOT / "dashboard-alt-data.js").exists()
    assert "dashboard-alt-data.js" in (ROOT / "huella.html").read_text(encoding="utf-8")
