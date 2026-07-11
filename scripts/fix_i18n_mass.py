"""
Mass i18n coverage improvement — LabX all pages.
Adds data-i18n to all static translatable texts found in the audit.
"""
import sys, re, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
base = 'C:/Users/rafae/projects/LabX/'

def patch(path, pairs):
    """Apply (old_exact, new_exact) replacements to a file."""
    with open(path, encoding='utf-8') as f:
        c = f.read()
    n = 0
    for old, new in pairs:
        occ = c.count(old)
        if occ > 0 and old != new:
            c = c.replace(old, new)
            n += occ
    with open(path, 'w', encoding='utf-8') as f:
        f.write(c)
    return n

report = {}

# ── 1. SIDEBAR TAGLINE — all pages with sidebar ──────────────────────────────
# "Where Champions Are Built" → needs a new i18n key: app_tagline
tagline_pages = [
    'dashboard.html','training_detail.html','blood_labs.html','nutrition.html',
    'training_plan.html','race_predictor.html','athlete_profile.html','coach.html'
]
for p in tagline_pages:
    n = patch(base+p, [
        ('class="sb-tagline">Where Champions Are Built</div>',
         'class="sb-tagline" data-i18n="app_tagline">Where Champions Are Built</div>'),
    ])
    if n: report[p] = report.get(p,0)+n

# ── 2. SIDEBAR SECTION LABEL "Módulos" ───────────────────────────────────────
# Already partially done. Catch the remaining pages.
for p in tagline_pages:
    n = patch(base+p, [
        ('<span class="sb-sect">Módulos</span>',
         '<span class="sb-sect" data-i18n="nav_modules">Módulos</span>'),
        ('<span class="sb-sect">Módulos<span',   # already wrapped version
         '<span class="sb-sect">Módulos<span'),  # skip if already wrapped
    ])
    if n: report[p] = report.get(p,0)+n

# ── 3. ATHLETE_PROFILE.HTML ──────────────────────────────────────────────────
n = patch(base+'athlete_profile.html', [
    ('>Identificación<',         ' data-i18n="prof_identification">Identificación<'),
    ('>Datos Físicos<',          ' data-i18n="prof_physical">Datos Físicos<'),
    ('>Potencia y Cardio<',      ' data-i18n="prof_power_cardio">Potencia y Cardio<'),
    ('>Ritmos Umbral<',          ' data-i18n="prof_thresholds">Ritmos Umbral<'),
    ('>Objetivo Temporada<',     ' data-i18n="prof_season_goal">Objetivo Temporada<'),
    ('>Guardar cambios<',        ' data-i18n="btn_save_changes">Guardar cambios<'),
    ('>Guardar Perfil<',         ' data-i18n="btn_save_changes">Guardar Perfil<'),
    ('>Mi Perfil<',              ' data-i18n="nav_profile">Mi Perfil<'),
    # Profile section headings
    ('>Datos personales<',       ' data-i18n="prof_identification">Datos personales<'),
    ('>Conexión Garmin<',        ' data-i18n="sec_garmin_conn">Conexión Garmin<'),
    ('>Carrera objetivo<',       ' data-i18n="sec_target_race">Carrera objetivo<'),
])
report['athlete_profile.html'] = report.get('athlete_profile.html',0)+n

# ── 4. DETALLE.HTML — hero and section labels ─────────────────────────────────
n = patch(base+'detalle.html', [
    ('>Valor actual<',           ' data-i18n="det_current_val">Valor actual<'),
    ('>Último registro<',        ' data-i18n="det_last_record">Último registro<'),
    ('>Energía disponible<',     ' data-i18n="det_energy">Energía disponible<'),
    ('>Fatiga Muscular (TSB)<',  ' data-i18n="det_muscle_fatigue">Fatiga Muscular (TSB)<'),
    # Back button
    ('>Dashboard<',              ' data-i18n="nav_dashboard">Dashboard<'),
])
report['detalle.html'] = report.get('detalle.html',0)+n

# ── 5. DASHBOARD.HTML — section headers ──────────────────────────────────────
n = patch(base+'dashboard.html', [
    ('>Resumen General<',        ' data-i18n="sec_overview">Resumen General<'),
    ('>Próximas sesiones<',      ' data-i18n="sec_upcoming">Próximas sesiones<'),
    ('>Bienestar<',              ' data-i18n="sec_bienestar">Bienestar<'),
    ('>Carga de Entrenamiento<', ' data-i18n="kpi_load">Carga de Entrenamiento<'),
    ('>Carrera objetivo<',       ' data-i18n="sec_target_race">Carrera objetivo<'),
    ('>Forma<',                  ' data-i18n="kpi_fitness">Forma<'),
    ('>Fatiga<',                 ' data-i18n="kpi_fatigue">Fatiga<'),
    ('>Frescura<',               ' data-i18n="kpi_form">Frescura<'),
    ('>Readiness<',              ' data-i18n="kpi_readiness">Readiness<'),
    ('>TSS Semana<',             ' data-i18n="kpi_tss_week">TSS Semana<'),
    ('>ACWR<',                   ' data-i18n="kpi_acwr">ACWR<'),
    ('>HRV Score<',              ' data-i18n="kpi_hrv">HRV Score<'),
    ('>Conexión Garmin<',        ' data-i18n="sec_garmin_conn">Conexión Garmin<'),
    ('>Sincronizar Garmin<',     ' data-i18n="btn_sync_garmin">Sincronizar Garmin<'),
    ('>Ver histórico →<',        ' data-i18n="btn_view_history">Ver histórico →<'),
])
report['dashboard.html'] = report.get('dashboard.html',0)+n

