"""W13 — portada en tres piezas (Dashboard, Estado, Perfil)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def _squash(s):
    return re.sub(r"\s+", " ", s)


# ── Dashboard ────────────────────────────────────────────────────────────────
def test_dashboard_tres_piezas_en_orden():
    h = _read("dashboard.html")
    # DASHBOARD-EJECUTIVO (344): el orden ahora son tres bandas
    # (hoy: insight + frase; carga: que toca hoy; destino: carrera)
    i_insight = h.index('id="insight-card"')
    i_phrase = h.index('id="w13-phrase"')
    i_today = h.index('id="w13-today"')
    i_race = h.index('id="kc-race"')
    assert i_insight < i_phrase < i_today < i_race


def test_dashboard_frase_enlaza_a_estado_con_misma_fuente():
    h = _read("dashboard.html")
    assert 'id="w13-phrase" href="estado.html"' in h
    # misma fuente que estado.html: el veredicto unico lo decide el servidor (A2)
    assert "/athlete/estado-hoy?date_iso=" in h
    assert "r.sev > m.sev ? r : m" not in h


def test_dashboard_que_toca_hoy_lee_coach_y_mi_plan_propio():
    h = _read("dashboard.html")
    assert "¿Qué toca hoy?" in h
    assert "LXOwnPlan" in h          # CQ7: Mi Plan propio viene del servidor
    assert "/athlete/plan?start=" in h
    m = re.search(r"function ownToday\(\).*?\n        \}\n", h, re.S)
    assert m, "ownToday no encontrada"
    body = m.group(0)
    # Mi Plan propio = sin api_assignment_id (los del coach vienen del endpoint)
    assert "!x.api_assignment_id" in body
    assert "x.date_iso === diso" in body
    # el Mi Plan propio se pinta de inmediato, sin esperar al coach
    assert "renderToday(ownToday())" in h
    assert "mergeToday(coachToday(assigns), ownToday())" in h


def test_dashboard_cuenta_a_la_carrera_en_dias_sin_segundos():
    h = _read("dashboard.html")
    for dead in ('id="cd-s"', 'id="cd-m"', 'id="cd-h"', "dash_unit_sec", "dash_unit_hrs"):
        assert dead not in h, dead
    assert 'id="cd-d"' in h
    m = re.search(r"function tick\(\).*?setInterval\(tick, (\d+)\)", h, re.S)
    assert m
    assert int(m.group(1)) >= 60000   # ya no hay reloj por segundo
    assert "cd-s" not in m.group(0)


def test_dashboard_tarjetas_densas_ya_no_son_plegables_344():
    h = _read("dashboard.html")
    # 344: las bandas 1-3 se ven sin clics; ninguna tarjeta densa es un <details> cerrado
    assert 'class="panel sr kpi-card w13-row"' not in h
    for pill in ("cluster-carga-pill", "cluster-hoy-pill", "cluster-objetivo-pill"):
        assert pill in h


def test_dashboard_no_pierde_secciones():
    h = _read("dashboard.html")
    for keep in ("insight-card", "coach-plan-list", "acwr-detail", "kc-race-empty", "kc-race-name"):
        assert keep in h


# ── Estado ───────────────────────────────────────────────────────────────────
def test_estado_detalle_en_dos_grupos_de_maximo_cuatro_piezas():
    h = _read("estado.html")
    det = h[h.index('id="est-detail"'):]
    assert det.count('class="est-group-h"') == 2
    fis = det[det.index('class="fis-tabs-bar"'):]
    fis = fis[:fis.index('<span class="est-more-row" id="fis-more"')]
    visibles_fis = len(re.findall(r"<button", fis))
    assert visibles_fis <= 4
    men = det[det.index('class="men-tabs"'):]
    men = men[:men.index('<span class="est-more-row" id="men-more"')]
    assert len(re.findall(r"<button", men)) <= 4   # incluye el boton Mas
    # nada se borra: las 13 pestanas siguen
    assert len(re.findall(r"FIS\.switchTab\('", h)) >= 8
    assert len(re.findall(r"MEN\.switchTab\('", h)) >= 5
    for tab in ("wellness", "timeline", "correlations", "protocol"):
        assert "FIS.switchTab('%s', this)" % tab in h
    for tab in ("correlations", "prerace"):
        assert "MEN.switchTab('%s', this)" % tab in h


def test_estado_checkin_se_pliega_tras_guardar_y_conserva_9_campos():
    h = _read("estado.html")
    assert 'id="reg-fold"' in h
    assert "Check-in de hoy: hecho" in h
    m = re.search(r"function markDone\(\) \{.*?\n        \}", h, re.S)
    assert m
    assert "reg-fold').open = false" in m.group(0)
    # se llama tras guardar con exito
    sv = re.search(r"function save\(\).*?\n        \}\n", h, re.S).group(0)
    assert "markDone()" in sv
    campos = set(re.findall(r'data-reg-field="(\w+)"', h))
    assert campos == {"energy", "soreness", "sleep_quality", "stress", "mood",
                      "motivation", "anxiety", "focus", "confidence"}


def test_estado_veredicto_intacto():
    h = _read("estado.html")
    # A2: el veredicto viene del servidor; la regla de fusion ya no vive en la pagina
    assert "/athlete/estado-hoy?date_iso=" in h
    assert "r.sev > m.sev" not in h


# ── Perfil ───────────────────────────────────────────────────────────────────
def test_perfil_tiene_tres_pestanas():
    h = _read("athlete_profile.html")
    tabs = h[h.index('<div class="tabs">'):]
    tabs = tabs[:tabs.index("</div>")]
    assert tabs.count("tab-btn") == 3
    assert "switchTab('perfil')" in tabs
    assert "switchTab('conexiones')" in tabs
    assert "switchTab('seguridad')" in tabs
    assert len(re.findall(r'class="tab-pane', h)) == 3


def test_perfil_conserva_objetivo_sexo_y_medidor():
    h = _read("athlete_profile.html")
    for i in ("races-list", "rc-name", "rc-date", "rc-dist", "p-sexo", "profile-meter"):
        assert 'id="%s"' % i in h, i
    # ambos viven en la primera pestana (Mis datos)
    pane = h[h.index('id="tab-perfil"'):h.index('id="tab-conexiones"')]
    for i in ("races-list", "p-sexo"):
        assert 'id="%s"' % i in pane
    assert "PROFILE_FIELDS" in h and "profileCompleteness" in h


def test_perfil_plan_y_privacidad_salen_de_la_primera_pantalla():
    h = _read("athlete_profile.html")
    mis_datos = h[h.index('id="tab-perfil"'):h.index('id="tab-conexiones"')]
    assert 'id="addons-list"' not in mis_datos
    assert 'id="priv-details"' not in mis_datos
    cuenta = h[h.index('id="tab-seguridad"'):]
    assert 'id="addons-list"' in cuenta
    assert 'id="priv-details"' in cuenta


def test_perfil_rendimiento_plegado_y_sin_records_manuales():
    h = _read("athlete_profile.html")
    mis_datos = h[h.index('id="tab-perfil"'):h.index('id="tab-conexiones"')]
    assert 'id="fold-rendimiento"' in mis_datos
    # Sprint RECORDS: Rendimiento es la unica fuente de records
    assert 'id="fold-records"' not in h
    assert "personal-records" not in h
    assert 'id="be-ftp"' in mis_datos
    assert "profileGoto" in h


# ── Release ──────────────────────────────────────────────────────────────────
def test_sw_build_276_y_i18n_trilingue():
    sw = _read("sw.js")
    assert int(re.search(r"var BUILD_VERSION = '(\d+)'", sw).group(1)) >= 276
    i18n = _read("i18n.js")
    for key in ("dash_w13_today_q", "est_checkin_done", "prof_tab_mydata", "prof_tab_account"):
        assert i18n.count(key + ":") == 3, key
