"""ASISTENTE-CLARO (BUILD 407): panel del Asistente IA y tarjetas Mental en modo claro."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_panel_ia_tiene_variables_claras_en_theme_vars():
    css = _read("theme-vars.css")
    # el comentario no debe cerrarse antes de tiempo (bug real al construir esto)
    assert css.count("/*") == css.count("*/")
    m = re.search(r"\[data-theme='light'\]\s+#lx-ai-panel\s*\{([^}]*)\}", css)
    assert m, "falta el bloque claro del panel IA"
    body = m.group(1)
    nav = _read("nav.js")
    for var in ("--lxb-08121e", "--lxb-06101a", "--lxd-rgba_255_255_255_p04",
                "--lxt-4a7a96", "--lxt-rgba_232_244_248_p88", "--lxt-e8f4f8", "--lxt-fca5a5"):
        assert var in body, var
        assert var in nav, var  # nav.js sigue usando la variable (mismo patron)


def test_panel_ia_oscuro_conserva_fallbacks():
    nav = _read("nav.js")
    assert "var(--lxb-08121e,#08121E)" in nav and "var(--lxb-06101a,#06101A)" in nav


def test_estado_men_scope_claro():
    html = _read("estado.html")
    assert re.search(r"html\[data-theme='light'\]\s+\.men-scope\s*\{[^}]*--card:\s*#ffffff", html)
    assert "--card: #08121e;" in html  # el oscuro no se toca


def test_build_407():
    sw = _read("sw.js")
    assert "var BUILD_VERSION = '407';" in sw
