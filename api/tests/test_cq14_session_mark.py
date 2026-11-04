"""CQ14: la app marca sesiones como la web (check sobrio + palabra), sin caja verde."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "athlete-app.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")


def test_no_green_box_marker_for_done_sessions():
    assert "(done ? '✅'" not in APP
    assert 'wk-wo-status">✅' not in APP
    assert "rgba(16,185,129,.08)" not in APP
    assert "✅ Completado" not in APP


def test_sober_mark_helper_used():
    assert APP.count("_sessMark(") >= 4
    assert 'class="sess-done"' in APP
    assert "app_session_done" in APP


def test_localized_done_word_in_three_languages():
    for word in ("Hecha", "Feita", "Done"):
        assert f"app_session_done: '{word}'" in I18N


def test_neutral_greeting_before_load():
    assert 'data-i18n="app_greet_morning"' not in APP
    for word in ("Hola", "Olá", "Hello"):
        assert f"app_greet_neutral: '{word}'" in I18N
