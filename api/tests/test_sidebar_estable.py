"""
Sprint MENUBAR — sidebar fijo y estable (estandar intervals.icu).
Guardias sobre nav.css / nav.js: sin transform ni `transition: all` en el
sidebar de escritorio, marca estatica, y reserva de espacio en .sb-user.
El drawer movil (@media) y la barra superior movil quedan fuera.
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


def test_marca_del_sidebar_estatica():
    # La rotacion solo existe bajo .sb-tb-logo (barra movil), no en el sidebar.
    for m in re.finditer(r"([^{}]*)\{[^{}]*animation\s*:\s*sbl-spin", _sin_comentarios(CSS)):
        assert "sb-tb-logo" in m.group(1), m.group(1)
    assert not re.search(r"(^|\})\s*\.sbl-(flower|arcs)\s*\{", _sin_comentarios(CSS))


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
    for sel in (".sb-lnk", ".sb-brand", ".sb-foot"):
        assert re.search(r"\bheight\s*:\s*\d+px", reglas[sel]), sel
        assert "overflow: hidden" in reglas[sel], sel


def test_activo_sin_cambio_de_peso():
    for sel, body in _reglas_planas():
        if sel.startswith(".sb-lnk:hover") or sel.startswith(".sb-lnk.on"):
            assert "font-weight" not in body, sel