# ── 6. TRAINING_PLAN.HTML — section headers ───────────────────────────────────
n = patch(base+'training_plan.html', [
    ('>Plan de Entrenamiento<',  ' data-i18n="nav_plan">Plan de Entrenamiento<'),
    ('>PLAN DE ENTRENAMIENTO<',  ' data-i18n="nav_plan">PLAN DE ENTRENAMIENTO<'),
    ('>Guardar Sesión<',         ' data-i18n="btn_save_session">Guardar Sesión<'),
    ('>Guardar resultado<',      ' data-i18n="btn_save_result">Guardar resultado<'),
    ('>Registrar resultado<',    ' data-i18n="btn_register_result">Registrar resultado<'),
    ('>Disciplina<',             ' data-i18n="tp_discipline">Disciplina<'),
    ('>Duración (min)<',         ' data-i18n="tp_duration">Duración (min)<'),
    ('>Distancia (km)<',         ' data-i18n="tp_distance">Distancia (km)<'),
    ('>TSS Objetivo<',           ' data-i18n="tp_tss_target">TSS Objetivo<'),
    ('>TSS Real<',               ' data-i18n="tp_tss_real">TSS Real<'),
    ('>Anterior<',               ' data-i18n="btn_prev">Anterior<'),
    ('>Siguiente<',              ' data-i18n="btn_next">Siguiente<'),
    ('>Actualizar Plan<',        ' data-i18n="btn_update_plan">Actualizar Plan<'),
    ('>Guardar<',                ' data-i18n="btn_save">Guardar<'),
    ('>Cancelar<',               ' data-i18n="btn_cancel">Cancelar<'),
])
report['training_plan.html'] = report.get('training_plan.html',0)+n

# ── 7. NUTRITION.HTML ─────────────────────────────────────────────────────────
n = patch(base+'nutrition.html', [
    ('>Resumen<',                ' data-i18n="nutr_summary">Resumen<'),
    ('>Plan Hora a Hora<',       ' data-i18n="nutr_plan">Plan Hora a Hora<'),
    ('>Pre-Carrera<',            ' data-i18n="nutr_prerace">Pre-Carrera<'),
    ('>Carbohidratos<',          ' data-i18n="nutr_cho">Carbohidratos<'),
    ('>Proteínas<',              ' data-i18n="nutr_pro">Proteínas<'),
    ('>Grasas<',                 ' data-i18n="nutr_fat">Grasas<'),
    ('>Calorías<',               ' data-i18n="nutr_kcal">Calorías<'),
    ('>Líquidos<',               ' data-i18n="nutr_fluid">Líquidos<'),
    ('>Guardar Plan<',           ' data-i18n="btn_save">Guardar Plan<'),
])
report['nutrition.html'] = report.get('nutrition.html',0)+n

# ── 8. RACE_PREDICTOR.HTML ────────────────────────────────────────────────────
n = patch(base+'race_predictor.html', [
    ('>Condiciones de Carrera<', ' data-i18n="pred_conditions">Condiciones de Carrera<'),
    ('>Condición del Día (TSB)<',' data-i18n="pred_tsb">Condición del Día (TSB)<'),
    ('>Ambiente &amp; Terreno<', ' data-i18n="pred_weather">Ambiente &amp; Terreno<'),
    ('>Temperatura<',            ' data-i18n="pred_temp">Temperatura<'),
    ('>Viento<',                 ' data-i18n="pred_wind">Viento<'),
    ('>Altimetría Bici<',        ' data-i18n="pred_altitude">Altimetría Bici<'),
    ('>Agua<',                   ' data-i18n="pred_water">Agua<'),
    ('>Splits Predichos<',       ' data-i18n="pred_splits">Splits Predichos<'),
    ('>Aplicar<',                ' data-i18n="btn_apply">Aplicar<'),
])
report['race_predictor.html'] = report.get('race_predictor.html',0)+n

# ── 9. BLOOD_LABS.HTML — section labels ──────────────────────────────────────
n = patch(base+'blood_labs.html', [
    ('>Hemograma<',              ' data-i18n="labs_hemo">Hemograma<'),
    ('>Muscular<',               ' data-i18n="labs_muscle">Muscular<'),
    ('>Lípidos<',                ' data-i18n="labs_lipids">Lípidos<'),
    ('>Vitaminas<',              ' data-i18n="labs_vitamins">Vitaminas<'),
    ('>Renal<',                  ' data-i18n="labs_renal">Renal<'),
    ('>Hormonal<',               ' data-i18n="labs_hormonal">Hormonal<'),
    ('>Electrolitos<',           ' data-i18n="labs_electrolytes">Electrolitos<'),
    ('>Fecha del examen<',       ' data-i18n="labs_date">Fecha del examen<'),
    ('>Laboratorio<',            ' data-i18n="labs_lab">Laboratorio<'),
    ('>Contexto / Motivo<',      ' data-i18n="labs_context">Contexto / Motivo<'),
    ('>Guardar Examen<',         ' data-i18n="btn_save_exam">Guardar Examen<'),
])
report['blood_labs.html'] = report.get('blood_labs.html',0)+n

