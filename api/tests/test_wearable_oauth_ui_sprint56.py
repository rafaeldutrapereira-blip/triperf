"""Sprint 56 paso 3: cableado estatico de las tarjetas Polar/Wahoo en Conexiones
(perfil web y app). Mismo enfoque que test_garmin_official_ui_cq9.py."""
import re
from pathlib import Path

import pytest

from api.tests.text_match import squash

ROOT = Path(__file__).resolve().parents[2]
FILES = {
    "web": (ROOT / "athlete_profile.html").read_text(encoding="utf-8"),
    "app": (ROOT / "athlete-app.html").read_text(encoding="utf-8"),
}
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
KEYS = [
    "on", "off", "soon", "err", "desc", "btn_connect", "btn_sync", "btn_disconnect",
    "dis_ok", "dis_err", "syncing", "syncing_initial", "res_saved", "res_skipped",
    "net_err", "conn_ok", "conn_denied", "conn_err",
]


def _wearable_js(src: str) -> str:
    """Solo el bloque JS de Polar/Wahoo (desde su cabecera hasta _wearConsumeReturn)."""
    start = src.index("Polar / Wahoo (Sprint 56 paso 3)")
    end = src.index("function _wearConsumeReturn(")
    end = src.index("\n      }\n", end)
    return src[start:end]


@pytest.mark.parametrize("name", ["web", "app"])
def test_consulta_providers_enabled(name):
    s = squash(FILES[name])
    assert squash("'/providers/enabled'") in s


@pytest.mark.parametrize("name", ["web", "app"])
def test_tarjetas_condicionadas_al_flag(name):
    s = squash(_wearable_js(FILES[name]))
    assert squash("var WEARABLE_OAUTH = ['polar', 'wahoo'];") in s
    # solo entran las marcas que vienen en true
    assert squash("d[p] === true") in s
    # ante error de red no se agregan tarjetas
    assert squash("box.innerHTML = '';") in s
    assert squash("return r.ok ? r.json() : null;") in s


@pytest.mark.parametrize("name", ["web", "app"])
def test_endpoints_por_provider(name):
    s = squash(_wearable_js(FILES[name]))
    assert squash("_lxTopNav(API + '/integrations/' + p + '/connect');") in s
    assert squash("'/integrations/' + p + '/status'") in s
    assert squash("'/integrations/' + p + '/sync'") in s
    assert squash("'/integrations/' + p + '/disconnect'") in s
    # sync y disconnect son POST
    assert s.count('"POST"') >= 2  # squash normaliza comillas


@pytest.mark.parametrize("name", ["web", "app"])
def test_retorno_oauth_dispara_sync_inicial(name):
    s = squash(_wearable_js(FILES[name]))
    assert squash("v === 'connected'") in s
    assert squash("wearableSync(p, 90, true)") in s
    for v in ("denied", "error", "error_state"):
        assert f"'{v}'" in _wearable_js(FILES[name])
    assert squash("'wearable_syncing_initial'") in s
    # el resultado real (saved / skipped_dup) se muestra tal cual
    assert "d.saved" in _wearable_js(FILES[name])
    assert "d.skipped_dup" in _wearable_js(FILES[name])


@pytest.mark.parametrize("name", ["web", "app"])
def test_sync_con_error_no_maquilla(name):
    js = _wearable_js(FILES[name])
    assert "d && d.error" in js
    assert "d.errors[0].message" in js


def test_web_hook_y_contenedor():
    web = FILES["web"]
    assert 'id="wearable-oauth-cards"' in web
    assert "loadWearableCards();" in web
    assert "wearableReadReturn();" in web


def test_app_hook_y_contenedor():
    app = FILES["app"]
    assert "id=\"wearable-oauth-cards\"" in app
    assert "loadWearableCards();" in app
    assert "wearableReadReturn();" in app


def test_garmin_y_strava_intactos():
    for src in FILES.values():
        assert "/integrations/garmin/status" in src
        assert "garminOfficialConnect" in src
    assert "stravaConnect()" in FILES["web"]
    assert "/strava/status" in FILES["app"]


def test_i18n_tres_idiomas():
    for k in KEYS:
        assert len(re.findall(rf"\bwearable_{k}:", I18N)) == 3, k


@pytest.mark.parametrize("name", ["web", "app"])
def test_fallbacks_sin_salud_ni_sueno(name):
    """El sync es solo de actividades: ni el JS ni los textos nuevos prometen
    salud/sueno. Acotado al bloque Polar/Wahoo y a las lineas de i18n wearable_*."""
    js = _wearable_js(FILES[name]).lower()
    for w in ("salud", "sueño", "sueno", "sleep", "health", "saúde", "sono"):
        assert w not in js, w


def test_i18n_wearable_sin_salud_ni_sueno():
    pairs = re.findall(r"wearable_\w+:\s*'([^']*)'", I18N)
    assert len(pairs) >= 3 * len(KEYS)
    for txt in pairs:
        low = txt.lower()
        for w in ("salud", "sueño", "sueno", "sleep", "health", "saúde", "sono"):
            assert w not in low, (w, txt)


def test_sw_build_incrementado():
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    m = re.search(r"BUILD_VERSION = '(\d+)'", sw)
    assert m and int(m.group(1)) >= 319
