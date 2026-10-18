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
    REPO / "api" / "routes" / "race_routes.py",
    # el insight diario ya genera el texto nativo desde esta tabla (ES/PT/EN)
    REPO / "api" / "services" / "insight_texts.py",
    REPO / "api" / "services" / "blood_labs_impact_service.py",
    REPO / "api" / "services" / "blood_labs_correlation_service.py",
    REPO / "api" / "routes" / "blood_lab_routes.py",
    # genera el lab_name por defecto que queda guardado en la BD ("Laboratorio Clínico")
    REPO / "scripts" / "blood_labs_upload.py",
]
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _entries():
    src = BE_JS.read_text(encoding="utf-8")
    m = re.search(r"var LX_BE_ENTRIES = (\[.*?\]);", src, re.S)
    assert m, "LX_BE_ENTRIES no encontrado en lx-backend-i18n.js"
    return json.loads(m.group(1))


def _backend_source():
    src = "\n".join(p.read_text(encoding="utf-8") for p in BACKEND_FILES)
    # literales adyacentes ("a" "b" / f"a" f"b") forman un solo texto en runtime
    return re.sub(r'"[ \t]*\r?\n[ \t]*f?"', "", src)


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


def _load_sport_map():
    src = BE_JS.read_text(encoding="utf-8")
    m = re.search(r"var LX_BE_SPORT = (\{.*?\});", src, re.S)
    assert m, "LX_BE_SPORT no encontrado en lx-backend-i18n.js"
    return json.loads(m.group(1))


def test_sport_map_keys_exist_with_matching_spanish_names():
    dic = _load_dict()
    problems = []
    for name, key in _load_sport_map().items():
        for lang in ("es", "pt", "en"):
            if key not in dic[lang]:
                problems.append("%s falta en %s" % (key, lang))
        if key in dic["es"] and dic["es"][key].lower() != name:
            problems.append("%s: ES '%s' no coincide con '%s'" % (key, dic["es"][key], name))
    assert not problems, "\n".join(problems)


def test_backend_sport_labels_exist_in_backend():
    # Los nombres de deporte que el backend emite en driver labels y plantillas
    src = (REPO / "api" / "services" / "training_service.py").read_text(encoding="utf-8")
    for name in ("Natación", "Ciclismo", "Trote", "Fuerza / Prep. física"):
        assert '"%s"' % name in src, "deporte del backend ya no existe: %s" % name


LX_INFO_JS = REPO / "lx-info.js"

FRONT_KEYS = [
    "dash_reload_now", "dash_vo2_sport", "aa_high_risk", "dash_load_high",
    "dtw_acwr_badge_low", "aa_lvl_low", "aa_lvl_mod", "aa_lvl_med", "aa_lvl_high",
    "info_tu_valor", "info_que_mide", "info_como_calcula", "info_rangos_ref",
    "info_ref_triatlon", "info_unidad",
]


def _acwr_block():
    src = LX_INFO_JS.read_text(encoding="utf-8")
    i = src.index("  acwr: {")
    j = src.index("  ctl_projected:")
    return src[i:j]


def _acwr_source_strings():
    """Textos ES del bloque acwr de lx-info.js que el panel traduce por clave."""
    blk = _acwr_block()
    str_re = r"'((?:[^'\\]|\\.)*)'"
    out = {}
    for field, key in [
        ("nombre", "info_acwr_nombre"),
        ("definicion", "info_acwr_definicion"),
        ("unidad", "info_acwr_unidad"),
        ("meta_triathlon", "info_acwr_meta"),
        ("pro_tip", "info_acwr_tip"),
    ]:
        m = re.search(field + r": " + str_re, blk)
        assert m, "campo %s no encontrado en el bloque acwr" % field
        out[key] = m.group(1)
    rangos = re.findall(r"\{min:[^}]*?label:" + str_re + r"[^}]*?advice:" + str_re + r"\}", blk)
    assert len(rangos) == 4, "se esperaban 4 rangos ACWR y hay %d" % len(rangos)
    for i, (label, advice) in enumerate(rangos):
        out["info_acwr_r%d_label" % i] = label
        out["info_acwr_r%d_adv" % i] = advice
    return out


