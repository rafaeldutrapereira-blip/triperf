"""PERFIL-ORDEN (BUILD 351): Mi Perfil ordenado por secciones. Test guardian:
ningun id, ni handler onclick del HTML estatico desaparece; las secciones
nuevas existen en el orden pedido y la cabecera lee el estado real."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
H = (ROOT / "athlete_profile.html").read_text(encoding="utf-8")

IDS_BASE = ['addons-list', 'b-css', 'b-fcmax', 'b-ftp', 'b-run', 'b-vo2', 'b-wpkg', 'be-css', 'be-fcmax', 'be-ftp', 'be-peso', 'be-run', 'be-vo2', 'bench-edit', 'btn-2fa-off', 'btn-2fa-on', 'btn-garmin-admin-dis', 'btn-garmin-dis', 'btn-garmin-off-con', 'btn-garmin-switch', 'btn-garmin-sync', 'btn-save-profile', 'btn-strava-con', 'btn-strava-dis', 'btn-strava-sync', 'fc-zones-wrap', 'fold-rendimiento', 'garmin-admin-legacy', 'garmin-admin-legacy-tpl', 'garmin-badge', 'garmin-card', 'garmin-details', 'garmin-log', 'garmin-log-txt', 'garmin-migrate-banner', 'garmin-status', 'hist-btn-intervals', 'hist-btn-strava', 'hist-card', 'hist-intervals-desc', 'hist-link-intervals', 'hist-msg', 'hist-row-intervals', 'hist-row-strava', 'lx-theme-light', 'main-content', 'modal-2fa', 'myplan-summary', 'myplan-toggle', 'notif-push', 'notif-weekly', 'notif-workout', 'p-altura', 'p-edad', 'p-email', 'p-nombre', 'p-peso', 'p-sexo', 'pending-coach-invites-wrap', 'pf-avatar-img', 'pow-zones-wrap', 'priv-details', 'priv-hr', 'priv-pace', 'priv-power', 'priv-route', 'priv-saved-msg', 'priv-sub', 'prof-toast', 'profile-meter', 'pw-new', 'pw-old', 'qr-container', 'races-card', 'races-form', 'races-list', 'rc-cancel', 'rc-date', 'rc-dist', 'rc-form-title', 'rc-loc', 'rc-name', 'rc-prio', 'rc-save', 'run-zones-wrap', 'sb-overlay', 'sessions-list', 'sidebar', 'strava-badge', 'strava-details', 'strava-log', 'strava-log-txt', 'strava-unavailable', 'tab-conexiones', 'tab-perfil', 'tab-rendimiento', 'tab-seguridad', 'totp-code', 'twofa-badge', 'wearable-oauth-cards']
HANDLERS_BASE = ['acceptCoachInvite', 'buyAddon', 'changePassword', 'close2FAModal', 'deleteAccount', 'deleteAvatarPerfil', 'disable2FA', 'garminCardDisconnect', 'garminDisconnect', 'garminOfficialConnect', 'garminSync', 'gmigDismiss', 'histDismiss', 'histRunIntervals', 'histRunStrava', 'loadProfile', 'loadSessions', 'rejectCoachInvite', 'revokeAll', 'saveBenchmarks', 'savePrivacyPrefs', 'saveProfile', 'setup2FA', 'stravaConnect', 'stravaDisconnect', 'stravaSync', 'switchTab', 'toggleBenchEdit', 'toggleMyPlan', 'verify2FA', 'wearableConnect', 'wearableDisconnect', 'wearableSync']


def test_ningun_id_desaparece():
    faltan = [i for i in IDS_BASE if 'id="%s"' % i not in H]
    assert not faltan, faltan


def test_ningun_handler_onclick_desaparece():
    faltan = [f for f in HANDLERS_BASE if (f + "(") not in H]
    assert not faltan, faltan


def test_secciones_en_orden_y_en_su_pestana():
    orden = [H.index('id="sec-%s"' % s) for s in ("datos", "carreras", "conexiones", "seguridad")]
    assert orden == sorted(orden)
    assert H.index('id="sec-carreras"') < H.index('id="races-card"')
    pane_datos = H[H.index('id="tab-perfil"'):H.index('id="tab-conexiones"')]
    assert 'id="sec-datos"' in pane_datos and 'id="sec-carreras"' in pane_datos
    pane_cuenta = H[H.index('id="tab-seguridad"'):]
    assert 'id="sec-seguridad"' in pane_cuenta
    # invitaciones de coach viven en Seguridad y cuenta
    assert 'id="pending-coach-invites-wrap"' in pane_cuenta


def test_cabecera_e_indice():
    assert 'id="acct-glance"' in H and 'id="prof-index"' in H
    idx = H[H.index('id="prof-index"'):]
    idx = idx[:idx.index("</nav>")]
    for s in ("datos", "carreras", "conexiones", "seguridad"):
        assert "profSecGo('%s')" % s in idx
    # el estado sale de las mismas fuentes que las tarjetas
    fn = H[H.index("function accountGlanceConns"):H.index("function renderAccountGlance")]
    for src in ("_gModel.connected", "_stravaGlance", "_wearState", "_wearLast"):
        assert src in fn, src


def test_cabecera_se_repinta_con_cada_fuente():
    for hook in ("renderAccountGlance();",):
        assert H.count(hook) >= 6


def test_i18n_trilingue_y_build():
    i18n = (ROOT / "i18n.js").read_text(encoding="utf-8")
    for k in ("prof_glance_title", "prof_sec_datos", "prof_sec_carreras",
              "prof_sec_conexiones", "prof_sec_seguridad",
              "prof_glance_checking", "prof_glance_invites"):
        assert i18n.count(k + ":") == 3, k
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    assert int(re.search(r"var BUILD_VERSION = '(\d+)'", sw).group(1)) >= 351
