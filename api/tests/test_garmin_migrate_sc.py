"""S-C: banner de migracion a Garmin oficial (solo presentacion)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = (ROOT / "athlete_profile.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
KEYS = "gmig_text gmig_btn gmig_dismiss".split()


def test_i18n_claves_en_tres_idiomas():
    for k in KEYS:
        assert len(re.findall(rf"\b{k}:", I18N)) == 3, k


def test_banner_oculto_por_defecto_y_dentro_de_conexiones():
    ini = WEB.index('id="tab-conexiones"')
    pos = WEB.index('id="garmin-migrate-banner"')
    assert pos > ini
    assert 'style="display: none"' in WEB[pos : pos + 200]
    for fn in ("garminOfficialConnect()", "gmigDismiss()"):
        assert fn in WEB[pos : pos + 1500]


def test_banner_solo_en_conexiones():
    assert WEB.count("garmin-migrate-banner") >= 2  # html + gmigRender
    for other in ("athlete-app.html", "dashboard.html", "training_plan.html"):
        f = ROOT / other
        if f.exists():
            assert "garmin-migrate-banner" not in f.read_text(encoding="utf-8")


def test_no_se_tocan_rutas_oauth():
    src = (ROOT / "api" / "routes" / "garmin_official_routes.py")
    if src.exists():
        assert "/connect" in src.read_text(encoding="utf-8")


def test_sw_build_324():
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    m = re.search(r"BUILD_VERSION = '(\d+)'", sw)
    assert m and int(m.group(1)) >= 324
