"""
Regresion del mapeo i18n de textos que el backend genera en espanol.

Los servicios de insight (training_service, recovery_routes, readiness_service,
injury_risk_service, performance_analytics_service) devuelven frases en
espanol. El frontend (lx-backend-i18n.js -> lxBeT) las traduce por coincidencia
exacta o por plantilla. Si el backend cambia una frase sin actualizar el
mapeo, el frontend vuelve al espanol EN SILENCIO. Este test falla en ese caso.
"""
import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BE_JS = REPO / "lx-backend-i18n.js"
I18N_JS = REPO / "i18n.js"
BACKEND_FILES = [
    REPO / "api" / "services" / "training_service.py",
    REPO / "api" / "routes" / "recovery_routes.py",
    REPO / "api" / "services" / "readiness_service.py",
    REPO / "api" / "services" / "injury_risk_service.py",
    REPO / "api" / "services" / "performance_analytics_service.py",
    REPO / "api" / "routes" / "mental_routes.py",
]
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _entries():
    src = BE_JS.read_text(encoding="utf-8")
    m = re.search(r"var LX_BE_ENTRIES = (\[.*?\]);", src, re.S)
    assert m, "LX_BE_ENTRIES no encontrado en lx-backend-i18n.js"
    return json.loads(m.group(1))


def _backend_source():
    return "\n".join(p.read_text(encoding="utf-8") for p in BACKEND_FILES)


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


def test_every_mapped_string_exists_in_backend():
    src = _backend_source()
    missing = []
    for es, _key in _entries():
        if PLACEHOLDER.search(es):
            # plantilla: el fragmento fijo mas largo debe existir en el backend
            frags = [f.strip() for f in PLACEHOLDER.split(es)[::2] if f.strip()]
            frag = max(frags, key=len) if frags else ""
            if not frag or frag not in src:
                missing.append(es)
        elif ('"' + es + '"') not in src:
            missing.append(es)
    assert not missing, "Textos del mapa que ya no existen en el backend:\n" + "\n".join(missing)


def test_keys_exist_in_all_languages_with_same_placeholders():
    dic = _load_dict()
    problems = []
    for es, key in _entries():
        for lang in ("es", "pt", "en"):
            if key not in dic[lang]:
                problems.append("%s falta en %s" % (key, lang))
        if key in dic["es"] and dic["es"][key] != es:
            problems.append("%s: valor ES no coincide con el backend" % key)
        if key in dic["pt"] and key in dic["en"]:
            want = set(PLACEHOLDER.findall(es))
            for lang in ("pt", "en"):
                got = set(PLACEHOLDER.findall(dic[lang][key]))
                if got != want:
                    problems.append("%s %s: marcadores %s != %s" % (key, lang, sorted(got), sorted(want)))
    assert not problems, "\n".join(problems)


def test_no_duplicate_or_orphan_keys():
    entries = _entries()
    es_list = [e[0] for e in entries]
    key_list = [e[1] for e in entries]
    assert len(set(es_list)) == len(es_list), "textos ES duplicados en el mapa"
    assert len(set(key_list)) == len(key_list), "claves duplicadas en el mapa"
    dic = _load_dict()
    be_keys = {k for k in dic["es"] if k.startswith("be_")}
    mapped_be = {k for k in key_list if k.startswith("be_")}
    assert be_keys == mapped_be, "claves be_* huerfanas o sin mapear: %s" % sorted(be_keys ^ mapped_be)
