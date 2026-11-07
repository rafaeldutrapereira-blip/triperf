"""S-B: paso 'Trae tu historial' en Conexiones (solo presentacion, sin migracion)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = (ROOT / "athlete_profile.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
KEYS = (
    "hist_title hist_why hist_intervals_desc hist_intervals_off hist_intervals_reconnect "
    "hist_btn_import hist_btn_connect_intervals hist_strava_desc hist_running hist_res_intervals "
    "hist_res_strava hist_res_errors hist_err hist_unavailable hist_btn_fresh"
).split()


def test_i18n_claves_en_tres_idiomas():
    for k in KEYS:
        assert len(re.findall(rf"\b{k}:", I18N)) == 3, k


def test_placeholders_coinciden_entre_idiomas():
    for k in ("hist_res_intervals", "hist_res_strava", "hist_res_errors"):
        found = re.findall(rf"{k}: '([^']*)'", I18N)
        assert len(found) == 3
        sets = {frozenset(re.findall(r"\{(\w)\}", f)) for f in found}
        assert len(sets) == 1, k


def test_tarjeta_oculta_por_defecto_y_dentro_de_conexiones():
    ini = WEB.index('id="tab-conexiones"')
    pos = WEB.index('id="hist-card"')
    assert pos > ini and 'id="hist-card" style="display: none"' in WEB
    for fn in ("histRunIntervals()", "histRunStrava()", "histDismiss()"):
        assert fn in WEB


def test_no_se_toca_backend():
    # el sprint no agrega rutas: las existentes siguen igual
    src = (ROOT / "api" / "routes" / "intervals_routes.py").read_text(encoding="utf-8")
    assert '@router.post("/backfill")' in src


def test_sw_build_323():
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    m = re.search(r"BUILD_VERSION = '(\d+)'", sw)
    assert m and int(m.group(1)) >= 323
