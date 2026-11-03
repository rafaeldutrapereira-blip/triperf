"""W4: Mi Huella oculta para todos; codigo conservado."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_huella_html_y_endpoints_se_conservan():
    assert (ROOT / "huella.html").exists()
    assert "loadProgressHuella" in _read("athlete-app.html")


def test_app_pestana_huella_condicionada_a_canaccess():
    s = _read("athlete-app.html")
    assert "{ el: 'pgr-tab-huella', mod: 'huella' }" in s
    assert "canAccess({ api_rol: 'atleta', plan: 'elite' }, 'huella')" in s


def test_landing_sin_feature_9_huella():
    s = _read("landing.html")
    assert "lnd_feat9" not in s
    assert "huella" not in s.lower()


def test_sw_build_268():
    assert "var BUILD_VERSION = '268';" in _read("sw.js")
