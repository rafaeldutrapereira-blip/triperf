"""CQ11: un solo sello ?v= por JS compartido, igual en web y app."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {"workout-blocks.js": "4", "estado-checkin.js": "1"}
PAGES = ["athlete-app.html", "coach.html", "estado.html", "indoor_workout.html"]


def _refs(js):
    pat = re.compile(r'<script[^>]*src="/?' + re.escape(js) + r'(\?v=(\d+))?"')
    out = []
    for p in PAGES:
        for m in pat.finditer((ROOT / p).read_text(encoding="utf-8")):
            out.append((p, m.group(2)))
    return out


def test_single_seal_per_file():
    for js, v in EXPECTED.items():
        refs = _refs(js)
        assert refs, js
        assert {r[1] for r in refs} == {v}, (js, refs)


def test_sw_precache_matches_seal():
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    assert "'/estado-checkin.js?v=1'" in sw
    assert "'/estado-checkin.js'," not in sw
