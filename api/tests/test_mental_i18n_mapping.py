"""
Regresión del mapeo i18n de mental.html.

El backend (mental_routes.py) devuelve textos en español que el frontend
traduce por coincidencia exacta (_MSG_KEYS) y los protocolos se traducen
por id (mp_<id>_n/_d/_s). Si el backend cambia una frase sin actualizar
el mapeo, el frontend vuelve al español EN SILENCIO. Este test falla en
ese caso.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

from api.routes.mental_routes import PROTOCOL_LIBRARY

REPO = Path(__file__).resolve().parents[2]
MENTAL_ROUTES = REPO / "api" / "routes" / "mental_routes.py"
MENTAL_HTML = REPO / "mental.html"
I18N_JS = REPO / "i18n.js"

BACKEND_MESSAGES = {
    "Estado mental óptimo. Excelente día para entrenamiento de calidad o competencia.": "mentmsg_mfs_peak",
    "Buen estado mental. Entrena con confianza.": "mentmsg_mfs_good",
    "Fatiga mental moderada. Considera reducir la intensidad o acortar la sesión.": "mentmsg_mfs_moderate",
    "Fatiga mental alta. Prioriza descanso mental — un entrenamiento suave o día de recuperación.": "mentmsg_mfs_low",
    "Fatiga mental crítica. El rendimiento y la toma de decisiones están comprometidos. Descansa.": "mentmsg_mfs_critical",
    "Completa el check-in para obtener tu Mental Fatigue Score.": "mentmsg_need_checkin",
    "Completa el check-in diario para calcular tu Mental Fatigue Score.": "mentmsg_need_checkin_daily",
    "Mayor Mental Fatigue Score se correlaciona positivamente con mayor TSS alcanzado.": "mentmsg_corr_pos",
    "Sin correlación significativa todavía — necesitas más datos (mín. 14 días).": "mentmsg_corr_none",
    "Sin carrera objetivo registrada. Agrega tu próxima carrera en Perfil.": "mentmsg_no_race",
    "Es el día de carrera. Confía en tu preparación. 🏁": "mentmsg_race_day",
    "Tu carrera": "ment_your_race",
}

PRERACE_DAYS_TEMPLATE = "A {days_to_race} días de la carrera. Sigue el protocolo mental del día."
PRERACE_DAYS_KEY = "mentmsg_prerace_days"


def _load_dict():
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


def _load_js_message_map():
    html = MENTAL_HTML.read_text(encoding="utf-8")
    block = re.search(r"var _MSG_KEYS = \{(.*?)\n\};", html, re.S).group(1)
    return {
        k.replace("\\'", "'"): v
        for k, v in re.findall(r"'((?:[^'\\]|\\.)*)':\s*'(\w+)'", block)
    }


@pytest.fixture(scope="module")
def dicts():
    return _load_dict()


@pytest.fixture(scope="module")
def js_map():
    return _load_js_message_map()


@pytest.fixture(scope="module")
def backend_src():
    return MENTAL_ROUTES.read_text(encoding="utf-8")


def test_backend_messages_still_exist_in_source(backend_src):
    missing = [t for t in BACKEND_MESSAGES if t not in backend_src]
    assert not missing, (
        "Frases del backend cambiaron o desaparecieron. Actualiza BACKEND_MESSAGES "
        "y el mapeo _MSG_KEYS de mental.html y las claves mentmsg_* en i18n.js: "
        f"{missing}"
    )


def test_js_mapping_covers_every_backend_message(js_map):
    for text, key in BACKEND_MESSAGES.items():
        assert js_map.get(text) == key, (
            f"Falta o está desalineado en _MSG_KEYS de mental.html: {text!r} -> {key}"
        )


def test_js_mapping_has_no_stale_entries(js_map):
    stale = [t for t in js_map if t not in BACKEND_MESSAGES]
    assert not stale, f"_MSG_KEYS tiene entradas que el backend ya no emite: {stale}"


@pytest.mark.parametrize("lang", ["es", "pt", "en"])
def test_message_keys_exist_in_every_language(dicts, lang):
    for text, key in BACKEND_MESSAGES.items():
        assert dicts[lang].get(key), f"Clave {key} sin traducción en {lang}"


def test_es_message_values_match_backend_text(dicts):
    for text, key in BACKEND_MESSAGES.items():
        assert dicts["es"][key] == text, (
            f"ES de {key} no coincide con el backend: {dicts['es'][key]!r} != {text!r}"
        )


def test_prerace_days_template_matches_backend(backend_src, dicts):
    assert 'f"A {days_to_race} días de la carrera. Sigue el protocolo mental del día."' in backend_src, (
        "La frase de pre-carrera con días cambió en el backend"
    )
    assert dicts["es"][PRERACE_DAYS_KEY] == PRERACE_DAYS_TEMPLATE.replace("{days_to_race}", "{n}")
    for lang in ("pt", "en"):
        assert "{n}" in dicts[lang][PRERACE_DAYS_KEY], f"{lang} sin placeholder {{n}}"


@pytest.mark.parametrize("protocol", PROTOCOL_LIBRARY, ids=lambda p: p["id"])
def test_protocol_texts_match_backend(protocol, dicts):
    base = "mp_" + protocol["id"]
    es = dicts["es"]
    assert es.get(base + "_n") == protocol["name"], (
        f"Nombre de {protocol['id']} cambió en backend sin actualizar i18n ES"
    )
    assert es.get(base + "_d") == protocol["description"], (
        f"Descripción de {protocol['id']} cambió en backend sin actualizar i18n ES"
    )
    assert es.get(base + "_s") == "|".join(protocol["steps"]), (
        f"Pasos de {protocol['id']} cambiaron en backend sin actualizar i18n ES"
    )
    for lang in ("pt", "en"):
        for suffix in ("_n", "_d", "_s"):
            assert dicts[lang].get(base + suffix), f"Falta {base}{suffix} en {lang}"
