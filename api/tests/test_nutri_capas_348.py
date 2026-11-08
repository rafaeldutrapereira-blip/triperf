"""NUTRI-CAPAS (BUILD 348) — Nutrición en capas ejecutivas, sin eliminar controles.

Nivel 1: titular + 3 tarjetas por hora. Nivel 2: plan por tramos en palabras,
Antes/Después y ajustes rápidos. Nivel 3: ajuste fino, datos del atleta, tabla,
gráficos e imprimir (plegado). «Mi semana» queda como banda final.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "nutrition.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")

# Inventario del Paso 0: ids de nutrition.html en BUILD 347 (guardián anti-eliminación).
IDS_347 = """
ca-css ca-ftp ca-run ca-weight cfg-ath-info ch-cho-fluid ch-pie ch-weekly gantt-wrap guide-text
if-alt-slider if-alt-val if-badge if-bike-slider if-bike-val if-elev-bike-slider if-elev-bike-val
if-elev-run-slider if-elev-run-val if-fine if-heat-quick if-panel if-precision-badge if-quick
if-run-slider if-run-val if-surface if-temp-slider if-temp-val if-terrain-quick if-toggle-btn
if-wind-slider if-wind-val kpi-cho kpi-cho-hr kpi-cho-s kpi-fluid kpi-fluid-hr kpi-fluid-s kpi-grid
kpi-kcal kpi-kcal-s kpi-more kpi-more-grid kpi-na kpi-na-s kpi-ratio kpi-ratio-s kpi-time plan-table
plan-tbody post-kpi-strip post-race-content pre-race-content race-src-card-host sb-overlay
sec-my-week sel-sweat sidebar splits-list tab-plan tab-post tab-pre tab-res tot-strip
weekly-chart-wrap weekly-empty weekly-sync-info
""".split()

# Controles (handlers) que deben seguir vivos.
HANDLERS = [
    "setRace('sprint', this)", "setRace('olympic', this)", "setRace('703', this)",
    "setRace('ironman', this)", "switchTab('res', this)", "switchTab('plan', this)",
    "switchTab('pre', this)", "switchTab('post', this)", "toggleIFPanel()", "resetIF()",
    "resetCourse()", "onQuickCourse()", "onIFChange()", "onCourseChange()", "nutCalc()",
    "window.print()",
]


def _static():
    """HTML estático (antes del primer <script> de datos)."""
    return HTML[:HTML.index('<script src="https://cdn.jsdelivr.net/npm/chart.js')]


def _ids(html):
    return set(re.findall(r'(?<![\w-])id="([^"]+)"', html))


def test_ningun_id_existente_desaparece():
    faltan = [i for i in IDS_347 if i not in _ids(_static())]
    assert not faltan, faltan


def test_ids_unicos():
    todos = re.findall(r'(?<![\w-])id="([^"]+)"', _static())
    dup = {i for i in todos if todos.count(i) > 1}
    assert not dup, dup


def test_controles_siguen_vivos():
    for h in HANDLERS:
        assert h in HTML, h
    for i in ("if-bike-slider", "if-run-slider", "if-elev-bike-slider", "if-elev-run-slider",
              "if-wind-slider", "if-alt-slider", "if-temp-slider", "if-surface", "sel-sweat"):
        assert 'id="%s"' % i in _static(), i


def test_orden_de_capas():
    s = _static()
    a = s.index('id="nut-l1"')
    b = s.index('id="nut-l2"')
    c = s.index('id="nut-detail-btn"')
    d = s.index('id="nut-detail"')
    e = s.index('id="sec-my-week"')
    assert a < b < c < d < e
    # el motor y el detalle: host de la carrera dentro del nivel 1
    assert a < s.index('id="race-src-card-host"') < b
    # chips de distancia en nivel 1, tarjetas por hora
    assert a < s.index("setRace('sprint', this)") < b
    for i in ("nut-headline", "nut-v-cho", "nut-v-fluid", "nut-v-na"):
        assert a < s.index('id="%s"' % i) < b, i


def test_detalle_plegado_y_contiene_todo():
    s = _static()
    assert re.search(r'<section[^>]*id="nut-detail" hidden', s)
    det = s[s.index('id="nut-detail"'):s.index('id="sec-my-week"')]
    for i in ("if-fine", "if-panel", "cfg-ath-info", "ca-ftp", "ca-weight", "if-toggle-btn",
              "kpi-grid", "kpi-more", "tab-res", "tab-plan", "tab-pre", "tab-post",
              "plan-table", "plan-tbody", "tot-strip", "ch-pie", "ch-cho-fluid",
              "gantt-wrap", "sel-sweat", "if-surface", "if-precision-badge"):
        assert 'id="%s"' % i in det, i
    assert "window.print()" in det
    # el ajuste fino sigue plegado dentro del nivel 3
    m = re.search(r'<details[^>]*id="if-fine"[^>]*>', det)
    assert m and " open" not in m.group(0).replace("onchange", "")


def test_ajustes_rapidos_visibles_en_nivel_2():
    s = _static()
    l2 = s[s.index('id="nut-l2"'):s.index('id="nut-detail-btn"')]
    assert 'id="if-terrain-quick"' in l2 and 'id="if-heat-quick"' in l2
    assert 'id="if-fine"' not in l2
    for k in ("nut_q_legs", "nut_q_ba", "nut_q_quick"):
        assert 'data-i18n="%s"' % k in l2
    assert "¿Qué tomo en cada tramo?" in l2 and "Antes y después" in l2
    assert 'id="nut-legs"' in l2 and 'id="nut-pre-sum"' in l2 and 'id="nut-post-sum"' in l2


def test_mi_semana_banda_final_sin_cambio_de_datos():
    s = _static()
    assert s.index('id="sec-my-week"') > s.index('id="nut-detail"')
    assert 'id="ch-weekly"' in s and "renderWeeklyChart();" in HTML


def test_nivel1_lee_de_las_mismas_fuentes_que_la_grilla():
    # los datos del nivel 1 se pintan desde updateKpis, con los mismos argumentos que kpi-*
    i = HTML.index("function updateKpis(")
    j = HTML.index("function aggPlanByDisc(")
    body = HTML[i:j]
    assert "nutPaintL1(time, choTot, choHr, flTot, flHr, naTot, naHr)" in body
    assert "getElementById('kpi-cho-hr').textContent = choHr" in body
    assert "getElementById('nut-v-cho').textContent = choHr" in body
    assert "getElementById('nut-v-fluid').textContent = flHr" in body
    assert "getElementById('nut-v-na').textContent =" in body and "naHr" in body
    # el motor no se tocó: sigue el mismo cálculo y el mismo endpoint
    assert "computeNutritionTargets(rk, totalH, sweatMl, heatF)" in HTML
    assert "precise-splits" in HTML and "nutProfileReady" in HTML


def test_tramos_salen_del_plan_del_motor():
    i = HTML.index("function nutPaintL2(")
    j = HTML.index("function nutPostTargets(")
    body = HTML[i:j]
    assert "aggPlanByDisc(plan)" in body and "buildPreRace(" in body
    assert "nutPostTargets(ATH.weight, t.flTot)" in body
    # Post-Carrera usa el mismo helper (misma cifra en resumen y detalle)
    k = HTML.index("function renderTab4(")
    assert "nutPostTargets(weight, flTot)" in HTML[k:k + 400]


def test_distancia_por_defecto_es_la_proxima_carrera():
    assert "function nutApplyRaceDistance(" in HTML
    assert "/races?limit=100" in HTML and "d.race_id" in HTML
    assert "full: 'ironman'" in HTML
    # si el atleta ya eligió, no se pisa
    assert "ST.picked" in HTML and "setRace(rk, b, true)" in HTML


def test_chips_de_distancia_solo_los_cuatro():
    chips = re.findall(r"setRace\('(\w+)', this\)", HTML)
    assert sorted(chips) == ["703", "ironman", "olympic", "sprint"]


def test_nombre_mas_sigla_via_lxinfo():
    s = _static()
    assert 'data-lx-info="nutricion_cho"' in s and 'data-lx-info="nutricion_sodio"' in s
    # no mezclar data-lx-info con data-lx-term en el mismo nodo (dos íconos ℹ)
    for tag in re.findall(r"<[^>]*data-lx-info=[^>]*>", s):
        assert "data-lx-term" not in tag


def test_tema_claro_solo_variables_en_capas_nuevas():
    css = HTML[HTML.index("NUTRI-CAPAS (BUILD 348): nivel 1"):HTML.index("</style>")]
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", css), "colores fijos en las capas nuevas"
    assert not re.search(r"rgba?\(", css)
    # cuerpo >= 0.95rem en niveles 1-2
    for sel in (".nut-card {", ".nut-card-t {", ".nut-card-x {", ".nut-leg {", ".nut-list {",
                ".nut-sub {", ".nut-link {"):
        blk = css[css.index(sel):]
        blk = blk[:blk.index("}")]
        assert re.search(r"font-size: (0\.9[5-9]|1[\.\d]*)rem", blk), sel
    # la barra fija oscura y el encabezado con degradado fijo ya no envuelven la página
    assert 'class="cfg-bar"' not in _static() and 'class="ph"' not in _static()


def test_i18n_es_pt_en_completo():
    claves = ["nut_l1_distance", "nut_l1_na", "nut_q_legs", "nut_q_ba", "nut_q_quick",
              "nut_q_quick_s", "nut_see_detail", "nut_see_tech", "nut_hide_tech", "nut_h1",
              "nut_sub_time", "nut_sub_src", "nut_x_cho", "nut_x_fluid", "nut_x_na",
              "nut_x_total_g", "nut_x_total_l", "nut_x_total_mg", "nut_leg_none_swim",
              "nut_leg_none", "nut_leg_txt", "nut_post_s1", "nut_post_s2",
              "nut_post_s3"]
    for k in claves:
        assert len(re.findall(r"^\s*%s:" % k, I18N, re.M)) == 3, k
    # toda clave data-i18n o _t() nueva existe
    usadas = set(re.findall(r'data-i18n="(nut_(?:l1|q|see|hide)\w*)"', HTML))
    assert usadas <= set(claves) | {"nut_see_tech"}, usadas - set(claves)
    # los marcadores de plantilla coinciden entre idiomas
    for k in ("nut_h1", "nut_leg_txt", "nut_post_s1"):
        sets = [frozenset(re.findall(r"\{(\w+)\}", m)) for m in
                re.findall(r"^\s*%s: '(.*)',$" % k, I18N, re.M)]
        assert len(set(sets)) == 1, k


def test_imprimir_abre_el_detalle():
    assert "beforeprint" in HTML and "afterprint" in HTML


def test_build_348():
    m = re.search(r"var BUILD_VERSION = '(\d+)'", SW)
    assert m and int(m.group(1)) >= 348
