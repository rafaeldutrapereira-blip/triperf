"""
Terminología: el módulo se llama "Asistente IA" (ES), "Assistente IA" (PT) y
"AI Assistant" (EN). Ninguna frase antigua ("AI Coach", "Coach IA") puede quedar
en texto visible para el usuario: valores i18n, HTML y JS de la interfaz, y
cadenas de código que llegan a la API o a los correos.

Los comentarios, docstrings, logs, nombres de claves/rutas/variables y la
documentación interna no cuentan.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAT = re.compile(r"AI Coach|AI COACH|AI coach|Coach IA|Coach de IA")

VISIBLE_FILES = [
    "i18n.js", "landing.html", "privacy.html", "tos.html", "registro.html", "dashboard.html",
    "lx-upgrade.js", "lx-info.js", "nav.js", "athlete-app.html", "ai_coach.html",
]
PY_VISIBLE = [
    "api/coach_main.py", "api/mailer.py", "api/scheduler.py", "api/routes/ai_routes.py",
]


def _visible_lines(text: str):
    for n, line in enumerate(text.split("\n"), 1):
        st = line.strip()
        if st.startswith(("/*", "//", "<!--", "*")):
            continue
        yield n, line


def test_no_quedan_menciones_visibles_en_frontend():
    bad = []
    for f in VISIBLE_FILES:
        text = (ROOT / f).read_text(encoding="utf-8")
        for n, line in _visible_lines(text):
            if PAT.search(line):
                bad.append(f"{f}:{n}")
    assert not bad, bad


def test_no_quedan_menciones_visibles_en_codigo_de_api_y_correos():
    bad = []
    for f in PY_VISIBLE:
        text = (ROOT / f).read_text(encoding="utf-8")
        for n, line in enumerate(text.split("\n"), 1):
            if line.strip().startswith("#") or "logger." in line:
                continue
            # Solo cadenas de código (con comillas): docstrings y comentarios son internos.
            if PAT.search(line) and ('"' in line or "'" in line):
                bad.append(f"{f}:{n}")
    assert not bad, bad


def test_claves_i18n_conservan_su_nombre():
    # Las claves internas no cambian de nombre: solo sus valores visibles.
    text = (ROOT / "i18n.js").read_text(encoding="utf-8")
    for k in ("nav_ai_coach", "app_aicoach_title", "shell_ai_btn", "app_menu_aicoach"):
        assert len(re.findall(r"\b" + k + r":", text)) == 3, k
