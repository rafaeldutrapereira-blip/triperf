window.KL_BLOOD = {
  "biomarkers": {
    "glucosa": {
      "label": "Glucosa",
      "unit": "mg/dL",
      "category": "bioquimica",
      "ref_low": 70.0,
      "ref_high": 99.0,
      "direction": "range",
      "athlete_note": "Ayuno. Óptimo deportista: 75-95"
    },
    "nitrogeno_ureico": {
      "label": "Nitrógeno Ureico",
      "unit": "mg/dL",
      "category": "renal",
      "ref_low": 7.0,
      "ref_high": 20.0,
      "direction": "range",
      "athlete_note": "Puede elevarse con dieta alta en proteínas o deshidratación"
    },
    "urea": {
      "label": "Urea",
      "unit": "mg/dL",
      "category": "renal",
      "ref_low": 15.0,
      "ref_high": 43.0,
      "direction": "range",
      "athlete_note": "Refleja catabolismo proteico post-esfuerzo"
    },
    "colesterol_total": {
      "label": "Colesterol Total",
      "unit": "mg/dL",
      "category": "lipidos",
      "ref_low": 0.0,
      "ref_high": 200.0,
      "direction": "lower",
      "athlete_note": "Atletas resistencia: frecuente <150. Muy bajo puede indicar poca síntesis hormonal."
    },
    "ac_urico": {
      "label": "Ácido Úrico",
      "unit": "mg/dL",
      "category": "lipidos",
      "ref_low": 2.4,
      "ref_high": 7.0,
      "direction": "range",
      "athlete_note": "Se eleva con catabolismo celular intenso"
    },
    "proteinas_totales": {
      "label": "Proteínas Totales",
      "unit": "g/dL",
      "category": "bioquimica",
      "ref_low": 6.4,
      "ref_high": 8.3,
      "direction": "range",
      "athlete_note": "Marcador de estado nutricional proteico"
    },
    "albumina": {
      "label": "Albúmina",
      "unit": "g/dL",
      "category": "bioquimica",
      "ref_low": 3.5,
      "ref_high": 5.2,
      "direction": "range",
      "athlete_note": "Proteína sérica principal; refleja nutrición y estado inflamatorio"
    },
    "globulinas": {
      "label": "Globulinas",
      "unit": "g/dL",
      "category": "bioquimica",
      "ref_low": 2.0,
      "ref_high": 3.5,
      "direction": "range",
      "athlete_note": "Incluye inmunoglobulinas; índice de respuesta inmune"
    },
    "bilirrubina_total": {
      "label": "Bilirrubina Total",
      "unit": "mg/dL",
      "category": "enzimas",
      "ref_low": 0.2,
      "ref_high": 1.2,
      "direction": "range",
      "athlete_note": "Puede elevarse post-ejercicio intenso (hemólisis de esfuerzo)"
    },
    "got_ast": {
      "label": "GOT / AST",
      "unit": "U/L",
      "category": "enzimas",
      "ref_low": 10.0,
      "ref_high": 40.0,
      "direction": "range",
      "athlete_note": "Indicador daño muscular/hepático. Se eleva normalmente 24-48h post-entrenamiento."
    },
    "gpt_alt": {
      "label": "GPT / ALT",
      "unit": "U/L",
      "category": "enzimas",
      "ref_low": 7.0,
      "ref_high": 56.0,
      "direction": "range",
      "athlete_note": "Más específico del hígado. Elevación crónica: revisar carga hepática."
    },
    "ggt": {
      "label": "GGT",
      "unit": "U/L",
      "category": "enzimas",
      "ref_low": 8.0,
      "ref_high": 61.0,
      "direction": "range",
      "athlete_note": "Sensible a alcohol, medicamentos y estrés metabólico"
    },
    "ldh": {
      "label": "LDH",
      "unit": "U/L",
      "category": "muscular",
      "ref_low": 140.0,
      "ref_high": 280.0,
      "direction": "range",
      "athlete_note": "Marcador global de estrés celular. Ideal en atleta: 150-220"
    },
    "fosfatasas_alc": {
      "label": "Fosfatasas Alcalinas",
      "unit": "U/L",
      "category": "enzimas",
      "ref_low": 44.0,
      "ref_high": 147.0,
      "direction": "range",
      "athlete_note": "Elevación puede indicar estrés óseo (fracturas por fatiga)"
    },
    "calcio": {
      "label": "Calcio",
      "unit": "mg/dL",
      "category": "electrolitos",
      "ref_low": 8.5,
      "ref_high": 10.5,
      "direction": "range",
      "athlete_note": "Crítico para contracción muscular y densidad ósea"
    },
    "fosforo": {
      "label": "Fósforo",
      "unit": "mg/dL",
      "category": "electrolitos",
      "ref_low": 2.5,
      "ref_high": 4.5,
      "direction": "range",
      "athlete_note": "Participa en síntesis de ATP (energía celular)"
    },
    "trigliceridos": {
      "label": "Triglicéridos",
      "unit": "mg/dL",
      "category": "lipidos",
      "ref_low": 0.0,
      "ref_high": 150.0,
      "direction": "lower",
      "athlete_note": "Atletas resistencia: <80 mg/dL. Muy bajos son signo de buena condición aeróbica."
    },
    "hdl": {
      "label": "HDL (Colesterol bueno)",
      "unit": "mg/dL",
      "category": "lipidos",
      "ref_low": 40.0,
      "ref_high": 100.0,
      "direction": "higher",
      "athlete_note": "Óptimo resistencia: >55. Correlaciona con capacidad aeróbica."
    },
    "ldl": {
      "label": "LDL (Colesterol malo)",
      "unit": "mg/dL",
      "category": "lipidos",
      "ref_low": 0.0,
      "ref_high": 100.0,
      "direction": "lower",
      "athlete_note": "Óptimo: <70. Atleta con colesterol total bajo suele tener LDL bajo."
    },
    "ck": {
      "label": "Creatinquinasa (CK)",
      "unit": "U/L",
      "category": "muscular",
      "ref_low": 52.0,
      "ref_high": 336.0,
      "direction": "range",
      "athlete_note": "CLAVE: refleja daño/recuperación muscular. Basal atleta: 80-250. Post-esfuerzo max: hasta 1000. Cronicamente >500: sobreentrenamiento."
    },
    "vitamina_b12": {
      "label": "Vitamina B12",
      "unit": "pg/mL",
      "category": "vitaminas",
      "ref_low": 200.0,
      "ref_high": 900.0,
      "direction": "range",
      "athlete_note": "Crítica para eritropoyesis y función nerviosa. Óptimo deportista: 400-900."
    },
    "creatinina": {
      "label": "Creatinina",
      "unit": "mg/dL",
      "category": "renal",
      "ref_low": 0.74,
      "ref_high": 1.35,
      "direction": "range",
      "athlete_note": "En atletas musculosos puede estar en límite alto y ser normal"
    },
    "tfge": {
      "label": "TFGe",
      "unit": "mL/min",
      "category": "renal",
      "ref_low": 60.0,
      "ref_high": 120.0,
      "direction": "higher",
      "athlete_note": "Función renal: >90 = normal, 60-89 = levemente reducida, <60 = alterada"
    },
    "psa_total": {
      "label": "PSA Total",
      "unit": "ng/mL",
      "category": "hormonal",
      "ref_low": 0.0,
      "ref_high": 4.0,
      "direction": "lower",
      "athlete_note": "Marcador prostático. El ejercicio intenso puede elevarlo transitoriamente."
    },
    "tsh": {
      "label": "TSH",
      "unit": "uU/mL",
      "category": "hormonal",
      "ref_low": 0.4,
      "ref_high": 4.0,
      "direction": "range",
      "athlete_note": "Tiroides. Entrenamiento excesivo puede suprimir TSH (síndrome de sobreentrenamiento)"
    },
    "ft4": {
      "label": "T4 Libre (FT4)",
      "unit": "ng/dL",
      "category": "hormonal",
      "ref_low": 0.8,
      "ref_high": 1.8,
      "direction": "range",
      "athlete_note": "Hormona tiroidea activa. Refleja estado metabólico basal."
    },
    "na": {
      "label": "Sodio (Na)",
      "unit": "mEq/L",
      "category": "electrolitos",
      "ref_low": 136.0,
      "ref_high": 145.0,
      "direction": "range",
      "athlete_note": "Hiponatremia por sudoración o hiperhidratación: riesgo en pruebas largas"
    },
    "k": {
      "label": "Potasio (K)",
      "unit": "mEq/L",
      "category": "electrolitos",
      "ref_low": 3.5,
      "ref_high": 5.1,
      "direction": "range",
      "athlete_note": "Crítico para función muscular y cardíaca"
    },
    "cl": {
      "label": "Cloro (Cl)",
      "unit": "mEq/L",
      "category": "electrolitos",
      "ref_low": 98.0,
      "ref_high": 107.0,
      "direction": "range",
      "athlete_note": "Equilibrio ácido-base. Refleja pérdidas por sudoración"
    },
    "vitamina_d": {
      "label": "Vitamina D",
      "unit": "ng/mL",
      "category": "vitaminas",
      "ref_low": 30.0,
      "ref_high": 100.0,
      "direction": "higher",
      "athlete_note": "Óptimo atleta: >40. Insuficiente: 20-29. Deficiente: <20. Impacta fuerza, inmunidad y recuperación."
    },
    "eritrocitos": {
      "label": "Recuento Hematíes",
      "unit": "10⁶/µL",
      "category": "hemograma",
      "ref_low": 4.5,
      "ref_high": 5.9,
      "direction": "range",
      "athlete_note": "Capacidad de transporte de O2. Atleta élite: 5.2-5.8"
    },
    "hemoglobina": {
      "label": "Hemoglobina",
      "unit": "g/dL",
      "category": "hemograma",
      "ref_low": 13.5,
      "ref_high": 17.5,
      "direction": "range",
      "athlete_note": "Proteína transportadora de O2. Óptimo resistencia hombre: >15.5 g/dL"
    },
    "hematocrito": {
      "label": "Hematocrito",
      "unit": "%",
      "category": "hemograma",
      "ref_low": 41.0,
      "ref_high": 53.0,
      "direction": "range",
      "athlete_note": "Fracción eritrocitaria. Óptimo resistencia: 45-52%. >52% requiere investigar."
    },
    "vcm": {
      "label": "VCM",
      "unit": "fL",
      "category": "hemograma",
      "ref_low": 80.0,
      "ref_high": 100.0,
      "direction": "range",
      "athlete_note": "Volumen corpuscular medio. Microcitosis → déficit Fe. Macrocitosis → déficit B12/folato."
    },
    "hcm": {
      "label": "HCM",
      "unit": "pg",
      "category": "hemograma",
      "ref_low": 27.0,
      "ref_high": 33.0,
      "direction": "range",
      "athlete_note": "Hemoglobina corpuscular media. Bajo → anemia ferropénica."
    },
    "chcm": {
      "label": "CHCM",
      "unit": "g/dL",
      "category": "hemograma",
      "ref_low": 32.0,
      "ref_high": 36.0,
      "direction": "range",
      "athlete_note": "Concentración Hb por eritrocito. Hipocromía → déficit de hierro."
    },
    "leucocitos": {
      "label": "Leucocitos",
      "unit": "10³/µL",
      "category": "hemograma",
      "ref_low": 4.0,
      "ref_high": 11.0,
      "direction": "range",
      "athlete_note": "Respuesta inmune. Leucopenia leve en resistencia es fisiológica. Elevación post-esfuerzo normal."
    },
    "plaquetas": {
      "label": "Plaquetas",
      "unit": "10³/µL",
      "category": "hemograma",
      "ref_low": 150.0,
      "ref_high": 400.0,
      "direction": "range",
      "athlete_note": "Hemostasia. Estables en atletas bien entrenados."
    },
    "sedimentacion": {
      "label": "Sedimentación (VSG)",
      "unit": "mm/hr",
      "category": "hemograma",
      "ref_low": 0.0,
      "ref_high": 15.0,
      "direction": "lower",
      "athlete_note": "Marcador inflamatorio inespecífico. <5 en atleta sano = excelente."
    }
  },
  "exams": []
};