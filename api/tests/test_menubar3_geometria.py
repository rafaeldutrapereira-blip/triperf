"""MENUBAR-3: la geometria del shell vive SOLO en nav.css; el menu no cambia
de posicion/ancho entre paginas y su barra de scroll no se ve."""

import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def _htmls():
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "*.html")))


def _norm(s):
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return re.sub(r"\s+", " ", s)


def test_hay_paginas_html():
    assert len(_htmls()) > 10


def test_ningun_html_fija_offset_de_220px():
    pat = re.compile(r"(padding|margin)-left\s*:\s*220px", re.I)
    assert [n for n in _htmls() if pat.search(_read(n))] == []


def test_ningun_html_redefine_el_sidebar():
    # Ni ancho del #sidebar ni reglas locales del shell: viven en nav.css.
    pat_sidebar = re.compile(r"#sidebar\s*\{[^}]*\b(width|min-width|max-width)\s*:", re.I)
    pat_var = re.compile(r"--sb-w\s*:")
    malos = [n for n in _htmls() if pat_sidebar.search(_read(n)) or pat_var.search(_read(n))]
    assert malos == []


def test_coach_sin_copia_local_del_menu():
    t = _read("coach.html")
    for sel in (r"\n\s*#sidebar\s*\{", r"\n\s*\.sb-lnk\s*\{", r"\n\s*\.sb-nav\s*\{", r"\n\s*\.sb-brand\s*\{"):
        assert not re.search(sel, t), sel


def test_mi_plan_sin_slideup():
    assert "slideUp" not in _read("training_plan.html")


def test_nav_css_geometria_232():
    css = _norm(_read("nav.css"))
    m = re.search(r"#sidebar \{([^}]*)\}", css)
    assert m and "width: 232px" in m.group(1)
    assert re.search(r"body \{ padding-left: 232px; \}", css)


def test_nav_css_oculta_barra_de_scroll_del_menu():
    css = _norm(_read("nav.css"))
    m = re.search(r"#sidebar \{([^}]*)\}", css)
    assert m and "scrollbar-width: none" in m.group(1)
    assert re.search(r"#sidebar::-webkit-scrollbar \{ display: none; \}", css)
    # el elemento que realmente scrollea es .sb-nav: mismo trato, sin perder overflow-y
    m2 = re.search(r"\.sb-nav \{([^}]*)\}", css)
    assert m2 and "scrollbar-width: none" in m2.group(1) and "overflow-y: auto" in m2.group(1)
    assert re.search(r"\.sb-nav::-webkit-scrollbar \{ display: none; \}", css)


def test_nav_js_conserva_scroll_del_menu():
    js = _read("nav.js")
    assert "lx_sb_scroll" in js
    assert "sessionStorage.setItem(KEY" in js and "sessionStorage.getItem(KEY" in js
    assert "scrollTop" in js
