"""CQ2: cero botones y cifras falsas visibles (H12, H16, H17, H22, H23)."""
import glob
import io
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _r(name):
    with io.open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def test_h12_sin_fakesync_ni_modal_garmin():
    html = _r("training_plan.html")
    for tok in ("fakeSync", "modal-garmin", "garmin-send-btn", "showGarminModal",
                "syncRescheduled", "sync_garmin_schedule", "btn_send_garmin"):
        assert tok not in html, tok


def test_h16_landing_tsb_coherente_y_rotulo_ilustrativo():
    html = _r("landing.html")
    assert ">-14<" in html and ">+14<" not in html
    assert 'data-i18n="lnd_mock_illustrative"' in html
    assert _r("i18n.js").count("lnd_mock_illustrative:") == 3


def test_h17_grafico_semanal_sin_semillas():
    html = _r("nutrition.html")
    fn = html[html.index("function renderWeeklyChart"):]
    fn = fn[:fn.index("// TABS")]
    assert "nutProfileReady()" in fn
    assert "a.calories" in fn
    assert "!usable" in fn
    marker = "else if (nutProfileReady())"
    assert "ATH." not in fn[:fn.index(marker)]
    assert "ATH." in fn[fn.index(marker):]


def test_h23_nav_sin_syncgarmin_y_sello_unico():
    nav = _r("nav.js")
    assert "syncGarmin" not in nav and "/personal/sync" not in nav
    stamps = set()
    for f in glob.glob(os.path.join(ROOT, "*.html")):
        stamps.update(re.findall(r"nav\.js\?v=(\d+)", _r(os.path.basename(f))))
    assert stamps == {"6"}


def test_h22_race_day_sin_readiness_score():
    html = _r("race_day.html")
    assert "readiness_score" not in html
    assert "var score = r.pacing_score;" in html
    assert "rd_chip_pacing_score" in html
