"""TEMA-RESTO (BUILD 349): tema claro/oscuro en todas las paginas pendientes del 344.

Guardianes estaticos:
  * cada pagina aplica data-theme antes del primer pintado y enlaza theme-light.css;
  * ningun color de texto claro hardcodeado fuera de variables en las reglas de las paginas
    (salvo texto sobre fondos de acento, que se queda blanco en ambos temas);
  * el tema oscuro no cambia: todo var(--lx?-<clave>, <fallback>) conserva el color original
    como fallback y la variable solo se redefine bajo [data-theme='light'].
"""
import colorsys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PAGES = (
    "adaptive ai_coach analytics athlete_profile blood_labs coach community detalle estado gear huella "
    "indoor_workout nutrition race_day recovery training_detail training_plan athlete-app landing login "
    "registro onboarding reset-password shared_plan public_activity invitacion app_invitacion privacy tos 404"
).split()

HEX = re.compile(r"(?<![\w&-])#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")


def _read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def _hls(h):
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)


def _strip_vars(val):
    return re.sub(r"var\([^()]*(?:\([^()]*\)[^()]*)*\)", "", val)


def _colored_bg(body):
    for m in re.finditer(r"(?<![\w-])background(?:-color)?\s*:\s*([^;}]*)", body):
        for c in HEX.findall(m.group(1)):  # incluye fallbacks de var(--accent, #ff6535)
            h, l, s = _hls(c[:6] if len(c) == 8 else c)
            if s >= 0.4 and 0.15 < l < 0.8:
                return True
    return False


def _style_blocks(html):
    return re.findall(r"<style(?![^>]*lx-theme-light)[^>]*>(.*?)</style>", html, flags=re.S)


def test_cada_pagina_aplica_tema_antes_del_primer_pintado():
    for p in PAGES:
        h = _read(p + ".html")
        head = h[: h.index("</head>")]
        assert 'localStorage.getItem("labx_theme")' in head, p
        assert 'setAttribute("data-theme"' in head, p
        assert "theme-light.css?v=349" in head, p
        assert 'id="lx-theme-light"' in head, p


def test_sin_colores_de_texto_claros_fuera_de_variables_en_reglas_principales():
    malos = []
    for p in PAGES:
        for css in _style_blocks(_read(p + ".html")):
            for sel, body in re.findall(r"([^{}]*)\{([^{}]*)\}", css):
                if _colored_bg(body):
                    continue
                for m in re.finditer(r"(?<![\w-])color\s*:\s*([^;}]*)", body):
                    for c in HEX.findall(_strip_vars(m.group(1))):
                        h, l, s = _hls(c[:6] if len(c) == 8 else c)
                        if l >= 0.75 and s < 0.4:
                            malos.append("%s: %s { color: #%s }" % (p, sel.strip()[:40], c))
    assert not malos, "texto claro hardcodeado:\n" + "\n".join(malos)


def test_activos_compartidos_sin_texto_claro_hardcodeado():
    malos = []
    for f in ("lx-info.js", "lx-upgrade.js", "dash-header.js", "lx-audit.js", "community.js", "gdpr-banner.js"):
        src = _read(f)
        for sel, body in re.findall(r"([^{}]*)\{([^{}]*)\}", src):
            if _colored_bg(body):
                continue
            for m in re.finditer(r"(?<![\w-])color\s*:\s*([^;}\"'`]*)", body):
                for c in HEX.findall(_strip_vars(m.group(1))):
                    h, l, s = _hls(c[:6] if len(c) == 8 else c)
                    if l >= 0.75 and s < 0.4:
                        malos.append("%s: color #%s" % (f, c))
    assert not malos, "\n".join(malos)


def test_tema_oscuro_intacto_fallback_igual_al_color_original():
    """var(--lxt-0ea5e9,#0EA5E9): la clave del nombre es el color del fallback."""
    pat = re.compile(r"var\(--lx([tbd])-([0-9a-z_]+),\s*([^()]*(?:\([^()]*\))?[^()]*?)\)")
    n = 0
    files = [p + ".html" for p in PAGES] + [
        "lx-info.js", "lx-upgrade.js", "dash-header.js", "lx-audit.js", "community.js", "gdpr-banner.js", "style.css"]
    for f in files:
        for _role, key, fallback in pat.findall(_read(f)):
            n += 1
            norm = re.sub(r"[^0-9a-z]+", "_", fallback.lower().replace(".", "p")).strip("_")
            assert norm == key, "%s: --lx*-%s con fallback %s" % (f, key, fallback)
    assert n > 200


def test_variables_claras_definidas_solo_bajo_tema_claro():
    css = _read("theme-light.css")
    assert "html[data-theme='light']" in css
    # ninguna variable --lx* se define fuera de un bloque [data-theme='light']
    fuera = re.sub(r"\[data-theme='light'\]\s*\{[^{}]*\}", "", css)
    assert "--lxt-" not in fuera and "--lxb-" not in fuera and "--lxd-" not in fuera
    usados = set()
    for f in [p + ".html" for p in PAGES] + ["lx-info.js", "lx-upgrade.js", "dash-header.js", "lx-audit.js",
                                             "community.js", "gdpr-banner.js", "style.css"]:
        usados |= set(re.findall(r"var\((--lx[tbd]-[0-9a-z_]+),", _read(f)))
    definidos = set(re.findall(r"(--lx[tbd]-[0-9a-z_]+)\s*:", css))
    for f in PAGES:
        definidos |= set(re.findall(r"(--lx[tbd]-[0-9a-z_]+)\s*:", _read(f + ".html")))
    assert not (usados - definidos), sorted(usados - definidos)[:10]


def test_build_349_y_precache():
    sw = _read("sw.js")
    assert "BUILD_VERSION = '349'" in sw
    assert "/theme-light.css?v=349" in sw
