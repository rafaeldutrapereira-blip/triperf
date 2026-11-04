"""W4/D1: Mi Huella oculta en la web (routes.config); D1 la borro de la app."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_huella_html_se_conserva_en_la_web():
    assert (ROOT / "huella.html").exists()


def test_huella_no_existe_en_la_app():
    s = _read("athlete-app.html")
    for needle in ("loadProgressHuella", "renderProgressHuella",
                   "pgr-tab-huella", "pgr-huella-content", "yir-mob"):
        assert needle not in s, needle


def test_landing_sin_feature_9_huella():
    s = _read("landing.html")
    assert "lnd_feat9" not in s
    assert "huella" not in s.lower()


def test_sw_build_268():
    import re

    m = re.search(r"var BUILD_VERSION = '(\d+)';", _read("sw.js"))
    assert m and int(m.group(1)) >= 268