def test_lx_info_acwr_keys_match_source_text():
    dic = _load_dict()
    problems = []
    for key, es in _acwr_source_strings().items():
        if key not in dic["es"]:
            problems.append("%s falta en es" % key)
            continue
        if dic["es"][key] != es:
            problems.append("%s: ES de i18n no coincide con lx-info.js" % key)
        for lang in ("pt", "en"):
            if key not in dic[lang]:
                problems.append("%s falta en %s" % (key, lang))
    assert not problems, "\n".join(problems)


def test_frontend_keys_exist_in_all_languages():
    dic = _load_dict()
    problems = []
    for key in FRONT_KEYS:
        for lang in ("es", "pt", "en"):
            if key not in dic[lang]:
                problems.append("%s falta en %s" % (key, lang))
    assert not problems, "\n".join(problems)


INSIGHT_KEYS_FRONT = [
    "info_insight_nombre", "info_insight_definicion", "info_insight_formula", "info_insight_tip",
    "info_tu_insight", "info_detalle_tecnico", "info_senales", "info_tu_estado",
    "info_desglose", "info_guia_hoy", "info_del_total", "info_limitante",
]


def _insight_block():
    src = LX_INFO_JS.read_text(encoding="utf-8")
    i = src.index("  insight: {")
    j = src.index("\n  },", i)
    return src[i:j]


def test_lx_info_insight_keys_match_source_text():
    blk = _insight_block()
    str_re = r"'((?:[^'\\]|\\.)*)'"
    dic = _load_dict()
    problems = []
    for field, key in [("nombre", "info_insight_nombre"), ("definicion", "info_insight_definicion"),
                       ("formula", "info_insight_formula"), ("pro_tip", "info_insight_tip")]:
        m = re.search(field + r": " + str_re, blk)
        if not m:
            problems.append("campo %s no encontrado en insight" % field)
            continue
        if key not in dic["es"]:
            problems.append("%s falta en es" % key)
        elif dic["es"][key] != m.group(1):
            problems.append("%s: ES de i18n no coincide con lx-info.js" % key)
        for lang in ("pt", "en"):
            if key not in dic[lang]:
                problems.append("%s falta en %s" % (key, lang))
    assert not problems, "\n".join(problems)


def test_insight_panel_routes_backend_text_through_lxbe():
    # El panel del insight debe traducir su texto del backend (titular, mensaje,
    # bullets tecnicos y drivers). Si alguien lo cambia, vuelve a verse en espanol.
    src = LX_INFO_JS.read_text(encoding="utf-8")
    for needle in ("_lxBe(inData.headline", "_lxBe(inData.message", "tech.map(_lxBe)", "_lxBe(dr.label)"):
        assert needle in src, "el panel del insight ya no llama a lxBeT: falta %s" % needle


def test_insight_panel_frontend_keys_exist_in_all_languages():
    dic = _load_dict()
    problems = []
    for key in INSIGHT_KEYS_FRONT:
        for lang in ("es", "pt", "en"):
            if key not in dic[lang]:
                problems.append("%s falta en %s" % (key, lang))
    assert not problems, "\n".join(problems)


def test_template_words_exist_in_all_languages():
    """Palabras sueltas (w_*) que el backend inserta en plantillas: bew_* en es/pt/en."""
    src = BE_JS.read_text(encoding="utf-8")
    m = re.search(r"var LX_BE_WORDS = (\{.*?\});", src, re.S)
    assert m, "LX_BE_WORDS no encontrado en lx-backend-i18n.js"
    dic = _load_dict()
    problems = []
    for word, key in json.loads(m.group(1)).items():
        for lang in ("es", "pt", "en"):
            if key not in dic[lang]:
                problems.append("%s falta en %s" % (key, lang))
        if key in dic["es"] and dic["es"][key] != word:
            problems.append("%s: ES '%s' != '%s'" % (key, dic["es"][key], word))
    assert not problems, "\n".join(problems)


