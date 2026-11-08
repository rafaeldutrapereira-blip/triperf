"""SHELL-1: cascara unica (shell.html) con el menu cargado una sola vez."""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def _norm(s):
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return re.sub(r"\s+", " ", s)


def test_shell_existe_con_iframe_y_sidebar():
    h = _read("shell.html")
    assert re.search(r'<iframe[^>]*name="lxcontent"', h)
    assert '<aside id="sidebar"></aside>' in h
    assert "nav.css" in h and "fonts.css" in h


def test_shell_lista_blanca_son_las_paginas_con_navjs():
    h = _read("shell.html")
    m = re.search(r"var ALLOWED = \[(.*?)\];", h, re.S)
    assert m, "falta la lista blanca ALLOWED"
    permitidas = set(re.findall(r"'([\w]+\.html)'", m.group(1)))
    con_nav = {
        n
        for n in os.listdir(ROOT)
        if n.endswith(".html") and n != "shell.html" and "nav.js" in _read(n)
    }
    assert permitidas == con_nav
    assert "DEFAULT_PAGE = 'dashboard.html'" in h
    assert "history.pushState" in h and "popstate" in h


def test_shell_redirige_sin_sesion_a_login():
    h = _norm(_read("shell.html"))
    assert "lx_co_token" in h
    assert "window.top.location.replace('login.html')" in h


def test_navjs_detecta_cascara():
    js = _read("nav.js")
    assert "window.self !== window.top" in js
    assert "lx-in-shell" in js
    assert "window.top.location.replace('login.html')" in js


def test_navcss_reglas_lx_in_shell():
    css = _norm(_read("nav.css"))
    assert "body.lx-in-shell #sidebar" in css
    assert re.search(r"body\.lx-in-shell \{ padding-left: 0;", css)
    # La geometria de 232px no cambia.
    assert "width: 232px" in css and "padding-left: 232px" in css


def test_login_redirige_a_shell_y_sw_precachea():
    assert "'shell.html'" in _read("login.html")
    sw = _read("sw.js")
    assert "'/shell.html'" in sw
    import re
    assert int(re.search(r"BUILD_VERSION = '(\d+)'", sw).group(1)) >= 340


NAV_CSS_V = "8"
NAV_JS_V = "10"


def test_version_de_nav_uniforme_en_todas_las_paginas():
    """Toda pagina raiz que cargue nav.css/nav.js usa la version vigente (v7/v9)."""
    css_re = re.compile(r"nav\.css\?v=(\w+)")
    js_re = re.compile(r"nav\.js\?v=(\w+)")
    paginas = 0
    for n in sorted(os.listdir(ROOT)):
        if not n.endswith(".html"):
            continue
        h = _read(n)
        css, js = css_re.findall(h), js_re.findall(h)
        if css or js:
            paginas += 1
        assert set(css) <= {NAV_CSS_V}, f"{n}: nav.css con version {set(css)}"
        assert set(js) <= {NAV_JS_V}, f"{n}: nav.js con version {set(js)}"
        assert not re.search(r"nav\.css(?!\?v=)['\"]", h), f"{n}: nav.css sin ?v="
        assert not re.search(r"nav\.js(?!\?v=)['\"]", h), f"{n}: nav.js sin ?v="
    assert paginas >= 19
