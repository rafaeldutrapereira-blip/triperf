import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
with open('C:/Users/rafae/projects/LabX/i18n.js', encoding='utf-8') as f:
    c = f.read()

NEW_ES = (
    "\n    /* Navegacion landing */\n"
    "    nav_disciplines: 'Disciplinas', nav_races: 'Carreras', nav_plans: 'Planes',\n"
    "    nav_metrics: 'Metricas', nav_contact: 'Contacto', nav_access: 'Acceder',\n"
    "    /* Filtros calendario */\n"
    "    filter_all: 'Todas', filter_marathon: '\U0001f3c5 Maratón', filter_triathlon: '\U0001f3c6 Triatlón',\n"
    "    /* Formulario contacto */\n"
    "    form_interest: 'Interés', btn_send_msg: 'Enviar mensaje',\n"
    "    /* Blood Labs */\n"
    "    labs_summary: '\U0001f4ca Resumen Clínico', labs_trends: '\U0001f4c8 Tendencias',\n"
    "    labs_garmin_corr: '\U0001f517 Correlación Garmin', btn_register_exam: '\U0001f4e5 Registrar Examen',\n"
    "    btn_add_exam: '+ Registrar Examen', btn_save_exam: '\U0001f4be Guardar Examen', btn_clear: '✕ Limpiar',\n"
    "    labs_hemo: '\U0001f9b8 Hemograma', labs_muscle: '\U0001f4aa Muscular', labs_lipids: '\U0001fac0 Lípidos',\n"
    "    labs_vitamins: '\U0001f31f Vitaminas', labs_renal: '\U0001fad8 Renal', labs_hormonal: '\U0001f9ea Hormonal',\n"
    "    labs_electrolytes: '⚡ Electrolitos',\n"
    "    labs_date: 'Fecha del examen', labs_lab: 'Laboratorio', labs_context: 'Contexto / Motivo',\n"
    "    /* Nutricion */\n"
    "    nutr_sprint: '⚡ Sprint', nutr_olympic: '\U0001f3ca Olímpico', nutr_703: '\U0001f30a 70.3',\n"
    "    nutr_ironman: '\U0001f525 Ironman', nutr_summary: '\U0001f4ca Resumen',\n"
    "    nutr_plan: '\U0001f4cb Plan Hora a Hora', nutr_prerace: '\U0001f4cb Pre-Carrera',\n"
    "    /* Plan entrenamiento */\n"
    "    tp_discipline: 'Disciplina', tp_session_name: 'Nombre de la sesión',\n"
    "    tp_duration: 'Duración (min)', tp_distance: 'Distancia (km)',\n"
    "    tp_tss_target: 'TSS Objetivo', tp_notes_inst: 'Notas / Instrucciones',\n"
    "    tp_tss_real: 'TSS Real', btn_save_session: 'Guardar Sesión',\n"
    "    btn_send_garmin: 'Enviar a Garmin Connect',\n"
    "    btn_save_result: 'Guardar resultado', btn_register_result: 'Registrar resultado',\n"
    "    /* Predictor */\n"
    "    pred_conditions: 'Condiciones de Carrera', pred_tsb: 'Condición del Día (TSB)',\n"
    "    pred_weather: 'Ambiente & Terreno', pred_temp: 'Temperatura',\n"
    "    pred_wind: 'Viento', pred_altitude: 'Altimetría Bici',\n"
    "    pred_water: 'Agua', pred_splits: 'Splits Predichos',\n"
    "    /* Reset */\n"
    "    form_email_account: 'Email de tu cuenta',\n"
    "    btn_send_reset: 'Enviar link de recuperación', btn_update_password: 'Actualizar contraseña',\n"
    "    /* Perfil */\n"
    "    prof_identification: 'Identificación', prof_physical: 'Datos Físicos',\n"
    "    prof_power_cardio: 'Potencia y Cardio', prof_thresholds: 'Ritmos Umbral',\n"
    "    prof_season_goal: 'Objetivo Temporada',\n"
    "    /* Labels */\n"
    "    lbl_week: 'Semana', lbl_3months: '3 Meses', lbl_6months: '6 Meses',\n"
    "    lbl_1year: '1 Año', lbl_all_time: 'Todo',\n"
    "    lbl_from: 'Desde', lbl_to: 'Hasta',\n"
    "    btn_apply: 'Aplicar', btn_update_plan: 'Actualizar Plan',\n"
    "    btn_view_history: 'Ver histórico →', kpi_sleep: 'Sueño', kpi_hr_rest: 'FC Reposo',\n"
    "    /* 404 */\n"
    "    notfound_title: 'Página no encontrada',\n"
    "    notfound_go_dash: 'Ir al Dashboard', notfound_go_home: 'Inicio',\n"
    "    perf_indicator: 'INDICADOR DE RENDIMIENTO',"
)

