"""W14 — paginas de nicho en lenguaje llano (Blood Labs, Adaptativos, Comunidad, Gear)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def _squash(s):
    return re.sub(r"\s+", " ", s)


# ── Blood Labs ───────────────────────────────────────────────────────────────
def test_blood_labs_abre_con_resumen_llano_y_alertas_antes_de_ver_todo():
    h = _read("blood_labs.html")
    i_plain = h.index('id="bl-plain"')
    i_alerts = h.index('id="alerts-container"')
    i_impact = h.index('id="clinical-summary"')
    i_all = h.index('<details class="bl-all')
    assert i_plain < i_alerts < i_impact < i_all
    # TRS, radar y tabla completa quedan dentro de "Ver todo"
    i_end = h.index("</details>", i_all)
    for marker in ('id="kpi-trs"', 'id="ch-radar"', 'id="bm-table-container"'):
        assert i_all < h.index(marker) < i_end


def test_blood_labs_resumen_cuenta_valores_reales():
    h = _squash(_read("blood_labs.html"))
    assert "function plainReviewCount(cur)" in h
    assert "ms[k].status === 'warning' || ms[k].status === 'critical'" in h
    assert ".replace('{n}', n)" in h
    assert "renderPlainSummary(cur);" in h
    i = _read("i18n.js")
    assert "Tienes {n} valores para revisar" in i


def test_blood_labs_descargo_fijo_y_visible():
    h = _read("blood_labs.html")
    # en el encabezado, fuera de pestanas y de <details>
    assert h.index('id="bl-disclaimer"') < h.index('class="tabs-bar"')
    assert "Esto no sustituye el consejo de tu médico." in h
    assert "Esto no sustituye el consejo de tu médico." in _read("i18n.js")


def test_blood_labs_registro_en_dos_pasos():
    h = _squash(_read("blood_labs.html"))
    assert 'onclick="reviewExam()"' in h
    assert 'id="import-review"' in h
    # Guardar solo vive en el paso 2
    i_review = h.index('id="import-review"')
    assert h.index('onclick="saveExam()"') > i_review
    assert "function backToLoad()" in h


def test_blood_labs_conserva_beta_y_gate_de_sexo_de_w11():
    h = _read("blood_labs.html")
    assert 'class="bl-beta"' in h
    assert 'id="sex-missing-banner"' in h
    assert "function sexMissing()" in h
    assert "if (sexMissing()) {" in h


# ── Adaptativos ──────────────────────────────────────────────────────────────
def test_adaptive_atleta_vista_unica_esta_semana():
    h = _squash(_read("adaptive.html"))
    # la clase de vista simple solo se pone fuera del embed del coach
    assert (
        "if (q.get('embed') !== '1' && q.get('view') !== 'coach') { "
        "document.documentElement.classList.add('lx-simple');"
    ) in h
    assert 'data-i18n="adp_title_simple"' in h
    assert ".lx-simple #sec-tabs .tabs-bar" in h
    for pane in ("compliance", "taper", "projections", "history", "coach"):
        assert f".lx-simple #tab-{pane}" in h
    # aceptar / rechazar siguen disponibles
    assert "acceptAllWeek()" in h


def test_adaptive_embed_del_coach_intacto():
    h = _squash(_read("adaptive.html"))
    coach = _squash(_read("coach.html"))
    assert 'data-src="adaptive.html?view=coach&amp;embed=1"' in coach
    assert 'id="tab-coach"' in h
    assert "get('view') === 'coach'" in h and "switchTab('coach')" in h
    assert "loadCoachQueue" in h
    # las reglas lx-embed originales siguen
    assert ".lx-embed #sidebar" in h
    # toda regla de la vista simple cuelga de .lx-simple (nunca afecta al embed)
    css = re.findall(r"([^{}]+)\{[^{}]*display: none !important", h)
    for sel in css:
        if "tab-" in sel or "sec-kpis" in sel:
            assert ".lx-simple" in sel


# ── Comunidad ────────────────────────────────────────────────────────────────
def test_community_leaderboard_dos_selectores():
    h = _read("community.html")
    a = h.index('id="leaderboard-panel"')
    b = h.index("<!-- Suggestions -->")
    block = h[a:b]
    assert len(re.findall(r"<select", block)) == 2
    assert 'id="lb-scope"' in block and 'id="lb-period"' in block
    # metrica y club quedan en su valor por defecto
    assert '<input type="hidden" id="lb-metric" value="tss"' in block
    assert '<input type="hidden" id="lb-club" value=""' in block


def test_community_sin_duplicacion_de_escritorio_y_feed_primero():
    h = _read("community.html")
    assert "cl-side-right" not in h.split("</style>")[-1]
    assert 'id="cl-mini-leaderboard"' not in h
    assert "loadSidebarLeaderboard();" not in h
    i_share = h.index('id="btn-share-toggle"')
    i_feed = h.index('id="feed-container"')
    assert i_share < i_feed
    # el formulario de publicar arranca plegado
    assert 'id="post-form-wrap" style="display: none"' in h
    assert "window.toggleShareForm" in h


# ── Gear ─────────────────────────────────────────────────────────────────────
def test_gear_bicicletas_basico_invitacion_no_403():
    h = _squash(_read("gear.html"))
    assert "s.plan === 'basic' || s.plan === 'basico'" in h
    assert 'id="bikes-upgrade"' in h
    assert ".lx-free #bikes-upgrade { display: block; }" in h
    assert ".lx-free #bikes-body { display: none; }" in h
    # el tab de Bicicletas ya no se oculta con display none
    assert ".lx-free [data-main='bikes']" not in h
    # Basico no llama al servidor; un 403 inesperado tambien cae a la invitacion
    m = re.search(r"function loadBikes\(\) \{(.*?)gearFetch\(", h)
    assert "classList.contains('lx-free')" in m.group(1) and "return;" in m.group(1)
    assert "e.status === 403" in h
    assert "err.status = r.status;" in h
    assert 'src="lx-upgrade.js"' in h


def test_gear_servidor_sigue_exigiendo_plan_para_bicicletas():
    # via elegida: invitacion en el cliente; el servidor no se toca
    src = _read("api/routes/gear_routes.py")
    assert '@router.get("/bikes", dependencies=_GEAR_FULL)' in src
    assert 'prefix="/gear"' in src


def test_i18n_claves_w14_en_tres_idiomas():
    i = _read("i18n.js")
    for k in ("bl_disclaimer", "bl_see_all", "bl_plain_n_many", "bl_review_exam",
              "adp_title_simple", "adp_simple_intro", "cmw_share_btn",
              "gear_bikes_upgrade_msg", "gear_bikes_upgrade_btn"):
        assert len(re.findall(rf"\b{k}:", i)) == 3, k
    assert "var BUILD_VERSION = '279';" in _read("sw.js")
