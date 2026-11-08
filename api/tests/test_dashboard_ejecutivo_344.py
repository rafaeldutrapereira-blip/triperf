"""DASHBOARD-EJECUTIVO (BUILD 344): tres bandas, guardian anti-eliminacion,
regla de siglas y sistema de tema global (oscuro por defecto + selector claro)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _r(name):
    return (ROOT / name).read_text(encoding="utf-8")


def _body(h):
    i = h.index("<body")
    return h[i:h.index("<script>", i)]


# Inventario del Paso 0: TODO id de bloque/KPI que existia antes de 344.
INVENTARIO_IDS = [
    # cabecera
    "date-lbl", "kl-greeting-txt", "kl-greeting-name", "garmin-sync-chip", "dhx-bell-btn",
    "dhx-bell-badge", "dhx-bell-panel", "dhx-bell-list", "btn-upgrade", "btn-upgrade-label",
    # primeros pasos
    "onb-card", "onb-count", "onb-list",
    # frase de hoy / carrera / que toca hoy
    "w13-phrase", "w13-dot", "w13-ball", "w13-phrase-label", "w13-phrase-text",
    "kc-race", "kc-race-content", "kc-race-next-lbl", "cd-d", "cd-unit", "kc-race-name",
    "kc-race-date", "kc-race-goal", "kc-race-year", "kc-race-empty",
    "w13-today", "w13-today-list",
    # insight
    "insight-card", "insight-readiness-pill", "insight-readiness-val", "insight-readiness-incomplete",
    "insight-severity", "insight-sev-word", "insight-headline", "insight-action",
    "insight-why-toggle", "insight-why-label", "insight-detail", "insight-message",
    "insight-drivers", "insight-technical", "insight-cta", "insight-cta-label",
    # carga
    "cluster-carga-pill", "spark-ctl", "badge-ctl-change", "spark-atl", "badge-atl",
    "spark-tsb", "tsb-val", "badge-tsb", "kc-acwr", "spark-acwr", "kc-acwr-val", "kc-acwr-badge",
    "kc-acwr-tip", "acwr-detail", "kc-acwr-swim", "kc-acwr-bike", "kc-acwr-run", "kc-acwr-gym",
    "kc-injury", "kc-injury-num", "kc-injury-badge",
    # hoy
    "cluster-hoy-pill", "hrv-7d-val", "spark-hrv", "badge-hrv", "kc-rhr", "rhr-7d-val", "spark-rhr",
    "kc-rhr-val", "badge-rhr", "kc-bb", "spark-bb", "kc-bb-val", "badge-bb", "kc-tr", "spark-tr",
    "kc-tr-val", "badge-tr", "lx-checkin", "lx-checkin-rows", "lx-checkin-save", "lx-checkin-msg",
    "kc-mental", "spark-mental", "kc-mental-val", "badge-mental", "spark-sleep", "w-sleep-val",
    "kc-nap", "w-nap-val", "spark-fatmusc", "w-fat-val",
    # esta semana / objetivo
    "cluster-objetivo-pill", "tss-week-meta", "spark-tss", "badge-tss", "kl-vo2-running-name",
    "spark-vo2-run", "kl-vo2max-val", "badge-vo2", "kl-vo2-cycling-name", "spark-vo2-bike",
    "kl-vo2max-cycling-val", "badge-vo2-cycling", "kc-ctlproj", "ctlproj-meta", "spark-ctlproj",
    "kc-ctlproj-val", "badge-ctlproj", "kc-goalrace", "goalrace-meta", "kc-goalrace-val",
    "badge-goalrace",
    # plan del coach
    "coach-plan-sec", "coach-plan-list",
]


def test_guardian_ningun_bloque_del_inventario_desaparece():
    body = _body(_r("dashboard.html"))
    faltan = [i for i in INVENTARIO_IDS if 'id="%s"' % i not in body]
    assert not faltan, faltan


def test_tres_bandas_con_titulos_i18n_en_orden_y_sin_details_cerrado():
    h = _r("dashboard.html")
    a = h.index('id="band-today"')
    b = h.index('id="band-load"')
    c = h.index('id="band-where"')
    assert a < b < c
    for key in ("dash_q_today", "dash_q_load", "dash_q_where"):
        assert 'data-i18n="%s"' % key in h
    # bandas 1-3 visibles al entrar: ningun <details> envuelve una banda entera
    for ini, fin in ((a, b), (b, c)):
        seg = h[ini:fin]
        assert '<details class="panel' not in seg
        assert '<details class="w13-fold"' not in seg
    # Insight en banda 1, grafico/tarjetas de carga en banda 2, carreras en banda 3
    assert a < h.index('id="insight-card"') < b
    assert b < h.index('id="kc-acwr"') < c
    assert b < h.index('id="w13-today"') < c
    assert b < h.index('id="coach-plan-sec"') < c
    assert c < h.index('id="kc-race"')
    assert c < h.index('id="kc-ctlproj"')
    # estado de hoy (HRV, sueno, check-in) en banda 1
    for ident in ("spark-hrv", "lx-checkin", "w-sleep-val", "w13-phrase"):
        assert a < h.index('id="%s"' % ident) < b, ident


def test_una_sola_clase_de_tarjeta_y_sin_colores_fuera_de_variables_en_el_bloque_nuevo():
    h = _r("dashboard.html")
    i = h.index("DASHBOARD EJECUTIVO (BUILD 344)")
    bloque = h[i:h.index("</style>", i)]
    assert "border-radius: 14px" in bloque
    assert "padding: 16px 18px" in bloque
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", bloque), "color hardcodeado en el bloque ejecutivo"
    assert not re.search(r"rgba?\(", bloque), "color hardcodeado en el bloque ejecutivo"
    assert "box-shadow: none" in bloque


def test_sin_siglas_solas_en_etiquetas_visibles():
    h = _r("dashboard.html")
    body = re.sub(r"<!--.*?-->", "", _body(h), flags=re.S)  # solo texto visible, sin comentarios
    prohibidos = [
        ">CTL — Fitness<", ">CTL<", ">ATL — Fatiga<", ">TSB — Forma<", ">ACWR — Carga<",
        ">HRV Score<", ">FC Reposo<", ">TSS total<", ">Readiness LabX<", "CTL Proyectado",
        ">VO2 Max Running<", ">VO2 Max Ciclismo<",
    ]
    for p in prohibidos:
        assert p not in body, p
    assert "'TSS ' + t.tss" not in h
    assert "'CTL ' + g.fitness" not in h
    # etiquetas estaticas corregidas
    for ok in ("Forma (CTL)", "Variabilidad cardíaca (HRV)", "Capacidad aeróbica · Trote (VO2 Max)"):
        assert ok in body, ok


def test_build_344_en_sw_y_sellos_de_la_capa_compartida():
    sw = _r("sw.js")
    import re
    assert re.search(r"var BUILD_VERSION = '(34[4-9]|3[5-9]\d|[4-9]\d\d)';", sw)
    for page in ("dashboard.html", "shell.html"):
        h = _r(page)
        assert "nav.css?v=8" in h and "nav.js?v=10" in h, page


# ---------------------------------------------------------------- tema global
def test_variables_de_tema_en_la_capa_compartida_para_ambos_temas():
    css = _r("theme-vars.css")
    assert re.search(r":root,\s*\[data-theme='dark'\]", css)
    assert "[data-theme='light']" in css
    dark = css[: css.index("[data-theme='light']")]
    light = css[css.index("[data-theme='light']"):]
    for var in ("--bg", "--card", "--border", "--text", "--muted", "--accent", "--line-fit"):
        assert var + ":" in dark, ("dark", var)
        assert var + ":" in light, ("light", var)
    # paleta del SPEC
    for hexv in ("#0c141d", "#131f2c", "#22344a", "#eef4fa", "#93a5b5", "#0e9f6e", "#7fb2e8"):
        assert hexv in dark, hexv
    for hexv in ("#f4f5f7", "#ffffff", "#e3e7ec", "#0a2540", "#5b6b7a", "#0e9f6e"):
        assert hexv in light, hexv


def test_tema_se_aplica_antes_del_primer_pintado_con_labx_theme():
    for page in ("dashboard.html", "shell.html"):
        h = _r(page)
        head = h[: h.index("</head>")]
        i = head.index('localStorage.getItem("labx_theme")')
        assert i < head.index("theme-vars.css") + 200  # script inline en <head>, junto al CSS de tema
        assert 'setAttribute("data-theme"' in head[i:i + 400]
        assert "<script src" not in head[i - 120:i]  # inline, no externo


def test_selector_de_tema_en_el_menu_compartido_con_i18n():
    nav = _r("nav.js")
    assert "window.LXTheme" in nav
    assert "'labx_theme'" in nav
    for k in ("theme_label", "theme_dark", "theme_light"):
        assert k in nav
    css = _r("nav.css")
    assert ".sb-theme" in css
    # el menu usa variables, no colores fijos de un solo tema
    assert "background: var(--sidebar-bg)" in css
    i18n = _r("i18n.js")
    for k in ("theme_label", "theme_dark", "theme_light"):
        assert i18n.count(k + ":") == 3, k


def test_dashboard_usa_variables_del_tema_en_sus_fondos_de_tarjeta():
    h = _r("dashboard.html")
    style = h[: h.index("</style>")]
    assert "linear-gradient(145deg, #08121e" not in style
    assert "background: var(--card)" in style
