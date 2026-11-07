"""S-D: 'Ver detalles' por conexion (solo presentacion)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = (ROOT / "athlete_profile.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
KEYS = (
    "cdet_toggle cdet_status cdet_recv cdet_send cdet_none cdet_last cdet_never "
    "cdet_last_failed cdet_sync_now cdet_reconnect cdet_item_activities "
    "cdet_item_sleep cdet_item_daily cdet_item_workouts"
).split()


def test_i18n_claves_en_tres_idiomas():
    for k in KEYS:
        assert len(re.findall(rf"\b{k}:", I18N)) == 3, k


def test_contenedores_en_las_tarjetas():
    ini = WEB.index('id="tab-conexiones"')
    assert WEB.index('id="garmin-details"') > ini
    assert WEB.index('id="strava-details"') > ini
    assert "connDetailsHtml(" in WEB[WEB.index("function _wearCardHtml") :]


def test_no_hay_endpoints_de_sync_nuevos():
    # Solo se reusan acciones existentes
    for fn in ("garminSync()", "wearableSync(", "stravaSync()"):
        assert fn in WEB


def test_indoor_intacto():
    assert "connDetailsHtml" not in (ROOT / "indoor_workout.html").read_text(encoding="utf-8")


def test_sw_build_325():
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    m = re.search(r"BUILD_VERSION = '(\d+)'", sw)
    assert m and int(m.group(1)) >= 325
