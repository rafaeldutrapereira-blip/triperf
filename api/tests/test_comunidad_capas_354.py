import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(n):
    return (ROOT / n).read_text(encoding="utf-8")


def test_comunidad_capas_nivel1_y_nivel2():
    js = _read("community.js")
    assert "myPlaceHtml" in js and 'data-lxc="place"' in js and 'data-lxc="level2"' in js
    for v in ("rankingView", "clubsView", "feedView", "challengeHtml"):
        assert v in js


def test_comunidad_cache_busting():
    assert "community.js?v=3" in _read("community.html")
    assert "/community.js?v=3" in _read("sw.js")


def test_build_354():
    m = re.search(r"BUILD_VERSION = '(\d+)'", _read("sw.js"))
    assert m and int(m.group(1)) >= 354
