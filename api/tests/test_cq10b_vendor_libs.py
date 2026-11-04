"""CQ10b/D3: Leaflet y Chart.js vendorizados para la app (athlete-app.html)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEAFLET = "vendor/leaflet"  # CQ15: ruta simple, sin carpeta doble
FILES = [
    f"{LEAFLET}/leaflet.css",
    f"{LEAFLET}/leaflet.js",
    f"{LEAFLET}/images/layers.png",
    f"{LEAFLET}/images/layers-2x.png",
    f"{LEAFLET}/images/marker-icon.png",
    f"{LEAFLET}/images/marker-icon-2x.png",
    f"{LEAFLET}/images/marker-shadow.png",
    "vendor/chart.umd.min.js",
]


def test_vendor_files_exist():
    for rel in FILES:
        assert (ROOT / rel).is_file(), rel


def test_no_double_leaflet_path():
    assert not (ROOT / "vendor/leaflet/leaflet").exists()
    for name in ("athlete-app.html", "sw.js"):
        assert "leaflet/leaflet/" not in (ROOT / name).read_text(encoding="utf-8"), name


def test_referenced_vendor_files_exist_on_disk():
    html = (ROOT / "athlete-app.html").read_text(encoding="utf-8")
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    refs = set(re.findall(r"""(?:href|src)=["'](vendor/[^"'?#]+)""", html))
    refs |= {m.lstrip("/") for m in re.findall(r"'(/vendor/[^']+)'", sw)}
    assert refs
    for rel in refs:
        assert (ROOT / rel).is_file(), rel


def test_app_has_no_cdn_for_leaflet_or_chartjs():
    html = (ROOT / "athlete-app.html").read_text(encoding="utf-8")
    assert not re.search(r"unpkg\.com|cdn\.jsdelivr\.net", html)
    for rel in (f"{LEAFLET}/leaflet.css", f"{LEAFLET}/leaflet.js", "vendor/chart.umd.min.js"):
        assert rel in html


def test_sw_precaches_vendor_files():
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    for rel in FILES:
        assert f"'/{rel}'" in sw, rel


def test_build_www_copies_vendor(tmp_path, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_www", ROOT / "scripts" / "build_www.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "WWW", tmp_path / "www")
    mod.build()
    for rel in FILES:
        assert (tmp_path / "www" / rel).is_file(), rel
