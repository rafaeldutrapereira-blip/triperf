"""
athlete-app.html: Conexiones con Garmin y Strava desde el móvil.

Contrato estático (la página se ejecuta en el navegador; estos tests fijan
los endpoints que usa, el flag móvil de Strava, el retorno con ?strava= y que
cada clave i18n usada exista en los tres idiomas).
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "athlete-app.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")


def test_strava_connect_usa_flag_movil_y_redirect_manual():
    assert "apiFetch('/strava/connect?client=mobile', { redirect:'manual' })" in APP
    assert "window.location.href = API + '/strava/connect?client=mobile';" in APP


def test_strava_connect_muestra_boton_solo_si_no_esta_conectado():
    assert "onclick=\"stravaConnectMobile()\"" in APP
    assert "(sOn ? '' : '<div><button class=\"pf-conn-sync-btn\" onclick=\"stravaConnectMobile()\"" in APP


def test_garmin_guarda_con_mismo_endpoint_y_campos_de_la_web():
    assert "apiFetch('/athlete/garmin-credentials', { method:'POST', body: JSON.stringify({ garmin_email: email, garmin_password: pass }) })" in APP


def test_garmin_mfa_paso_dos_como_en_la_web():
    assert "if(res.d.needs_mfa){" in APP
    assert "apiFetch('/athlete/garmin/reauth/mfa', { method:'POST', body: JSON.stringify({ code: code }) })" in APP


def test_garmin_desconectar_usa_endpoint_existente():
    assert "apiFetch('/athlete/garmin-credentials', { method:'DELETE' })" in APP
    assert "onclick=\"pfGarminDisconnect()\"" in APP


def test_retorno_de_strava_muestra_toast_y_limpia_parametro():
    assert "function _handleStravaReturn(){" in APP
    for estado in ("connected", "denied", "error"):
        assert f"{estado}:" in APP
    assert "url.searchParams.delete('strava');" in APP
    assert "window.history.replaceState(" in APP


def test_retorno_de_strava_se_procesa_al_arrancar():
    boot = APP[APP.index("/* ── Boot"):]
    assert "_handleStravaReturn();" in boot
    assert boot.index("_handleStravaReturn();") < boot.index("initApp(tok);")


def test_backend_devuelve_a_athlete_app_con_el_parametro_strava():
    strava = (ROOT / "api" / "routes" / "strava_routes.py").read_text(encoding="utf-8")
    assert '"/athlete-app.html" if payload.get("app") == "mobile"' in strava


def test_claves_i18n_nuevas_existen_en_los_tres_idiomas():
    usadas = set(re.findall(r"_t\('(app_conn_[a-z_]+)'", APP))
    assert usadas, "no se encontraron claves app_conn_* en la página"
    for key in sorted(usadas):
        # Una definición por idioma (es, pt, en) dentro de DICT.
        n = len(re.findall(r"^\s*" + re.escape(key) + r":", I18N, re.M))
        assert n == 3, f"{key} aparece {n} veces en i18n.js (esperado 3: es/pt/en)"


def test_la_vista_de_solo_lectura_ya_no_queda():
    assert "hacelo desde la web en Mi Perfil" not in APP