def _run_lxbet(lang, texts):
    js = (
        "const fs=require('fs');"
        "const src=fs.readFileSync(process.argv[1],'utf8');"
        r"const m=src.match(/var DICT = \{[\s\S]*?\n\};/);eval(m[0]);"
        "global.window={i18n:{t:function(k){return DICT[process.argv[3]][k]||k;}}};"
        "eval(fs.readFileSync(process.argv[2],'utf8'));"
        "process.stdout.write(JSON.stringify(JSON.parse(process.argv[4]).map(window.lxBeT)));"
    )
    out = subprocess.run(
        ["node", "-e", js, str(I18N_JS), str(BE_JS), lang, json.dumps(texts)],
        capture_output=True, encoding="utf-8", check=True,
    )
    return json.loads(out.stdout)


def test_lxbet_translates_blood_labs_templates_and_names():
    es = [
        "URGENTE: consultar médico por Ferritina, Vitamina D",
        "Biomarcadores críticos: Ferritina",
        "CK 650 U/L → reducir sesiones de carrera con cuestas y eccéntricos",
        "Reducir CTL objetivo a ~56 (desde 80) hasta normalizar biomarcadores",
        "verde",
        "Vitamina B12 sube cuando HRV nocturno promedio sube (correlación directa 0.55).",
        "Tu Ferritina está bajo (12) y correlaciona positivamente con tu CTL (Fitness crónico) (r=0.60). "
        "Optimizarlo podría mejorar directamente tu rendimiento.",
    ]
    en = _run_lxbet("en", es)
    assert en[0] == "URGENT: see a doctor about Ferritin, Vitamin D"
    assert en[1] == "Critical biomarkers: Ferritin"
    assert en[2].startswith("CK 650 U/L") and "hills" in en[2]
    assert en[3] == "Lower target CTL to ~56 (from 80) until biomarkers normalize"
    assert en[4] == "green"
    assert en[5] == "Vitamin B12 rises when Average nightly HRV rises (direct correlation 0.55)."
    assert en[6].startswith("Your Ferritin is low (12)") and "Chronic fitness" in en[6]
    pt = _run_lxbet("pt", es)
    assert pt[4] == "verde" and pt[0].startswith("URGENTE: consultar um médico")


def test_lxbet_translates_blood_lab_alert_title_and_correlation_notes():
    """Titulo y notas de correlacion de blood_lab_routes.py (2026-10-18)."""
    es = [
        "Ferritina fuera de rango óptimo",
        "CTL actual de 45: la carga alta pudo acelerar el consumo de reservas de hierro.",
        "CTL 62: cortisol elevado + carga alta = riesgo de overreaching.",
        "CK elevada con CTL 58: el plan de esta semana debería ser de recuperación activa.",
    ]
    en = _run_lxbet("en", es)
    assert en[0] == "Ferritin out of optimal range"  # el nombre del marcador tambien se traduce
    assert en[1] == "Current CTL of 45: high load may have accelerated iron stores depletion."
    assert en[2] == "CTL 62: high cortisol + high load = overreaching risk."
    assert en[3] == "High CK with CTL 58: this week's plan should focus on active recovery."
    pt = _run_lxbet("pt", es)
    assert pt[0] == "Ferritina fora da faixa ótima"
    assert pt[2] == "CTL 62: cortisol elevado + carga alta = risco de overreaching."


def test_lxbet_translates_stored_default_lab_name():
    """lab_name por defecto guardado en la BD (blood_labs_upload.py) se traduce al leer."""
    es = ["Laboratorio Clínico"]
    assert _run_lxbet("en", es) == ["Clinical Laboratory"]
    assert _run_lxbet("pt", es) == ["Laboratório Clínico"]
    # un laboratorio con nombre propio no se toca
    assert _run_lxbet("en", ["Lab Hospital Italiano"]) == ["Lab Hospital Italiano"]


