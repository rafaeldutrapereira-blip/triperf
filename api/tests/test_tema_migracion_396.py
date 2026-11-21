"""MIGRACION-TEMA (BUILD 396): componentes compartidos sin colores oscuros fijos en tema claro.

Guardianes estaticos:
  * el muro de plan (nav.css), los toasts/widget IA/estados de carga (nav.js) y el aviso de
    plan (auth.js) no fijan fondos oscuros: usan variables de tema con fallback oscuro;
  * toda variable --lxt-/--lxb- que esos archivos usan esta definida para el tema claro;
  * nav.js traduce los colores de canvas al tema activo (LXCanvasTheme);
  * el texto sobre botones de acento no depende del tema;
  * sellos de version.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _r(n):
    return (ROOT / n).read_text(encoding="utf-8")


def _light_vars():
    css = _r("theme-light.css")
    return set(re.findall(r"(--lx[a-z]-[\w]+)\s*:", css))


def test_nav_css_muro_de_plan_sin_fondo_oscuro_fijo():
    css = _r("nav.css")
    wall = css[css.index("#lx-upgrade-wall"): css.index(".sb-sep")]
    sin_var = re.sub(r"var\([^()]*(?:\([^()]*\)[^()]*)*\)", "", wall)
    malos = re.findall(r"background[^;]*?(#08121e|rgba\(4, 8, 15)", sin_var, flags=re.I)
    assert not malos, malos
    assert "var(--lxb-08121e" in wall and "var(--lxt-f0f9ff" in wall


def test_variables_lx_usadas_en_compartidos_existen_en_tema_claro():
    definidas = _light_vars()
    faltan = []
    for f in ("nav.css", "nav.js", "auth.js", "dashboard.html"):
        # (--on-accent no lleva prefijo lx?-)
        for v in set(re.findall(r"var\((--lx[tbd]-[\w]+)", _r(f))):
            if v not in definidas:
                faltan.append("%s: %s" % (f, v))
    assert not faltan, faltan


def test_nav_js_toast_widget_y_carga_usan_variables():
    js = _r("nav.js")
    toast = js[js.index("el.style.cssText='position:fixed;bottom:1.5rem;left:50%"):]
    toast = toast[: toast.index("document.body.appendChild(el)")]
    assert "background:#08121E" not in toast and "var(--lxb-08121e" in toast
    ai = js[js.index("s.textContent='#lx-ai-btn"): js.index("document.head.appendChild(s)", js.index("s.textContent='#lx-ai-btn"))]
    assert "background:#08121E" not in ai and "background:#06101A" not in ai
    assert "color:#E8F4F8" not in ai
    assert "padding:40px;color:#7FB3CC" not in js


def test_auth_js_aviso_de_plan_sin_fondo_oscuro_fijo():
    assert "background:'#08121E'" not in _r("auth.js")


def test_canvas_se_adapta_al_tema_activo():
    js = _r("nav.js")
    assert "window.LXCanvasTheme" in js
    for p in ("fillStyle", "strokeStyle", "shadowColor", "addColorStop"):
        assert p in js[js.index("LXCanvasTheme"): js.index("var LXTheme = window.LXTheme")]
    # al cambiar de tema se repinta
    assert "LXCanvasTheme.refresh(t)" in js


def test_texto_sobre_boton_de_acento_no_depende_del_tema():
    assert "color: var(--lxt-fff" not in _r("style.css") and "var(--on-accent" in _r("style.css")
    assert "var(--lxt-fff" not in _r("dash-header.js").split(".dhx-bell-badge")[1].split("}")[0]


def test_sellos_de_version():
    sw = _r("sw.js")
    assert "var BUILD_VERSION = '405'" in sw
    for s in ("'/i18n.js?v=404'", "'/theme-light.css?v=396'", "'/nav.js?v=11'", "'/auth.js?v=374'"):
        assert s in sw, s
    for p in ("analytics", "detalle", "nutrition"):
        h = _r(p + ".html")
        assert "i18n.js?v=404" in h and "theme-light.css?v=396" in h, p
        assert "nav.js?v=11" in h, p