NEW_PT = (
    "\n    /* Navegacao landing */\n"
    "    nav_disciplines: 'Disciplinas', nav_races: 'Corridas', nav_plans: 'Planos',\n"
    "    nav_metrics: 'Métricas', nav_contact: 'Contato', nav_access: 'Entrar',\n"
    "    filter_all: 'Todas', filter_marathon: '\U0001f3c5 Maratona', filter_triathlon: '\U0001f3c6 Triatlo',\n"
    "    form_interest: 'Interesse', btn_send_msg: 'Enviar mensagem',\n"
    "    labs_summary: '\U0001f4ca Resumo Clínico', labs_trends: '\U0001f4c8 Tendências',\n"
    "    labs_garmin_corr: '\U0001f517 Correlação Garmin', btn_register_exam: '\U0001f4e5 Registrar Exame',\n"
    "    btn_add_exam: '+ Registrar Exame', btn_save_exam: '\U0001f4be Salvar Exame', btn_clear: '✕ Limpar',\n"
    "    labs_hemo: '\U0001f9b8 Hemograma', labs_muscle: '\U0001f4aa Muscular', labs_lipids: '\U0001fac0 Lipídios',\n"
    "    labs_vitamins: '\U0001f31f Vitaminas', labs_renal: '\U0001fad8 Renal', labs_hormonal: '\U0001f9ea Hormonal',\n"
    "    labs_electrolytes: '⚡ Eletrólitos',\n"
    "    labs_date: 'Data do exame', labs_lab: 'Laboratório', labs_context: 'Contexto / Motivo',\n"
    "    nutr_sprint: '⚡ Sprint', nutr_olympic: '\U0001f3ca Olímpico', nutr_703: '\U0001f30a 70.3',\n"
    "    nutr_ironman: '\U0001f525 Ironman', nutr_summary: '\U0001f4ca Resumo',\n"
    "    nutr_plan: '\U0001f4cb Plano Hora a Hora', nutr_prerace: '\U0001f4cb Pré-Corrida',\n"
    "    tp_discipline: 'Disciplina', tp_session_name: 'Nome da sessão',\n"
    "    tp_duration: 'Duração (min)', tp_distance: 'Distância (km)',\n"
    "    tp_tss_target: 'TSS Alvo', tp_notes_inst: 'Notas / Instruções',\n"
    "    tp_tss_real: 'TSS Real', btn_save_session: 'Salvar Sessão',\n"
    "    btn_send_garmin: 'Enviar ao Garmin Connect',\n"
    "    btn_save_result: 'Salvar resultado', btn_register_result: 'Registrar resultado',\n"
    "    pred_conditions: 'Condições de Corrida', pred_tsb: 'Condição do Dia (TSB)',\n"
    "    pred_weather: 'Ambiente & Terreno', pred_temp: 'Temperatura',\n"
    "    pred_wind: 'Vento', pred_altitude: 'Altimetria Bici',\n"
    "    pred_water: 'Água', pred_splits: 'Splits Previstos',\n"
    "    form_email_account: 'Email da sua conta',\n"
    "    btn_send_reset: 'Enviar link de recuperação', btn_update_password: 'Atualizar senha',\n"
    "    prof_identification: 'Identificação', prof_physical: 'Dados Físicos',\n"
    "    prof_power_cardio: 'Potência e Cardio', prof_thresholds: 'Ritmos Limiar',\n"
    "    prof_season_goal: 'Objetivo da Temporada',\n"
    "    lbl_week: 'Semana', lbl_3months: '3 Meses', lbl_6months: '6 Meses',\n"
    "    lbl_1year: '1 Ano', lbl_all_time: 'Tudo',\n"
    "    lbl_from: 'De', lbl_to: 'Até',\n"
    "    btn_apply: 'Aplicar', btn_update_plan: 'Atualizar Plano',\n"
    "    btn_view_history: 'Ver histórico →', kpi_sleep: 'Sono', kpi_hr_rest: 'FC Repouso',\n"
    "    notfound_title: 'Página não encontrada',\n"
    "    notfound_go_dash: 'Ir ao Painel', notfound_go_home: 'Início',\n"
    "    perf_indicator: 'INDICADOR DE DESEMPENHO',"
)

