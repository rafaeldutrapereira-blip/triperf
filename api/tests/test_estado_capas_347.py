"""ESTADO-CAPAS (BUILD 347) — Estado en capas ejecutivas, sin eliminar bloques.

Nivel 1: titular (hero) + «lo que más pesa hoy». Nivel 2: tres bandas con
pregunta. Nivel 3: el detalle técnico completo, plegado por defecto.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "estado.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")

# Inventario del Paso 0: ids de estado.html en BUILD 346 (guardián anti-eliminación).
IDS_346 = """
est-detail est-detail-btn est-dial-ring est-dot est-fig-hrv est-fig-men est-fig-rec
est-fig-sleep est-governs est-grp-fis est-grp-men est-head est-hero est-label
est-modal-host est-rec est-reg est-reg-fis est-reg-men est-rule est-score-l est-score-n
fis-coach-view-content fis-corr-days-sel fis-corr-insights fis-corr-table fis-garmin-kpis
fis-hrv-bars fis-hrv-days-sel fis-hrv-insights fis-hrv-kpis fis-hrv-mini-chart
fis-hrv-zones fis-more fis-more-btn fis-protocol-content fis-rc-factors fis-rec-alerts
fis-rec-box-main fis-rec-priorities fis-sleep-bars fis-sleep-days-sel fis-sleep-debt-box
fis-sleep-kpis fis-sleep-mini fis-tab-coach fis-tab-coach-btn fis-tab-correlations
fis-tab-hrv fis-tab-overview fis-tab-protocol fis-tab-sleep fis-tab-timeline
fis-tab-wellness fis-tl-days-sel fis-tl-hrv fis-tl-recovery fis-tl-sleep fis-tl-windows
fis-wellness-history men-breath-arc men-breath-complete-msg men-breath-count
men-breath-cycles men-breath-phase men-breath-rating-stars men-breath-ring
men-breath-selector men-breath-start-btn men-breath-stop-btn men-corr-content
men-filter-cat men-filter-diff men-filter-dur men-filter-goal men-mfs-arc men-mfs-badge
men-mfs-completeness men-mfs-hero-card men-mfs-hero-content men-mfs-loader
men-mfs-no-data men-mfs-num men-mfs-rec men-mfs-signal men-modal-rating-stars men-more
men-more-btn men-prerace-content men-proto-grid men-proto-modal men-proto-modal-cat
men-proto-modal-desc men-proto-modal-steps men-proto-modal-title men-proto-saved-msg
men-tab-breathing men-tab-correlations men-tab-prerace men-tab-protocols men-tab-score
men-trend-bars reg-done reg-fold reg-fold-sum reg-form reg-l-anxiety reg-l-confidence
reg-l-energy reg-l-focus reg-l-mood reg-l-motivation reg-l-sleep_quality reg-l-soreness
reg-l-stress reg-msg reg-notes reg-save reg-sum-state sb-overlay sidebar
""".split()


def _ids(html):
    return set(re.findall(r'(?<![\w-])id="([^"]+)"', html))


def test_ningun_id_existente_desaparece():
    presentes = _ids(HTML)
    faltan = [i for i in IDS_346 if i not in presentes]
    assert not faltan, faltan


def test_ids_unicos():
    todos = re.findall(r'(?<![\w-])id="([^"]+)"', HTML)
    dup = {i for i in todos if todos.count(i) > 1}
    assert not dup, dup


def test_detalle_tecnico_plegado_por_defecto_y_contiene_todo():
    i = HTML.index('id="est-detail"')
    assert re.search(r'<section[^>]*id="est-detail" hidden', HTML)
    det = HTML[i:]
    # las 8 pestañas del físico y el detalle mental viven dentro de la capa 3
    for tab in ("overview", "hrv", "sleep", "wellness", "timeline", "correlations", "protocol", "coach"):
        assert 'id="fis-tab-%s"' % tab in det
    assert 'id="est-grp-fis"' in det and 'id="est-grp-men"' in det
    assert "FIS.switchTab('timeline', this)" in det
    # el botón de la capa 3 usa la clave nueva
    assert 'data-i18n="est_see_tech"' in HTML and "'est_hide_tech'" in HTML


def test_orden_de_capas():
    a = HTML.index('id="est-hero"')
    b = HTML.index('id="est-reg"')
    c = HTML.index('id="est-l2"')
    d = HTML.index('id="est-detail-btn"')
    e = HTML.index('id="est-detail"')
    assert a < b < c < d < e


def test_tres_bandas_con_titulo_literal():
    for k in ("est_q_sleep", "est_q_body", "est_q_week"):
        assert 'data-i18n="%s"' % k in HTML
    assert "¿Cómo dormí?" in HTML and "¿Cómo está mi cuerpo?" in HTML and "¿Cómo vengo?" in HTML


def test_nivel1_lo_que_mas_pesa():
    assert 'id="est-weighs-h"' in HTML and 'data-i18n="est_weighs"' in HTML
    assert "factors[a.key] - factors[b.key]" in HTML  # los más bajos primero


def test_tarjetas_usan_datos_reales_y_no_inventan_rangos():
    # HRV: contra la referencia personal que ya entrega el servidor
    assert "hrv.baseline_ms" in HTML and "hrv.last_night_ms" in HTML
    # FC en reposo: sin baseline -> sin estado (sev null), solo contexto de 7 días
    m = re.search(r"var rc = \{[^}]*sev: null", HTML)
    assert m
    # deuda de sueño y duración vienen de sleep/history y dashboard
    assert "sh.sleep_debt_7d_h" in HTML and "s.total_min" in HTML
    # datos de contexto: endpoints existentes
    for ep in ("/recovery/sleep/history?days=7", "/recovery/hrv/history?days=14",
               "/recovery/wellness/history?days=7", "/recovery/timeline?days=7"):
        assert ep in HTML
    # tarjeta sin datos se omite: la banda queda oculta si no hay tarjetas
    assert "b.hidden = !html" in HTML


def test_nombre_mas_sigla_via_lxterm():
    for term in ("hrv", "resting_hr", "fatiga_muscular"):
        assert "term('%s')" % term in HTML


def test_tema_claro_solo_variables():
    css = HTML[HTML.index("ESTADO-CAPAS (BUILD 347): nivel 1"):HTML.index("</style>")]
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", css), "colores fijos en las capas nuevas"
    assert not re.search(r"rgba?\(", css)
    # cuerpo >= 0.95rem en la capa 2
    for sel in (".est-card {", ".est-card-s {", ".est-card-x {"):
        blk = css[css.index(sel):]
        blk = blk[:blk.index("}")]
        assert re.search(r"font-size: (0\.9[5-9]|1[\.\d]*)rem", blk), sel


def test_i18n_es_pt_en_completo():
    claves = ["est_q_sleep", "est_q_body", "est_q_week", "est_weighs", "est_see_tech",
              "est_hide_tech", "est_s_good", "est_s_warn", "est_s_care", "est_c_night",
              "est_c_target", "est_c_debt", "est_c_deep", "est_c_quality", "est_c_vs_base",
              "est_c_avg7", "est_c_week7", "est_c_week_legend", "est_c_proto",
              "est_c_proto_open", "est_c_proto_all"]
    for k in claves:
        assert len(re.findall(r"^\s*%s:" % k, I18N, re.M)) == 3, k
    # todas las claves data-i18n nuevas existen
    for k in re.findall(r'data-i18n="(est_(?:q_|weighs|see_tech)\w*)"', HTML):
        assert k in claves


def test_build_347():
    m = re.search(r"var BUILD_VERSION = '(\d+)'", SW)
    assert m and int(m.group(1)) >= 347
