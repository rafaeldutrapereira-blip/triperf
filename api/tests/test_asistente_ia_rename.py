"""
B3 — "AI Coach" pasa a "Asistente IA" en la interfaz (ES/PT/EN).
"Coach" queda solo para el rol de entrenador.

Los textos legales (tos_*, priv_*) y de marketing (lnd_*) no se tocan aquí:
son decisión de producto/compliance y están pendientes.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
AI_HTML = (ROOT / "ai_coach.html").read_text(encoding="utf-8")
APP = (ROOT / "athlete-app.html").read_text(encoding="utf-8")
ROUTES = (ROOT / "routes.config.js").read_text(encoding="utf-8")

BLOCKS = {}
for lang in ("es", "pt", "en"):
    m = re.search(r"^  " + lang + r": \{", I18N, re.M)
    nxt = [x.start() for x in re.finditer(r"^  (es|pt|en): \{", I18N, re.M) if x.start() > m.start()]
    BLOCKS[lang] = I18N[m.start(): nxt[0] if nxt else len(I18N)]


def _value(lang, key):
    m = re.search(r"\b" + key + r": (['\"])((?:\\.|(?!\1).)*?)\1", BLOCKS[lang])
    assert m, f"{lang}.{key} no existe"
    return m.group(2)


def test_nav_y_boton_se_llaman_asistente_en_los_tres_idiomas():
    assert "Asistente" in _value("es", "nav_ai_coach")
    assert "Assistente" in _value("pt", "nav_ai_coach")
    assert "AI Assistant" == _value("en", "nav_ai_coach")
    for lang in ("es", "pt", "en"):
        assert "Coach" not in _value(lang, "nav_ai_coach")
        assert "Coach" not in _value(lang, "shell_ai_btn")


def test_chat_y_errores_no_mencionan_coach_ia():
    keys = ["shell_ai_welcome", "aico_chat_welcome", "aico_typing", "app_aic_welcome",
            "app_ai_typing", "app_plan_gate_aicoach", "err_ai_not_configured",
            "err_ai_timeout", "err_ai_internal_error"]
    for lang in ("es", "pt", "en"):
        for k in keys:
            v = _value(lang, k)
            assert "AI Coach" not in v and "Coach IA" not in v, f"{lang}.{k}: {v}"


def test_titulo_de_pagina_y_literales_de_la_app():
    assert "LabX — Asistente IA" in AI_HTML
    assert "AI Coach" not in APP.replace("/*", "").split("\n")[0]  # sin literales en código
    code_lines = [l for l in APP.split("\n") if not l.strip().startswith(("/*", "*", "//", "<!--"))]
    assert not any("AI Coach" in l or "Coach IA" in l for l in code_lines)


def test_label_del_modulo_en_routes_config():
    assert "label:   'Asistente IA'" in ROUTES
    assert "label:   'AI Coach'" not in ROUTES


def test_coach_es_solo_el_rol_entrenador():
    # El módulo Coach (rol entrenador) conserva su nombre; no se confunde con la IA.
    assert "label:   'Coach'" in ROUTES
    assert "roles:   ['coach','admin']" in ROUTES