# ── 10. COACH.HTML — section/tab labels ──────────────────────────────────────
n = patch(base+'coach.html', [
    ('>Resumen<',                ' data-i18n="tab_overview">Resumen<'),
    ('>Atletas<',                ' data-i18n="tab_athletes">Atletas<'),
    ('>Grupos<',                 ' data-i18n="tab_groups">Grupos<'),
    ('>Entrenamientos<',         ' data-i18n="tab_workouts">Entrenamientos<'),
    ('>Planificación<',          ' data-i18n="tab_planning">Planificación<'),
    ('>Cumplimiento<',           ' data-i18n="tab_compliance">Cumplimiento<'),
    ('>Reportes<',               ' data-i18n="tab_reports">Reportes<'),
    ('>Atletas del equipo<',     ' data-i18n="sec_team_athletes">Atletas del equipo<'),
    ('>Asignar Entrenamiento<',  ' data-i18n="sec_assign_workout">Asignar Entrenamiento<'),
    ('>Nuevo Atleta<',           ' data-i18n="btn_new_athlete">Nuevo Atleta<'),
    ('>Nuevo Grupo<',            ' data-i18n="btn_new_group">Nuevo Grupo<'),
    ('>Nuevo Template<',         ' data-i18n="btn_new_template">Nuevo Template<'),
    ('>Guardar cambios<',        ' data-i18n="btn_save_changes">Guardar cambios<'),
    ('>Cerrar<',                 ' data-i18n="btn_close">Cerrar<'),
    ('>Asignar<',                ' data-i18n="btn_assign">Asignar<'),
    ('>Vista Equipo<',           ' data-i18n="tab_team_view">Vista Equipo<'),
    ('>Alertas de Bienestar<',   ' data-i18n="sec_wellness_alerts">Alertas de Bienestar<'),
])
report['coach.html'] = report.get('coach.html',0)+n

# ── 11. ADD app_tagline KEY to i18n.js ────────────────────────────────────────
with open(base+'i18n.js', encoding='utf-8') as f:
    js = f.read()

new_keys = {
    'es': "    app_tagline: 'Where Champions Are Built',",
    'pt': "    app_tagline: 'Where Champions Are Built',",
    'en': "    app_tagline: 'Where Champions Are Built',",
}
anchors = {
    'es': "    nav_dashboard: 'Dashboard',",
    'pt': "    nav_dashboard: 'Painel',",
    'en': "    nav_dashboard: 'Dashboard',",
}

for lang, anchor in anchors.items():
    key_line = new_keys[lang]
    if anchor in js and key_line.strip() not in js:
        js = js.replace(anchor, key_line + '\n' + anchor, 1)
        print(f'OK app_tagline added to {lang}')

# Also add detalle-specific keys
extra_keys_per_lang = {
    'es': [
        "    det_current_val: 'Valor actual',",
        "    det_last_record: 'Último registro',",
        "    det_energy: 'Energía disponible',",
        "    det_muscle_fatigue: 'Fatiga Muscular (TSB)',",
    ],
    'pt': [
        "    det_current_val: 'Valor atual',",
        "    det_last_record: 'Último registro',",
        "    det_energy: 'Energia disponível',",
        "    det_muscle_fatigue: 'Fadiga Muscular (TSB)',",
    ],
    'en': [
        "    det_current_val: 'Current value',",
        "    det_last_record: 'Last record',",
        "    det_energy: 'Available energy',",
        "    det_muscle_fatigue: 'Muscle Fatigue (TSB)',",
    ],
}

anchors2 = {
    'es': "    app_tagline: 'Where Champions Are Built',",
    'pt': "    app_tagline: 'Where Champions Are Built',",
    'en': "    app_tagline: 'Where Champions Are Built',",
}

for lang, keys in extra_keys_per_lang.items():
    anchor = anchors2[lang]
    for key_line in keys:
        key_name = key_line.split(':')[0].strip()
        if key_name not in js and anchor in js:
            js = js.replace(anchor, anchor + '\n' + key_line, 1)

with open(base+'i18n.js', 'w', encoding='utf-8') as f:
    f.write(js)
print('Saved i18n.js with new keys')

# ── FINAL REPORT ──────────────────────────────────────────────────────────────
print('\n=== Changes per page ===')
for page, n in sorted(report.items()):
    if n > 0: print(f'  {page:<35} +{n}')

# Final attr counts
print('\n=== Final data-i18n counts ===')
pages = sorted([f for f in os.listdir(base) if f.endswith('.html')])
for p in pages:
    t = open(base+p, encoding='utf-8').read()
    n = len(re.findall(r'data-i18n', t))
    print(f'  {p:<35} {n:>4}')
