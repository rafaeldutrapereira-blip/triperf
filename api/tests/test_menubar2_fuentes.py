"""
Sprint MENUBAR-2 — fuentes locales sin swap.
Ninguna pagina depende de Google Fonts; fonts.css declara los 7 @font-face
con font-display: optional y los archivos viven en vendor/fonts/.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FUENTES = {
    ("Inter", "400"): "inter-400.woff2",
    ("Inter", "500"): "inter-500.woff2",
    ("Inter", "600"): "inter-600.woff2",
    ("Oswald", "500"): "oswald-500.woff2",
    ("Oswald", "600"): "oswald-600.woff2",
    ("Barlow Condensed", "700"): "barlow-condensed-700.woff2",
    ("Barlow Condensed", "800"): "barlow-condensed-800.woff2",
}


def test_ninguna_pagina_usa_google_fonts():
    malas = []
    for p in sorted(ROOT.glob("*.html")):
        t = p.read_text(encoding="utf-8")
        if "fonts.googleapis.com" in t or "fonts.gstatic.com" in t:
            malas.append(p.name)
    assert not malas, malas


def test_fonts_css_tiene_los_7_font_face_optional():
    css = (ROOT / "fonts.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    bloques = re.findall(r"@font-face\s*\{([^}]*)\}", css)
    assert len(bloques) == 7
    vistos = {}
    for b in bloques:
        fam = re.search(r"font-family\s*:\s*'([^']+)'", b).group(1)
        peso = re.search(r"font-weight\s*:\s*(\d+)", b).group(1)
        assert re.search(r"font-display\s*:\s*optional\b", b), (fam, peso)
        vistos[(fam, peso)] = re.search(r"url\('vendor/fonts/([^']+)'\)", b).group(1)
    assert vistos == FUENTES


def test_los_7_woff2_existen():
    for nombre in FUENTES.values():
        f = ROOT / "vendor" / "fonts" / nombre
        assert f.is_file() and f.stat().st_size > 1000, nombre


def test_paginas_enlazan_fonts_css_y_precargan_inter():
    for p in sorted(ROOT.glob("*.html")):
        t = p.read_text(encoding="utf-8")
        if "nav.css" in t:
            assert 'href="fonts.css?v=373"' in t, p.name
            assert "vendor/fonts/inter-500.woff2" in t, p.name
            assert "vendor/fonts/inter-600.woff2" in t, p.name


def test_sw_build_335_y_precache_de_fuentes():
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    m = re.search(r"BUILD_VERSION\s*=\s*'(\d+)'", sw)
    assert m and int(m.group(1)) >= 335
    ini = sw.index("var PRECACHE")
    pre = sw[ini:sw.index("];", ini)]
    assert "'/fonts.css?v=373'" in pre
    for nombre in FUENTES.values():
        assert "'/vendor/fonts/%s'" % nombre in pre, nombre
