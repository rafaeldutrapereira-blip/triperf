"""
Textos del insight diario (training_service.build_daily_insight) en cada idioma.

La narrativa NO la genera una IA: es un motor de reglas. Por eso cada frase se
escribe de forma nativa en ES, PT y EN, en vez de traducirla después. Las
claves son estables; las plantillas usan {marcador} y se formatean con tr().

Regla de mantenimiento: si cambias una regla o un texto de build_daily_insight,
agrega la clave aquí en los tres idiomas. api/tests/test_insight_i18n.py falla
si falta alguna o si no coinciden los marcadores.
"""

SUPPORTED = ("es", "pt", "en")

TEXTS = {
    # ── Titulares ──────────────────────────────────────────────
    "h_reduce_now": {"es": "Reducir carga hoy", "pt": "Reduzir carga hoje", "en": "Reduce load today"},
    "h_risk": {"es": "Riesgo de lesión", "pt": "Risco de lesão", "en": "Injury risk"},
    "h_risk_sport": {"es": "Riesgo de lesión en {sport}", "pt": "Risco de lesão em {sport}", "en": "Injury risk in {sport}"},
    "h_risk_crit": {"es": "Riesgo de lesión crítico", "pt": "Risco de lesão crítico", "en": "Critical injury risk"},
    "h_risk_high": {"es": "Riesgo de lesión alto", "pt": "Risco de lesão alto", "en": "High injury risk"},
    "h_fatigue": {"es": "Fatiga acumulada", "pt": "Fadiga acumulada", "en": "Accumulated fatigue"},
    "h_mental_crit": {"es": "Fatiga mental crítica", "pt": "Fadiga mental crítica", "en": "Critical mental fatigue"},
    "h_mental_high": {"es": "Fatiga mental alta", "pt": "Fadiga mental alta", "en": "High mental fatigue"},
    "h_attention": {"es": "Presta atención a tu recuperación", "pt": "Preste atenção à sua recuperação", "en": "Pay attention to your recovery"},
    "h_fresh_low": {"es": "Fresco, pero por baja carga", "pt": "Descansado, mas com pouca carga", "en": "Fresh, but on low load"},
    "h_good": {"es": "Buen momento para exigir", "pt": "Bom momento para exigir", "en": "Good time to push"},
    "h_neutral": {"es": "Todo en rango normal", "pt": "Tudo dentro da faixa normal", "en": "Everything within normal range"},

    # ── Mensajes principales (bullets) ─────────────────────────
    "b_c1_1": {
        "es": "Tu cuerpo no se recuperó bien anoche y venís acumulando cansancio de varios días.",
        "pt": "Seu corpo não se recuperou bem à noite e você vem acumulando cansaço há vários dias.",
        "en": "Your body didn't recover well last night and you've been accumulating fatigue for several days."},
    "b_c1_2": {
        "es": "Recomendación: sesión suave o descanso hoy — evitá los intervalos de alta intensidad.",
        "pt": "Recomendação: sessão leve ou descanso hoje — evite os intervalos de alta intensidade.",
        "en": "Recommendation: easy session or rest today — avoid high-intensity intervals."},
    "b_danger_1": {
        "es": "Subiste tu carga de entrenamiento muy rápido esta semana respecto a tus semanas previas.",
        "pt": "Você aumentou sua carga de treino muito rápido esta semana em relação às semanas anteriores.",
        "en": "You increased your training load very quickly this week compared with previous weeks."},
    "b_danger_2": {
        "es": "Recomendación: bajale el volumen o la intensidad hoy para reducir el riesgo de lesión.",
        "pt": "Recomendação: reduza o volume ou a intensidade hoje para diminuir o risco de lesão.",
        "en": "Recommendation: reduce volume or intensity today to lower injury risk."},
    "b_sport_1": {
        "es": "Tu carga general se ve bien, pero en {sport} subiste el volumen mucho más rápido que en el resto de tu entrenamiento.",
        "pt": "Sua carga geral está boa, mas em {sport} você aumentou o volume bem mais rápido do que no resto do seu treino.",
        "en": "Your overall load looks good, but in {sport} you increased your volume much faster than in the rest of your training."},
    "b_sport_2": {
        "es": "Recomendación: bajale el ritmo en {sport} esta semana.",
        "pt": "Recomendação: reduza o ritmo em {sport} esta semana.",
        "en": "Recommendation: ease off the pace in {sport} this week."},
    "b_inj_1": {
        "es": "Tu score de riesgo de lesión — que combina tu carga, HRV, monotonía de entrenamiento y tus últimos exámenes de sangre — está elevado, aunque tu carga de hoy por sí sola no lo muestre.",
        "pt": "Seu score de risco de lesão — que combina sua carga, HRV, monotonia de treino e seus últimos exames de sangue — está elevado, mesmo que a carga de hoje sozinha não mostre isso.",
        "en": "Your injury risk score — which combines your load, HRV, training monotony and your latest blood tests — is elevated, even though today's load alone does not show it."},
    "b_inj_2": {
        "es": "Recomendación: priorizá recuperación antes de sumar más intensidad.",
        "pt": "Recomendação: priorize a recuperação antes de somar mais intensidade.",
        "en": "Recommendation: prioritize recovery before adding more intensity."},
    "b_fat_1": {
        "es": "Venís acumulando cansancio por varios días seguidos de entrenamiento exigente.",
        "pt": "Você vem acumulando cansaço há vários dias seguidos de treino intenso.",
        "en": "You've been accumulating fatigue over several consecutive days of hard training."},
    "b_fat_2": {
        "es": "Recomendación: mantené la intensidad baja y priorizá el descanso esta semana.",
        "pt": "Recomendação: mantenha a intensidade baixa e priorize o descanso esta semana.",
        "en": "Recommendation: keep intensity low and prioritize rest this week."},
    "b_mental_1": {
        "es": "Tu carga y tu recuperación física se ven bien, pero tu check-in mental de hoy muestra fatiga {nivel}.",
        "pt": "Sua carga e sua recuperação física estão boas, mas o seu check-in mental de hoje mostra fadiga {nivel}.",
        "en": "Your training load and physical recovery look good, but today's mental check-in shows {nivel} fatigue."},
    "b_mental_2": {
        "es": "Recomendación: considerá acortar la sesión o priorizar descanso mental — el rendimiento no es solo físico.",
        "pt": "Recomendação: considere encurtar a sessão ou priorizar descanso mental — o desempenho não é só físico.",
        "en": "Recommendation: consider shortening the session or prioritizing mental rest — performance isn't only physical."},
    "b_hoy": {
        "es": "Hoy {parts}.",
        "pt": "Hoje {parts}.",
        "en": "Today {parts}."},
    "b_att_2": {
        "es": "Recomendación: tu entrenamiento sigue en nivel razonable, pero prestá atención a cómo te sentís antes de una sesión exigente.",
        "pt": "Recomendação: seu treino segue em um nível razoável, mas preste atenção em como você se sente antes de uma sessão exigente.",
        "en": "Recommendation: your training is still at a reasonable level, but pay attention to how you feel before a demanding session."},
    "b_fresh_1": {
        "es": "Tu forma se ve muy bien, pero es porque entrenaste menos de lo planificado esta semana — no necesariamente por una mejora real.",
        "pt": "Sua forma está muito boa, mas isso acontece porque você treinou menos do que o planejado esta semana — não necessariamente por uma melhora real.",
        "en": "Your form looks very good, but that's because you trained less than planned this week — not necessarily because of a real improvement."},
    "b_fresh_2": {
        "es": "Recomendación: retomá el plan gradualmente en vez de forzar una sesión muy exigente hoy.",
        "pt": "Recomendação: retome o plano gradualmente, em vez de forçar uma sessão muito exigente hoje.",
        "en": "Recommendation: resume the plan gradually instead of forcing a very demanding session today."},
    "b_good_1": {
        "es": "Estás en tu mejor momento de forma y tu recuperación se ve estable.",
        "pt": "Você está no seu melhor momento de forma e sua recuperação parece estável.",
        "en": "You're at your best fitness and your recovery looks stable."},
    "b_good_2": {
        "es": "Recomendación: buen día para una sesión de calidad o un test.",
        "pt": "Recomendação: bom dia para uma sessão de qualidade ou um teste.",
        "en": "Recommendation: good day for a quality session or a test."},
    "b_neutral_1": {
        "es": "Tu entrenamiento y tu recuperación están dentro de lo esperado hoy.",
        "pt": "Seu treino e sua recuperação estão dentro do esperado hoje.",
        "en": "Your training and recovery are within the expected range today."},
    "b_neutral_2": {
        "es": "Recomendación: seguí tu plan con normalidad.",
        "pt": "Recomendação: siga seu plano normalmente.",
        "en": "Recommendation: follow your plan as usual."},

    # ── Detalle técnico (bullets "ver por qué") ────────────────
    "t_pct": {"es": " ({pct}%)", "pt": " ({pct}%)", "en": " ({pct}%)"},
    "t_hrv_down": {
        "es": "HRV de anoche: {hrv}ms — bajó{pct_txt}",
        "pt": "HRV da noite: {hrv}ms — caiu{pct_txt}",
        "en": "HRV last night: {hrv}ms — dropped{pct_txt}"},
    "t_hrv_down0": {
        "es": "HRV de anoche: {hrv}ms — bajó",
        "pt": "HRV da noite: {hrv}ms — caiu",
        "en": "HRV last night: {hrv}ms — dropped"},
    "t_hrv_stable": {
        "es": "HRV de anoche: {hrv}ms — estable",
        "pt": "HRV da noite: {hrv}ms — estável",
        "en": "HRV last night: {hrv}ms — stable"},
    "t_tsb_fatigue": {
        "es": "TSB (forma): {tsb} — con fatiga acumulada (ATL {atl})",
        "pt": "TSB (forma): {tsb} — com fadiga acumulada (ATL {atl})",
        "en": "TSB (form): {tsb} — with accumulated fatigue (ATL {atl})"},
    "t_sleep_low": {
        "es": "Sueño anoche: por debajo de lo habitual",
        "pt": "Sono à noite: abaixo do habitual",
        "en": "Sleep last night: below usual"},
    "t_sleep_hm": {
        "es": "Sueño anoche: {hm}",
        "pt": "Sono à noite: {hm}",
        "en": "Sleep last night: {hm}"},
    "t_aerobic_rec": {
        "es": "Recomendación: sesión aeróbica suave o descanso — evitá intervalos de alta intensidad",
        "pt": "Recomendação: sessão aeróbica leve ou descanso — evite intervalos de alta intensidade",
        "en": "Recommendation: easy aerobic session or rest — avoid high-intensity intervals"},
    "t_acwr_current": {
        "es": "ACWR actual: {acwr} (rango seguro: 0.8–1.3)",
        "pt": "ACWR atual: {acwr} (faixa segura: 0,8–1,3)",
        "en": "Current ACWR: {acwr} (safe range: 0.8–1.3)"},
    "t_load_28": {
        "es": "Carga semanal muy por encima de tu promedio de 28 días",
        "pt": "Carga semanal muito acima da sua média de 28 dias",
        "en": "Weekly load well above your 28-day average"},
    "t_reduce_now": {
        "es": "Recomendación: reducí volumen o intensidad hoy",
        "pt": "Recomendação: reduza volume ou intensidade hoje",
        "en": "Recommendation: reduce volume or intensity today"},
    "t_sport_acwr": {
        "es": "ACWR {label}: {acwr} (zona de riesgo, >1.5)",
        "pt": "ACWR {label}: {acwr} (zona de risco, >1,5)",
        "en": "ACWR {label}: {acwr} (risk zone, >1.5)"},
    "t_acwr_general": {
        "es": "ACWR general: {acwr} ({zona}) — en rango",
        "pt": "ACWR geral: {acwr} ({zona}) — na faixa",
        "en": "Overall ACWR: {acwr} ({zona}) — within range"},
    "t_overuse": {
        "es": "Las lesiones por sobreuso son específicas de tejido: un pico aislado no se compensa con el resto",
        "pt": "As lesões por sobrecarga são específicas do tecido: um pico isolado não se compensa com o resto",
        "en": "Overuse injuries are tissue-specific: an isolated spike is not offset by the rest"},
    "t_sport_rec": {
        "es": "Recomendación: bajale el ritmo en {sport} esta semana",
        "pt": "Recomendação: reduza o ritmo em {sport} esta semana",
        "en": "Recommendation: ease off the pace in {sport} this week"},
    "t_inj_score": {
        "es": "Injury Risk Score: {score}/100 ({nivel})",
        "pt": "Injury Risk Score: {score}/100 ({nivel})",
        "en": "Injury Risk Score: {score}/100 ({nivel})"},
    "t_inj_compose": {
        "es": "Compone: ACWR 35% · HRV 30% · Monotonía de entrenamiento 20% · Marcadores de sangre 15%",
        "pt": "Composição: ACWR 35% · HRV 30% · Monotonia de treino 20% · Marcadores de sangue 15%",
        "en": "Composed of: ACWR 35% · HRV 30% · Training monotony 20% · Blood markers 15%"},
    "t_acwr_isolated": {
        "es": "ACWR aislado hoy: {acwr} — se ve en rango por sí solo",
        "pt": "ACWR isolado hoje: {acwr} — está na faixa por si só",
        "en": "ACWR alone today: {acwr} — within range on its own"},
    "t_inj_rec": {
        "es": "Recomendación: priorizá recuperación antes de sumar más intensidad",
        "pt": "Recomendação: priorize a recuperação antes de somar mais intensidade",
        "en": "Recommendation: prioritize recovery before adding more intensity"},
    "t_fat_tsb": {
        "es": "TSB (forma): {tsb} — nivel de fatiga alto",
        "pt": "TSB (forma): {tsb} — nível de fadiga alto",
        "en": "TSB (form): {tsb} — high fatigue level"},
    "t_fat_atl": {
        "es": "ATL (carga aguda): {atl} — varios días de carga sostenida",
        "pt": "ATL (carga aguda): {atl} — vários dias de carga sustentada",
        "en": "ATL (acute load): {atl} — several days of sustained load"},
    "t_fat_rec": {
        "es": "Recomendación: intensidad baja y priorizá descanso esta semana para no entrar en sobreentrenamiento",
        "pt": "Recomendação: intensidade baixa e priorize o descanso esta semana para não entrar em overtraining",
        "en": "Recommendation: low intensity and prioritize rest this week to avoid overtraining"},
    "t_mental_score": {
        "es": "Mental Fatigue Score: {score}/100 (check-in de mental.html)",
        "pt": "Mental Fatigue Score: {score}/100 (check-in no módulo Mental)",
        "en": "Mental Fatigue Score: {score}/100 (mental check-in)"},
    "t_phys_ok": {
        "es": "Carga física: TSB {tsb}, ACWR {acwr} — en rango razonable",
        "pt": "Carga física: TSB {tsb}, ACWR {acwr} — dentro de uma faixa razoável",
        "en": "Physical load: TSB {tsb}, ACWR {acwr} — reasonable range"},
    "t_subj": {
        "es": "La fatiga viene del lado subjetivo, no del entrenamiento físico",
        "pt": "A fadiga vem do lado subjetivo, não do treino físico",
        "en": "The fatigue comes from the subjective side, not from physical training"},
    "t_mental_rec": {
        "es": "Recomendación: acortá la sesión o priorizá descanso mental",
        "pt": "Recomendação: encurte a sessão ou priorize o descanso mental",
        "en": "Recommendation: shorten the session or prioritize mental rest"},
    "t_carga_todavia": {
        "es": "Carga de entrenamiento: TSB {tsb}, ACWR {acwr} — todavía en rango razonable",
        "pt": "Carga de treino: TSB {tsb}, ACWR {acwr} — ainda em faixa razoável",
        "en": "Training load: TSB {tsb}, ACWR {acwr} — still in a reasonable range"},
    "t_fc_up": {
        "es": "FC en reposo: {rhr}bpm — subió",
        "pt": "FC em repouso: {rhr}bpm — subiu",
        "en": "Resting HR: {rhr}bpm — went up"},
    "t_monitor": {
        "es": "Recomendación: monitoreá cómo te sentís antes de una sesión exigente",
        "pt": "Recomendação: monitore como você se sente antes de uma sessão exigente",
        "en": "Recommendation: monitor how you feel before a demanding session"},
    "t_tsb_range": {
        "es": "TSB {tsb} — dentro del rango normal (-8 a +15): ni fatiga excesiva ni forma pico",
        "pt": "TSB {tsb} — dentro da faixa normal (-8 a +15): nem fadiga excessiva nem forma de pico",
        "en": "TSB {tsb} — within the normal range (-8 to +15): neither excess fatigue nor peak form"},
    "t_acwr_range": {
        "es": "ACWR {acwr} — dentro del rango seguro (0.8–1.3)",
        "pt": "ACWR {acwr} — dentro da faixa segura (0,8–1,3)",
        "en": "ACWR {acwr} — within the safe range (0.8–1.3)"},
    "t_tsb_plus": {
        "es": "TSB +{tsb} — por encima del umbral de forma óptima (+15)",
        "pt": "TSB +{tsb} — acima do limiar de forma ótima (+15)",
        "en": "TSB +{tsb} — above the optimal fitness threshold (+15)"},
    "t_acwr_no_less": {
        "es": "ACWR {acwr} — dentro del rango seguro (0.8–1.3), no viene de entrenar de menos",
        "pt": "ACWR {acwr} — dentro da faixa segura (0,8–1,3), não vem de treinar pouco",
        "en": "ACWR {acwr} — within the safe range (0.8–1.3), not from training too little"},
    "t_no_indicator": {
        "es": "Ningún indicador de fatiga o mala recuperación está activo",
        "pt": "Nenhum indicador de fadiga ou má recuperação está ativo",
        "en": "No fatigue or poor-recovery indicator is active"},
    "t_none_out": {
        "es": "Ninguno de tus indicadores de carga o recuperación está fuera de rango",
        "pt": "Nenhum dos seus indicadores de carga ou recuperação está fora da faixa",
        "en": "None of your load or recovery indicators are out of range"},
    "t_tsb_acwr_ok": {
        "es": "TSB {tsb} y ACWR {acwr} — ambos en rango saludable",
        "pt": "TSB {tsb} e ACWR {acwr} — ambos em faixa saudável",
        "en": "TSB {tsb} and ACWR {acwr} — both in a healthy range"},
    "t_compliance": {
        "es": "Cumplimiento del plan esta semana: {pct}%",
        "pt": "Cumprimento do plano esta semana: {pct}%",
        "en": "Plan compliance this week: {pct}%"},
    "t_tsb_plan_nota": {
        "es": "El TSB alto puede reflejar menos carga acumulada, no necesariamente una mejora real de forma",
        "pt": "Um TSB alto pode refletir menos carga acumulada, não necessariamente uma melhora real de forma",
        "en": "A high TSB may reflect less accumulated load, not necessarily a real fitness gain"},
    "t_rec_plan": {
        "es": "Recomendación: retomá el plan gradualmente",
        "pt": "Recomendação: retome o plano gradualmente",
        "en": "Recommendation: resume the plan gradually"},
    "t_gear_one": {
        "es": "Equipo: {label} al {pct}% de su vida útil — revisalo en Mi Equipo",
        "pt": "Equipamento: {label} com {pct}% da vida útil — confira em Meu Equipamento",
        "en": "Gear: {label} at {pct}% of its useful life — check it in My Gear"},
    "t_gear_many": {
        "es": "Equipo: {n} ítems por encima del 80% de vida útil (el más avanzado: {label} {pct}%) — revisalos en Mi Equipo",
        "pt": "Equipamento: {n} itens acima de 80% da vida útil (o mais avançado: {label} {pct}%) — confira em Meu Equipamento",
        "en": "Gear: {n} items above 80% of useful life (the most worn: {label} {pct}%) — check them in My Gear"},

    # ── Etiquetas de drivers ───────────────────────────────────
    "d_gear": {"es": "Equipo", "pt": "Equipamento", "en": "Gear"},
    "d_hrv": {"es": "HRV anoche", "pt": "HRV da noite", "en": "HRV last night"},
    "d_tsb": {"es": "TSB (forma)", "pt": "TSB (forma)", "en": "TSB (form)"},
    "d_sleep": {"es": "Sueño anoche", "pt": "Sono à noite", "en": "Sleep last night"},
    "d_mental": {"es": "Fatiga mental (check-in)", "pt": "Fadiga mental (check-in)", "en": "Mental fatigue (check-in)"},
    "d_compliance": {"es": "Cumplimiento semanal", "pt": "Cumprimento semanal", "en": "Weekly compliance"},
    "d_risk": {"es": "Riesgo de lesión", "pt": "Risco de lesão", "en": "Injury risk"},
    "d_acwr_sport": {"es": "ACWR {sport}", "pt": "ACWR {sport}", "en": "ACWR {sport}"},
    "alerts_1": {"es": "1 alerta", "pt": "1 alerta", "en": "1 alert"},
    "alerts_n": {"es": "{n} alertas", "pt": "{n} alertas", "en": "{n} alerts"},

    # ── Partes de la frase "Hoy …" y niveles ───────────────────
    "p_hrv": {"es": "tu recuperación nocturna bajó", "pt": "sua recuperação noturna caiu", "en": "your overnight recovery dropped"},
    "p_sleep": {"es": "dormiste menos de lo habitual", "pt": "você dormiu menos que o habitual", "en": "you slept less than usual"},
    "p_rhr": {"es": "tu frecuencia cardíaca en reposo subió", "pt": "sua frequência cardíaca em repouso subiu", "en": "your resting heart rate went up"},
    "lv_mental_crit": {"es": "crítica", "pt": "crítica", "en": "critical"},
    "lv_mental_high": {"es": "alta", "pt": "alta", "en": "high"},
    "lv_high": {"es": "alto", "pt": "alto", "en": "high"},
    "lv_critical": {"es": "crítico", "pt": "crítico", "en": "critical"},

    # ── CTA (botones) ──────────────────────────────────────────
    "cta_recovery_protocol": {"es": "Ver protocolo de recuperación sugerido", "pt": "Ver protocolo de recuperação sugerido", "en": "See suggested recovery protocol"},
    "cta_load_history": {"es": "Ver histórico de carga", "pt": "Ver histórico de carga", "en": "See load history"},
    "cta_acwr_discipline": {"es": "Ver ACWR por disciplina", "pt": "Ver ACWR por modalidade", "en": "See ACWR by discipline"},
    "cta_inj_detail": {"es": "Ver detalle de riesgo de lesión", "pt": "Ver detalhe do risco de lesão", "en": "See injury risk details"},
    "cta_pmc": {"es": "Ver histórico PMC", "pt": "Ver histórico PMC", "en": "See PMC history"},
    "cta_mental": {"es": "Ver protocolos de recuperación mental", "pt": "Ver protocolos de recuperação mental", "en": "See mental recovery protocols"},
    "cta_plan": {"es": "Ver tu plan de la semana", "pt": "Ver seu plano da semana", "en": "See your weekly plan"},

    # ── Deportes (sustantivo y forma en minúscula) ─────────────
    "sp_swim": {"es": "Natación", "pt": "Natação", "en": "Swimming"},
    "sp_bike": {"es": "Ciclismo", "pt": "Ciclismo", "en": "Cycling"},
    "sp_run": {"es": "Trote", "pt": "Corrida", "en": "Run"},
    "sp_gym": {"es": "Fuerza / Prep. física", "pt": "Força / Prep. física", "en": "Strength / Prep."},
}

# Nombre del deporte tal como lo entrega ACWR_SPORT_LABELS -> clave
SPORT_KEYS = {
    "Natación": "sp_swim",
    "Ciclismo": "sp_bike",
    "Trote": "sp_run",
    "Fuerza / Prep. física": "sp_gym",
}


def norm_lang(lang):
    """Idioma soportado o 'es' (valor por defecto de la app)."""
    if not lang:
        return "es"
    code = str(lang).strip().lower()[:2]
    return code if code in SUPPORTED else "es"


def tr(key, lang="es", **kw):
    """Texto del insight en el idioma pedido, con sus marcadores llenados."""
    entry = TEXTS[key]
    text = entry.get(norm_lang(lang)) or entry["es"]
    return text.format(**kw) if kw else text


def sport_t(label, lang="es", lower=False):
    """Nombre de deporte en el idioma pedido. Si no es un deporte conocido, lo deja igual."""
    key = SPORT_KEYS.get(label)
    if not key:
        return label.lower() if lower else label
    name = tr(key, lang)
    return name.lower() if lower else name
