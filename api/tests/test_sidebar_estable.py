"""
Sprint MENUBAR — sidebar fijo y estable (estandar intervals.icu).
Guardias sobre nav.css / nav.js: sin transform ni `transition: all` en el
sidebar de escritorio, marca estatica en TODAS las superficies (MENUBAR-2),
filas de 36px sin barra lateral, y reserva de espacio en .sb-user.
El drawer movil (@media) y la barra superior movil quedan fuera de las
reglas de transform/animation, pero NO de `transition: all` ni de la marca.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "nav.css").read_text(encoding="utf-8")
JS = (ROOT / "nav.js").read_text(encoding="utf-8")

# Selectores que NO son del sidebar de escritorio.
_FUERA = ("sb-tb-", "sb-topbar", "sb-hamburger", "sb-overlay", "lx-uw", "lx-upgrade")


def _sin_comentarios(s):
    return re.sub(r"/\*.*?\*/", "", s, flags=re.S)


def _reglas_planas():
    """(selector, cuerpo) de reglas de primer nivel (sin @media/@keyframes)."""
    css = _sin_comentarios(CSS)
    out, i, n = [], 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            break
        sel = css[i:j].strip()
        depth, k = 1, j + 1
        while depth and k < n:
            depth += {"{": 1, "}": -1}.get(css[k], 0)
            k += 1
        body = css[j + 1:k - 1]
        if not sel.startswith("@"):
            out.append((sel, body))
        i = k
    return out


def _del_sidebar(sel):
    if any(f in sel for f in _FUERA):
        return False
    return "#sidebar" in sel or ".sb-" in sel


def test_sin_transition_all_en_sidebar():
    malas = [s for s, b in _reglas_planas()
             if _del_sidebar(s) and re.search(r"transition\s*:\s*all\b", b)]
    assert not malas, malas


def test_sin_transform_ni_animation_en_sidebar():
    # Excepcion: spinner de carga de .sb-sync (estado "sincronizando", no hover).
    malas = [s for s, b in _reglas_planas()
             if _del_sidebar(s) and s != ".sb-sync.spin svg"
             and re.search(r"(?<![\w-])(transform|animation)\s*:", b)]
    assert not malas, malas


def test_transiciones_solo_color_fondo_opacidad():
    for sel, body in _reglas_planas():
        if not _del_sidebar(sel):
            continue
        for m in re.finditer(r"transition\s*:([^;]+);", body):
            props = re.findall(r"([a-z-]+)\s+[\d.]+m?s", m.group(1))
            assert props, (sel, m.group(0))
            for p in props:
                assert p in ("color", "background-color", "opacity"), (sel, p)
            for d in re.findall(r"([\d.]+)s", m.group(1)):
                assert float(d) <= 0.15, (sel, d)


def test_sin_transition_all_en_todo_nav_css():
    # MENUBAR-2: incluye hamburguesa y overlay (solo transform/opacity).
    assert not re.search(r"transition\s*:\s*all\b", _sin_comentarios(CSS))


def test_marca_estatica_en_todas_las_superficies():
    css = _sin_comentarios(CSS)
    # Ni sidebar ni barra movil rotan la marca; keyframes de giro eliminados.
    assert "sbl-spin" not in css
    assert not re.search(r"\.sbl-(flower|arcs)\b[^{]*\{[^}]*animation", css)
    assert not re.search(r"\.sb-tb-logo[^{]*\{[^}]*animation", css)


def test_filas_36px_sin_barra_lateral():
    lnk = dict(_reglas_planas())[".sb-lnk"]
    assert re.search(r"\bheight\s*:\s*36px", lnk)
    assert "border-left" not in lnk
    assert "text-transform" not in lnk
    assert re.search(r"border-radius\s*:\s*8px", lnk)
    for sel, body in _reglas_planas():
        if sel.startswith(".sb-lnk.on"):
            assert "border-left" not in body, sel


def test_ancho_232_y_padding_del_body():
    reglas = dict(_reglas_planas())
    assert re.search(r"\bwidth\s*:\s*232px", reglas["#sidebar"])
    assert re.search(r"padding-left\s*:\s*232px", reglas["body"])
    assert "280px" in CSS  # el drawer movil conserva 280px


def test_sb_user_reserva_espacio():
    reglas = dict(_reglas_planas())
    user = reglas[".sb-user"]
    assert re.search(r"\bheight\s*:\s*\d+px", user)
    assert "overflow: hidden" in user
    ubox = reglas[".sb-ubox"]
    assert re.search(r"\bheight\s*:\s*\d+px", ubox) and "overflow: hidden" in ubox
    uname = reglas[".sb-uname"]
    assert "text-overflow: ellipsis" in uname and "white-space: nowrap" in uname
    assert re.search(r"\bheight\s*:\s*\d+px", uname)
    assert 'class="sb-ubox"' in JS


def test_filas_y_marca_con_alto_fijo():
    reglas = dict(_reglas_planas())
    for sel in (".sb-lnk", ".sb-brand", ".sb-foot", ".sb-sync"):
        assert re.search(r"\bheight\s*:\s*\d+px", reglas[sel]), sel
        assert "overflow: hidden" in reglas[sel], sel


def test_activo_sin_cambio_de_peso():
    for sel, body in _reglas_planas():
        if sel.startswith(".sb-lnk:hover") or sel.startswith(".sb-lnk.on"):
            assert "font-weight" not in body, sel