def test_blood_labs_routes_stored_lab_name_through_lxbe():
    src = (REPO / "blood_labs.html").read_text(encoding="utf-8")
    assert "_lxBe(cur.lab_name)" in src, "exam-ctx-lbl ya no traduce el lab_name guardado"


def test_lxbet_translates_marker_names_and_notes_en_pt():
    """Nombres y notas de biomarcadores que blood_lab_routes genera en vivo (MARKERS)."""
    es = [
        "HDL (colesterol bueno)",
        "LDL (colesterol malo)",
        "TSH (Tiroides)",
        "TSH en rango óptimo para atletas.",
        "HDL bajo: factor de riesgo cardiovascular. El entrenamiento aeróbico debería subirlo.",
        "Urea muy baja: posible dieta hiperproteica insuficiente.",
    ]
    assert _run_lxbet("en", es) == [
        "HDL (good cholesterol)",
        "LDL (bad cholesterol)",
        "TSH (Thyroid)",
        "TSH in optimal range for athletes.",
        "Low HDL: cardiovascular risk factor. Aerobic training should raise it.",
        "Very low urea: possibly an insufficient high-protein diet.",
    ]
    pt = _run_lxbet("pt", es)
    assert pt[0] == "HDL (colesterol bom)"
    assert pt[2] == "TSH (Tireoide)"
    assert pt[3] == "TSH na faixa ótima para atletas."


def test_every_marker_name_and_note_in_catalog_is_mapped():
    """Cada nombre y nota de MARKERS debe tener traduccion: un marcador nuevo sin mapear falla aqui."""
    src = (REPO / "api" / "routes" / "blood_lab_routes.py").read_text(encoding="utf-8")
    texts = re.findall(r'"(?:name|tip_\w+)": "([^"]+)"', src)
    assert len(texts) > 100
    mapped = {e[0] for e in _entries()}
    missing = sorted({t for t in texts if t not in mapped})
    assert not missing, "nombres/notas de MARKERS sin traduccion:\n" + "\n".join(missing)


def test_blood_labs_marker_table_routes_names_and_notes_through_lxbe():
    src = (REPO / "blood_labs.html").read_text(encoding="utf-8")
    for needle in ("_lxBe(m.name)", "_lxBe(m.tip)"):
        assert needle in src, "la tabla de biomarcadores ya no traduce: falta %s" % needle


def test_lxbet_translates_urea_supplement_hint_and_drs_warnings():
    """Recomendacion de suplementacion (blood_labs_impact) y advertencias de DRS (readiness_service)."""
    es = [
        "Aumentar ingesta proteica a 2-2.5g/kg. BCAAs intra-entrenamiento.",
        "DRS calculado con 3/4 dimensiones — datos faltantes: Bioquímica",
        "DRS calculado con 2/4 dimensiones — datos faltantes: Recuperación, Forma",
        "Sin datos fisiológicos disponibles — DRS neutral (70)",
    ]
    en = _run_lxbet("en", es)
    assert en[0] == "Increase protein intake to 2-2.5 g/kg. BCAAs during training."
    assert en[1] == "DRS calculated with 3/4 dimensions — missing data: Biochemistry"
    assert en[2].startswith("DRS calculated with 2/4 dimensions — missing data: Recovery, ")
    assert en[3] == "No physiological data available — neutral DRS (70)"
    pt = _run_lxbet("pt", es)
    assert pt[0] == "Aumentar a ingestão de proteína para 2-2,5 g/kg. BCAAs durante o treino."
    assert pt[1] == "DRS calculado com 3/4 dimensões — dados faltantes: Bioquímica"


def test_dashboard_readiness_warnings_routed_through_lxbe():
    src = (REPO / "dashboard.html").read_text(encoding="utf-8")
    assert "window.lxBeT(w)" in src, "el tooltip de readiness ya no traduce las advertencias del backend"