NEW_EN = (
    "\n    /* Landing nav */\n"
    "    nav_disciplines: 'Disciplines', nav_races: 'Races', nav_plans: 'Plans',\n"
    "    nav_metrics: 'Metrics', nav_contact: 'Contact', nav_access: 'Log in',\n"
    "    filter_all: 'All', filter_marathon: '\U0001f3c5 Marathon', filter_triathlon: '\U0001f3c6 Triathlon',\n"
    "    form_interest: 'Interest', btn_send_msg: 'Send message',\n"
    "    labs_summary: '\U0001f4ca Clinical Summary', labs_trends: '\U0001f4c8 Trends',\n"
    "    labs_garmin_corr: '\U0001f517 Garmin Correlation', btn_register_exam: '\U0001f4e5 Register Exam',\n"
    "    btn_add_exam: '+ Register Exam', btn_save_exam: '\U0001f4be Save Exam', btn_clear: '✕ Clear',\n"
    "    labs_hemo: '\U0001f9b8 Blood Count', labs_muscle: '\U0001f4aa Muscular', labs_lipids: '\U0001fac0 Lipids',\n"
    "    labs_vitamins: '\U0001f31f Vitamins', labs_renal: '\U0001fad8 Renal', labs_hormonal: '\U0001f9ea Hormonal',\n"
    "    labs_electrolytes: '⚡ Electrolytes',\n"
    "    labs_date: 'Exam Date', labs_lab: 'Laboratory', labs_context: 'Context / Reason',\n"
    "    nutr_sprint: '⚡ Sprint', nutr_olympic: '\U0001f3ca Olympic', nutr_703: '\U0001f30a 70.3',\n"
    "    nutr_ironman: '\U0001f525 Ironman', nutr_summary: '\U0001f4ca Summary',\n"
    "    nutr_plan: '\U0001f4cb Hour-by-Hour Plan', nutr_prerace: '\U0001f4cb Pre-Race',\n"
    "    tp_discipline: 'Discipline', tp_session_name: 'Session Name',\n"
    "    tp_duration: 'Duration (min)', tp_distance: 'Distance (km)',\n"
    "    tp_tss_target: 'Target TSS', tp_notes_inst: 'Notes / Instructions',\n"
    "    tp_tss_real: 'Actual TSS', btn_save_session: 'Save Session',\n"
    "    btn_send_garmin: 'Send to Garmin Connect',\n"
    "    btn_save_result: 'Save result', btn_register_result: 'Register result',\n"
    "    pred_conditions: 'Race Conditions', pred_tsb: 'Day Condition (TSB)',\n"
    "    pred_weather: 'Weather & Terrain', pred_temp: 'Temperature',\n"
    "    pred_wind: 'Wind', pred_altitude: 'Bike Elevation',\n"
    "    pred_water: 'Water', pred_splits: 'Predicted Splits',\n"
    "    form_email_account: 'Account email',\n"
    "    btn_send_reset: 'Send recovery link', btn_update_password: 'Update password',\n"
    "    prof_identification: 'Identification', prof_physical: 'Physical Data',\n"
    "    prof_power_cardio: 'Power & Cardio', prof_thresholds: 'Threshold Paces',\n"
    "    prof_season_goal: 'Season Goal',\n"
    "    lbl_week: 'Week', lbl_3months: '3 Months', lbl_6months: '6 Months',\n"
    "    lbl_1year: '1 Year', lbl_all_time: 'All',\n"
    "    lbl_from: 'From', lbl_to: 'To',\n"
    "    btn_apply: 'Apply', btn_update_plan: 'Update Plan',\n"
    "    btn_view_history: 'View history →', kpi_sleep: 'Sleep', kpi_hr_rest: 'Resting HR',\n"
    "    notfound_title: 'Page not found',\n"
    "    notfound_go_dash: 'Go to Dashboard', notfound_go_home: 'Home',\n"
    "    perf_indicator: 'PERFORMANCE INDICATOR',"
)

ES_END = "    reg_have_account: '¿Ya tienes cuenta?',\n  },"
PT_END = "    reg_have_account: 'Já tem conta?',\n  },"
EN_END = "    reg_have_account: 'Already have an account?',\n  }"

if ES_END in c:
    c = c.replace(ES_END, NEW_ES + '\n' + ES_END)
    print('OK ES')
else:
    print('MISS ES')

if PT_END in c:
    c = c.replace(PT_END, NEW_PT + '\n' + PT_END)
    print('OK PT')
else:
    print('MISS PT')

if EN_END in c:
    c = c.replace(EN_END, NEW_EN + '\n' + EN_END)
    print('OK EN')
else:
    print('MISS EN')

with open('C:/Users/rafae/projects/LabX/i18n.js', 'w', encoding='utf-8') as f:
    f.write(c)
print('Saved i18n.js')
