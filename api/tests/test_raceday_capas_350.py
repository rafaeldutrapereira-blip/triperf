"""RACEDAY-CAPAS (BUILD 350) — Día de la prueba en capas ejecutivas, sin eliminar controles.

Nivel 1: cuenta regresiva + Tu plan de carrera (ritmos y combustible por hora del plan generado).
Nivel 2: el plan en palabras + detalle plegado. Nivel 3: Ajustes del generador (plegado).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "race_day.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")

# Inventario del Paso 0: ids de race_day.html en BUILD 349 (guardián anti-eliminación).
IDS_349 = """
btn-auto-plan btn-plan-advanced countdown-card dash-content dash-days dash-loader dash-plan-card
dash-plan-content dash-race-date dash-race-name history-list main-content nutrition-link
pacing-targets-plan plan-altitude plan-basis plan-conf-pct plan-confidence-row plan-ftp plan-gen-msg
plan-goal plan-goal-gap plan-goal-pred plan-goal-row plan-goal-val plan-gpx-bike plan-gpx-bike-info
plan-gpx-run plan-gpx-run-info plan-if-bike plan-if-bike-val plan-if-run plan-if-run-val
plan-method-badge plan-race-type plan-range plan-results plan-surface plan-sweat plan-temp plan-water
plan-weight plan-wind rd-advanced rd-empty rd-empty-cta rd-race-section res-analysis-box
res-analysis-content res-bike res-dnf res-dnf-reason res-feeling res-hr-run res-notes res-power res-run
res-run-pace res-saved-msg res-swim res-t1 res-t2 sb-overlay sidebar splits-table-plan tab-main tab-races
""".split()


def _ids():
    return re.findall(r'(?<![\w-])id="([^"]+)"', HTML)


def test_ningun_id_desaparece_y_son_unicos():
    ids = _ids()
    assert not [i for i in IDS_349 if i not in ids]
    assert not {i for i in ids if ids.count(i) > 1}


def test_generador_intacto():
    for h in ("generatePlan(false)", "generatePlan(true)", "function postAutoPlan(", "/races/auto-plan",
              "function buildAdvancedPayload(", "function renderPlanResults(", "syncPlanIFSliders();"):
        assert h in HTML, h


def test_orden_de_capas():
    a = HTML.index('id="rd-l1"')
    b = HTML.index('id="rd-l2"')
    c = HTML.index('id="rd-advanced"')
    assert a < b < c
    assert a < HTML.index('id="countdown-card"') < HTML.index('id="dash-plan-card"') < b
    assert a < HTML.index('id="btn-auto-plan"') < b
    assert a < HTML.index('id="rd-fuel"') < b
    # nivel 2: palabras + detalle plegado que contiene todo el detalle del plan
    assert b < HTML.index('id="rd-words"') < HTML.index('id="rd-plan-detail"') < c
    det = HTML[HTML.index('id="rd-plan-detail"'):c]
    for i in ("plan-results", "splits-table-plan", "pacing-targets-plan", "plan-basis", "nutrition-link",
              "plan-confidence-row", "plan-goal-row"):
        assert 'id="%s"' % i in det, i
    assert not re.search(r'<details[^>]*id="rd-plan-detail"[^>]* open', HTML)


def test_nivel3_plegado_con_toda_la_configuracion():
    m = re.search(r'<details[^>]*id="rd-advanced"[^>]*>', HTML)
    assert m and " open" not in m.group(0)
    adv = HTML[HTML.index('id="rd-advanced"'):HTML.index('id="tab-races"')]
    for i in ("plan-race-type", "plan-ftp", "plan-weight", "plan-sweat", "plan-if-bike", "plan-if-run",
              "plan-gpx-bike", "plan-gpx-run", "plan-wind", "plan-altitude", "plan-temp", "plan-surface",
              "plan-water", "plan-goal", "btn-plan-advanced"):
        assert 'id="%s"' % i in adv, i


def test_combustible_solo_con_plan_generado():
    # sale de la respuesta del generador (nutrition.strategy), nunca de cifras fijas
    i = HTML.index("function renderPlanFuel(")
    j = HTML.index("function renderPlanWords(")
    body = HTML[i:j]
    assert "(d.nutrition || {}).strategy" in body and "st.carb_g_h" in body
    assert "display = 'none'" in body
    assert 'id="rd-fuel" style="display: none"' in HTML
    assert "renderPlanFuel(d, splits);" in HTML and "renderPlanWords(d, splits," in HTML


def test_tema_y_tamano_en_capas_nuevas():
    css = HTML[HTML.index("RACEDAY-CAPAS (BUILD 350)"):HTML.index("</style>", HTML.index("RACEDAY-CAPAS (BUILD 350)"))]
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", css) and "rgb" not in css
    for sel in (".rd-fuel-title {", ".rd-fuel-v {", ".rd-fuel-l {", ".rd-word {", ".rd-words-note {", ".rd-detail-sum {"):
        blk = css[css.index(sel):]
        blk = blk[:blk.index("}")]
        assert re.search(r"font-size: (0\.9[5-9]|1[\.\d]*)rem", blk), sel


def test_i18n_es_pt_en_completo():
    claves = ["rd_l1_title", "rd_btn_gen_my", "rd_fuel_title", "rd_fuel_carb", "rd_fuel_fluid", "rd_fuel_na",
              "rd_l2_title", "rd_l2_detail", "rd_words_none", "rd_word_swim", "rd_word_t1", "rd_word_t2",
              "rd_word_bike_w", "rd_word_bike", "rd_word_run_p", "rd_word_run", "rd_word_total"]
    for k in claves:
        assert len(re.findall(r"(?<![\w])%s:" % k, I18N)) == 3, k
    usadas = set(re.findall(r'data-i18n="(rd_(?:l1|l2|words|btn_gen_my|fuel)\w*)"', HTML))
    assert usadas <= set(claves), usadas - set(claves)
    for k in ("rd_word_bike_w", "rd_word_run_p", "rd_word_total"):
        sets = [frozenset(re.findall(r"\{(\w+)\}", m)) for m in re.findall(r"%s: '([^']*)'" % k, I18N)]
        assert len(sets) == 3 and len(set(sets)) == 1, k
    # nombre + (sigla)
    assert "Carbohidratos (CHO)" in I18N and "Sodio (Na)" in I18N and "Transición 1 (T1)" in I18N


def test_build_350():
    m = re.search(r"var BUILD_VERSION = '(\d+)'", SW)
    assert m and int(m.group(1)) >= 350
