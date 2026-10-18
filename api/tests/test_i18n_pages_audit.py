"""
Auditoria i18n de paginas (sesion 2026-10-18).

Dos garantias que test_i18n.py no cubre:
  1. Toda clave que una pagina usa en JS (_t('k', ...), i18n.t('k')) o en
     el DOM (data-i18n / -placeholder / -title) existe en ES, PT **y** EN.
     test_i18n.py solo mira data-i18n contra ES.
  2. Las paginas ya auditadas no vuelven a tener literales en espanol en
     llamadas que ven el usuario (alert / textContent / innerHTML con texto
     fijo). Se listan frases concretas, no heuristicas, para no generar
     falsos positivos.
"""
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

I18N_JS = REPO_ROOT / "i18n.js"
_LANGS = ("es", "pt", "en")

_DATA_KEY = re.compile(r'data-i18n(?:-placeholder|-title)?="([A-Za-z0-9_]+)"')
_CALL_KEY = re.compile(
    r"""(?:i18n\.t|\b_t|window\._t)\(\s*['"]([A-Za-z0-9_]+)['"]\s*(?=[,)])"""
)


def _dict_by_lang():
    """Carga DICT evaluando el bloque con node (mismo metodo que test_i18n.py)."""
    import subprocess

    js = (
        "const fs=require('fs');"
        "const src=fs.readFileSync(process.argv[1],'utf8');"
        "const m=src.match(/var DICT = \\{[\\s\\S]*?\\n\\};/);"
        "eval(m[0]);"
        "process.stdout.write(JSON.stringify(DICT));"
    )
    out = subprocess.run(
        ["node", "-e", js, str(I18N_JS)], capture_output=True, encoding="utf-8", check=True
    )
    return json.loads(out.stdout)


def _pages():
    return sorted(REPO_ROOT.glob("*.html"))


def test_every_key_used_by_pages_exists_in_all_languages():
    dicts = _dict_by_lang()
    missing = {}
    for page in _pages():
        text = page.read_text(encoding="utf-8", errors="ignore")
        used = set(_DATA_KEY.findall(text)) | set(_CALL_KEY.findall(text))
        for lang in _LANGS:
            gone = sorted(k for k in used if k not in dicts[lang])
            if gone:
                missing.setdefault(page.name, {})[lang] = gone
    assert not missing, (
        "Claves usadas por paginas que faltan en algun idioma "
        f"(se verian como clave cruda o fallback en espanol):\n{json.dumps(missing, indent=1, ensure_ascii=False)}"
    )


# Literales en espanol que ya no deben aparecer en las paginas auditadas.
# Cada entrada: (pagina, fragmento exacto que NO debe existir).
_FORBIDDEN_LITERALS = [
    # training_plan.html (2026-10-18)
    ("training_plan.html", "textContent = '+ Agregar Sesión'"),
    ("training_plan.html", "textContent = 'Editar Sesión'"),
    ("training_plan.html", "textContent = 'Guardar Sesión'"),
    ("training_plan.html", "textContent = 'Enviar a Garmin Connect'"),
    ("training_plan.html", "'Sin sesiones para los filtros seleccionados'</td>"),
    ("training_plan.html", "label:'Sesión'"),
    ("training_plan.html", "MONTHS_L[") ,
    ("training_plan.html", "DAYS_SHORT["),
    # gear.html (2026-10-18): codigos del backend se muestran traducidos
    ("gear.html", "s.shoe_type + '</div>'"),
    ("gear.html", "+ b.bike_type + '</div></div>'"),
    ("gear.html", "' ' + c.tracking_unit + '</div></div>'"),
    # reset-password.html (2026-10-18): errores con clave, sin ex.message ni literales
    ("reset-password.html", "msg.textContent = ex.message;"),
    ("reset-password.html", "msg.textContent='Las contraseñas no coinciden.'"),
    ("reset-password.html", '<div class="card-sub">Elige una'),
    # dashboard-alt.html (2026-10-18)
    ("dashboard-alt.html", "label: 'TSS Semana'"),
    ("dashboard-alt.html", "zoneLabel = 'Óptimo';"),
    ("dashboard-alt.html", "var DOW = ['Lun'"),
    # huella.html (2026-10-18)
    ("huella.html", "toLocaleString('es-CL')"),
    ("huella.html", "label:'Carga total'"),
    ("huella.html", "<div class=\"ctl-lbl\">Inicio del año"),
]


@pytest.mark.parametrize("page,fragment", _FORBIDDEN_LITERALS)
def test_audited_pages_have_no_hardcoded_spanish_literal(page, fragment):
    text = (REPO_ROOT / page).read_text(encoding="utf-8")
    assert fragment not in text, (
        f"{page} todavia contiene el literal en espanol {fragment!r}; "
        "debe pasar por _t('clave', 'fallback') o data-i18n."
    )


# Paginas ya auditadas: ningun caracter U+FFFD (mojibake) fuera de comentarios.
_MOJIBAKE_CLEAN_PAGES = [
    "training_plan.html", "gear.html", "reset-password.html", "dashboard-alt.html",
    "huella.html", "analytics.html", "year_in_review.html", "race_predictor.html",
]


@pytest.mark.parametrize("page", _MOJIBAKE_CLEAN_PAGES)
def test_audited_pages_have_no_mojibake_outside_comments(page):
    comment_start = re.compile(r"\s*(//|/\*|<!--|\*)")
    bad = [
        (i + 1, line.strip()[:100])
        for i, line in enumerate((REPO_ROOT / page).read_text(encoding="utf-8").split("\n"))
        if "�" in line and not comment_start.match(line)
    ]
    assert not bad, f"{page} tiene U+FFFD (mojibake) en codigo visible: {bad}"
