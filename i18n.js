/* LabX i18n — ES / PT / EN
   Uso:
     data-i18n="key"             → textContent
     data-i18n-html="key"        → innerHTML (para emojis + HTML)
     data-i18n-placeholder="key" → placeholder
     data-i18n-title="key"       → title attr
     window.i18n.t('key')        → JS traducción
     window.i18n.lang            → idioma actual
     window.i18n.set('pt')       → cambiar idioma
     window.i18n.registerChart(id, instance, fn) → traducción automática de charts
*/
(function () {

/* ─────────────────────────── DICCIONARIO ─────────────────────────── */
var DICT = {
  es: {
    /* Navegación */
    ath_portal: 'Portal Atleta',
    ath_activities: 'Actividades Garmin',
    app_tagline: 'Where Champions Are Built',
    det_muscle_fatigue: 'Fatiga Muscular (TSB)',
    det_energy: 'Energía disponible',
    det_last_record: 'Último registro',
    det_current_val: 'Valor actual',
    td_zones: 'Distribución de Zonas',

    nav_dashboard: 'Dashboard', nav_plan: 'Mi Plan', nav_profile: 'Mi Perfil',
    nav_nutrition: 'Nutrición', nav_labs: 'Labs', nav_predictor: 'Predictor',
    nav_session: 'Sesión', nav_coach: 'Coach', nav_garmin: 'Garmin',
    nav_logout: 'Cerrar sesión', nav_team: 'Equipo', nav_training: 'Entrenamiento',
    nav_wellness: 'Bienestar', nav_modules: 'Módulos',
    nav_group_daily: 'Uso diario', nav_group_health: 'Seguimiento y salud',
    nav_group_goal: 'Objetivo y comunidad', nav_group_tools: 'Herramientas',
    nav_group_account: 'Cuenta', nav_mobile_app: 'App Móvil',
    /* Tabs coach */
    tab_overview: 'Resumen', tab_athletes: 'Atletas', tab_groups: 'Grupos',
    tab_workouts: 'Entrenamientos', tab_planning: 'Planificación',
    tab_compliance: 'Cumplimiento', tab_team_view: 'Vista Equipo',
    tab_reports: 'Reportes', tab_macrocycles: '📋 Macrociclos',
    tab_assign: 'Asignar',
    /* Tabs athlete/dashboard */
    tab_garmin_acts: 'Actividades Garmin', tab_my_plan: 'Mi Plan',
    tab_my_profile: 'Mi Perfil',
    /* Botones */
    btn_save: 'Guardar', btn_cancel: 'Cancelar', btn_add: 'Agregar',
    btn_delete: 'Eliminar', btn_close: 'Cerrar', btn_edit: 'Editar',
    btn_new_athlete: 'Nuevo Atleta', btn_new_group: 'Nuevo Grupo',
    btn_new_template: 'Nuevo Template', btn_create_group: 'Crear Grupo',
    btn_save_changes: 'Guardar cambios', btn_assign: 'Asignar',
    btn_connect_garmin: 'Conectar Garmin', btn_disconnect_garmin: 'Desconectar',
    btn_sync_garmin: 'Sincronizar Garmin', btn_filter: 'Filtrar',
    btn_login: 'Ingresar a LabX', btn_register: 'Crear mi cuenta gratis',
    btn_forgot: '¿Olvidaste tu contraseña?', btn_back_login: 'Volver al login',
    btn_send_link: 'Enviar enlace', btn_reset_password: 'Cambiar contraseña',
    btn_prev: '◀ Anterior', btn_next: 'Siguiente ▶',
    btn_choose_plan: 'Elegir',
    /* Wellness */
    wellness_title: '¿Cómo te sientes hoy?', wellness_fatigue: 'Fatiga',
    wellness_sleep: 'Calidad sueño', wellness_soreness: 'Dolor muscular',
    wellness_mood: 'Estado ánimo', wellness_weight: 'Peso kg',
    wellness_scale: '1 = bajo / 5 = alto', wellness_notes: 'Notas adicionales...',
    wellness_save: 'Guardar bienestar',
    /* Secciones */
    sec_team_athletes: 'Atletas del equipo', sec_assign_workout: 'Asignar Entrenamiento',
    sec_recent_assignments: 'Asignaciones recientes', sec_wellness_alerts: 'Alertas de Bienestar',
    sec_garmin_conn: 'Conexión Garmin', sec_target_race: 'Carrera objetivo',
    sec_upcoming: 'Próximas sesiones', sec_my_data: 'Mis datos',
    sec_bienestar: 'Bienestar', sec_overview: 'Resumen General',
    /* KPIs */
    kpi_fitness: 'Forma', kpi_fatigue: 'Fatiga', kpi_form: 'Frescura',
    kpi_load: 'Carga', kpi_volume: 'Volumen', kpi_tss_week: 'TSS Semana',
    kpi_next_race: 'Próx. carrera', kpi_compliance: 'Cumplimiento',
    kpi_readiness: 'Readiness', kpi_hrv: 'HRV Score', kpi_vo2: 'VO2 Max',
    kpi_acwr: 'ACWR',
    /* Formularios */
    form_email: 'Email', form_password: 'Contraseña', form_name: 'Nombre completo',
    form_confirm_password: 'Confirmar contraseña',
    form_remember: 'Recordar sesión en este dispositivo',
    form_new_password: 'Nueva contraseña', form_confirm_new: 'Confirmar nueva contraseña',
    ph_email: 'tu@email.com', ph_password: '••••••••',
    ph_name: 'Tu nombre completo', ph_notes: 'Notas para el atleta...',
    ph_weight: '70.5', ph_wellness_notes: 'Notas adicionales...',
    ph_group_name: 'Nombre del grupo', ph_group_desc: 'Descripción...',
    /* Auth */
    auth_private: 'Acceso Privado',
    auth_credentials: 'Ingresa tus credenciales para continuar',
    auth_error: 'Usuario o contraseña incorrectos',
    auth_no_account: '¿No tienes cuenta?', auth_have_account: '¿Ya tienes cuenta?',
    auth_register: 'Regístrate', auth_login: 'Inicia sesión',
    auth_reset_sent: 'Enlace enviado, revisa tu email',
    auth_reset_success: 'Contraseña actualizada correctamente',
    /* Fortaleza contraseña */
    pwd_very_weak: 'Muy débil', pwd_weak: 'Débil', pwd_good: 'Buena', pwd_excellent: 'Excelente',
    /* Planes */
    plan_basic: 'Atleta', plan_pro: 'Agegroup', plan_elite: 'Elite', plan_coach: 'Coach',
    plan_free: 'Atleta', plan_popular: 'Más popular', plan_current: 'Plan actual',
    plan_per_day: '/día', plan_per_month: '/mes', plan_manages: 'gestiona 50+ atletas',
    plan_unlock_title: 'Desbloquea tu Potencial',
    plan_unlock_sub: 'Elige el plan que mejor se adapta a tu entrenamiento',
    plan_secure: '🔒 Pago seguro via Stripe · Cancela cuando quieras · Sin permanencia',
    /* Estado */
    status_loading: 'Cargando...', status_no_data: 'Sin datos',
    status_error: 'Error al cargar', status_saved: 'Guardado ✓',
    status_ok: 'OK', status_alert: 'Alerta', status_moderate: 'Moderado',
    /* Coach */
    coach_garmin_ok: '● Garmin conectado', coach_no_garmin: '○ Sin Garmin',
    coach_garmin_in: '● en Garmin', coach_garmin_sys: '○ solo sistema',
    coach_linked: '✓ Cuenta vinculada:', coach_bienestar_col: 'Bienestar',
    coach_days_ago: 'd atrás', coach_today: 'hoy',
    /* Notas */
    note_observation: '📝 Observación', note_goal: 'Meta',
    note_race: '🏃 Carrera', note_injury: 'Lesión',
    /* Select opciones */
    opt_all: 'Todos', opt_swim: 'Natación', opt_bike: 'Ciclismo',
    opt_run: 'Carrera', opt_strength: 'Fuerza', opt_all_sports: 'Todos los deportes',
    /* Landing */
    landing_hero_badge: 'Plataforma de triatlón — IA + Garmin',
    landing_hero_cta: 'Empieza gratis', landing_start_free: 'Empieza gratis',
    landing_no_card: 'Sin tarjeta de crédito',
    /* Registro */
    reg_title: 'Crea tu cuenta', reg_free_badge: 'Plan Básico gratuito incluido',
    reg_no_card: 'Empieza gratis · Sin tarjeta de crédito',
    /* Navegación landing */
    nav_disciplines: 'Disciplinas', nav_races: 'Carreras', nav_plans: 'Planes',
    nav_metrics: 'Metricas', nav_contact: 'Contacto', nav_access: 'Acceder',
    /* Filtros calendario */
    filter_all: 'Todas', filter_marathon: '🏅 Maratón', filter_triathlon: '🏆 Triatlón',
    /* Formulario contacto */
    form_interest: 'Interés', btn_send_msg: 'Enviar mensaje',
    /* Blood Labs */
    labs_summary: '📊 Resumen Clínico', labs_trends: '📈 Tendencias',
    labs_garmin_corr: '🔗 Correlación Garmin', btn_register_exam: '📥 Registrar Examen',
    btn_add_exam: '+ Registrar Examen', btn_save_exam: '💾 Guardar Examen', btn_clear: '✕ Limpiar',
    labs_hemo: '🦸 Hemograma', labs_muscle: '💪 Muscular', labs_lipids: '🫀 Lípidos',
    labs_vitamins: '🌟 Vitaminas', labs_renal: '🫘 Renal', labs_hormonal: '🧪 Hormonal',
    labs_electrolytes: '⚡ Electrolitos',
    labs_date: 'Fecha del examen', labs_lab: 'Laboratorio', labs_context: 'Contexto / Motivo',
    /* Charts Blood Labs */
    chart_radar_o2: 'Transporte O₂', chart_radar_recovery: 'Recuperación',
    chart_radar_vitamins: 'Vitaminas', chart_radar_metabolism: 'Metabolismo',
    chart_radar_lipids: 'Lípidos', chart_radar_renal: 'Renal',
    chart_radar_hormonal: 'Hormonal',
    chart_tss_swim: 'Natación', chart_tss_bike: 'Ciclismo',
    chart_tss_run: 'Carrera', chart_tss_str: 'Fuerza',
    chart_pmc_ctl: 'CTL — Forma', chart_pmc_atl: 'ATL — Fatiga', chart_pmc_tsb: 'TSB — Balance',
    chart_pmc_x: 'Semana', chart_pmc_y: 'Carga',
    chart_score_current: 'Examen actual', chart_score_prev: 'Examen anterior',
    chart_score_optimal: 'Óptimo',
    chart_trend_label: 'Valor', chart_trend_ref_low: 'Ref. mínimo', chart_trend_ref_high: 'Ref. máximo',
    /* Nutricion */
    nutr_sprint: '⚡ Sprint', nutr_olympic: '🏊 Olímpico', nutr_703: '🌊 70.3',
    nutr_ironman: '🔥 Ironman', nutr_summary: '📊 Resumen',
    nutr_plan: '📋 Plan Hora a Hora', nutr_prerace: '📋 Pre-Carrera',
    nutr_cho: 'Carbohidratos', nutr_pro: 'Proteínas', nutr_fat: 'Grasas',
    nutr_kcal: 'Calorías', nutr_fluid: 'Líquidos',
    /* Plan entrenamiento */
    tp_discipline: 'Disciplina', tp_session_name: 'Nombre de la sesión',
    tp_duration: 'Duración (min)', tp_distance: 'Distancia (km)',
    tp_tss_target: 'TSS Objetivo', tp_notes_inst: 'Notas / Instrucciones',
    tp_tss_real: 'TSS Real', btn_save_session: 'Guardar Sesión',
    btn_send_garmin: 'Enviar a Garmin Connect',
    btn_save_result: 'Guardar resultado', btn_register_result: 'Registrar resultado',
    /* Predictor */
    pred_conditions: 'Condiciones de Carrera', pred_tsb: 'Condición del Día (TSB)',
    pred_weather: 'Ambiente & Terreno', pred_temp: 'Temperatura',
    pred_wind: 'Viento', pred_altitude: 'Altimetría Bici',
    pred_water: 'Agua', pred_splits: 'Splits Predichos',
    /* Reset */
    form_email_account: 'Email de tu cuenta',
    btn_send_reset: 'Enviar link de recuperación', btn_update_password: 'Actualizar contraseña',
    /* Perfil */
    prof_identification: 'Identificación', prof_physical: 'Datos Físicos',
    prof_power_cardio: 'Potencia y Cardio', prof_thresholds: 'Ritmos Umbral',
    prof_season_goal: 'Objetivo Temporada',
    /* Labels */
    lbl_week: 'Semana', lbl_3months: '3 Meses', lbl_6months: '6 Meses',
    lbl_1year: '1 Año', lbl_all_time: 'Todo',
    lbl_from: 'Desde', lbl_to: 'Hasta',
    btn_apply: 'Aplicar', btn_update_plan: 'Actualizar Plan',
    btn_view_history: 'Ver histórico →', kpi_sleep: 'Sueño', kpi_hr_rest: 'FC Reposo',
    /* Training detail */
    td_overview: 'Resumen', td_route: 'Ruta', td_laps: 'Parciales', td_hr: 'Frecuencia Cardíaca',
    td_power: 'Potencia', td_pace: 'Ritmo', td_elevation: 'Elevación',
    td_calories: 'Calorías', td_distance: 'Distancia', td_duration: 'Duración',
    td_avg_hr: 'FC Media', td_max_hr: 'FC Máxima', td_avg_power: 'Potencia Media',
    td_max_power: 'Potencia Máxima', td_avg_pace: 'Ritmo Medio', td_tss: 'TSS',
    td_back: '← Volver', td_replay: '▶ Replay',
    /* 404 */
    notfound_title: 'Página no encontrada',
    notfound_go_dash: 'Ir al Dashboard', notfound_go_home: 'Inicio',
    perf_indicator: 'INDICADOR DE RENDIMIENTO',
    det_hours: 'Horas',
    det_score: 'Score',
    det_body_bat: 'Body Battery',
    det_tsb_form: 'TSB (Forma)',
    reg_have_account: '¿Ya tienes cuenta?',
  },

  pt: {
    /* Navegação */
    ath_portal: 'Portal Atleta',
    ath_activities: 'Atividades Garmin',
    app_tagline: 'Where Champions Are Built',
    det_current_val: 'Valor atual',
    td_zones: 'Distribuição por Zonas',

    det_last_record: 'Último registro',
    det_energy: 'Energia disponível',
    det_muscle_fatigue: 'Fadiga Muscular (TSB)',
    nav_dashboard: 'Painel', nav_plan: 'Meu Plano', nav_profile: 'Meu Perfil',
    nav_nutrition: 'Nutrição', nav_labs: 'Laboratório', nav_predictor: 'Preditor',
    nav_session: 'Sessão', nav_coach: 'Coach', nav_garmin: 'Garmin',
    nav_logout: 'Sair', nav_team: 'Equipe', nav_training: 'Treino',
    nav_wellness: 'Bem-estar', nav_modules: 'Módulos',
    nav_group_daily: 'Uso diário', nav_group_health: 'Acompanhamento e saúde',
    nav_group_goal: 'Objetivo e comunidade', nav_group_tools: 'Ferramentas',
    nav_group_account: 'Conta', nav_mobile_app: 'App Mobile',
    tab_overview: 'Resumo', tab_athletes: 'Atletas', tab_groups: 'Grupos',
    tab_workouts: 'Treinos', tab_planning: 'Planejamento',
    tab_compliance: 'Aderência', tab_team_view: 'Vista do Time',
    tab_reports: 'Relatórios', tab_macrocycles: '📋 Macrociclos',
    tab_assign: 'Atribuir',
    tab_garmin_acts: 'Atividades Garmin', tab_my_plan: 'Meu Plano',
    tab_my_profile: 'Meu Perfil',
    btn_save: 'Salvar', btn_cancel: 'Cancelar', btn_add: 'Adicionar',
    btn_delete: 'Excluir', btn_close: 'Fechar', btn_edit: 'Editar',
    btn_new_athlete: 'Novo Atleta', btn_new_group: 'Novo Grupo',
    btn_new_template: 'Novo Template', btn_create_group: 'Criar Grupo',
    btn_save_changes: 'Salvar alterações', btn_assign: 'Atribuir',
    btn_connect_garmin: 'Conectar Garmin', btn_disconnect_garmin: 'Desconectar',
    btn_sync_garmin: 'Sincronizar Garmin', btn_filter: 'Filtrar',
    btn_login: 'Entrar no LabX', btn_register: 'Criar minha conta grátis',
    btn_forgot: 'Esqueceu a senha?', btn_back_login: 'Voltar ao login',
    btn_send_link: 'Enviar link', btn_reset_password: 'Alterar senha',
    btn_prev: '◀ Anterior', btn_next: 'Próximo ▶',
    btn_choose_plan: 'Escolher',
    wellness_title: 'Como você se sente hoje?', wellness_fatigue: 'Fadiga',
    wellness_sleep: 'Qualidade do sono', wellness_soreness: 'Dor muscular',
    wellness_mood: 'Humor', wellness_weight: 'Peso kg',
    wellness_scale: '1 = baixo / 5 = alto', wellness_notes: 'Notas adicionais...',
    wellness_save: 'Salvar bem-estar',
    sec_team_athletes: 'Atletas da equipe', sec_assign_workout: 'Atribuir Treino',
    sec_recent_assignments: 'Atribuições recentes', sec_wellness_alerts: 'Alertas de Bem-estar',
    sec_garmin_conn: 'Conexão Garmin', sec_target_race: 'Prova alvo',
    sec_upcoming: 'Próximas sessões', sec_my_data: 'Meus dados',
    sec_bienestar: 'Bem-estar', sec_overview: 'Resumo Geral',
    kpi_fitness: 'Forma', kpi_fatigue: 'Fadiga', kpi_form: 'Frescor',
    kpi_load: 'Carga', kpi_volume: 'Volume', kpi_tss_week: 'TSS Semana',
    kpi_next_race: 'Próx. prova', kpi_compliance: 'Aderência',
    kpi_readiness: 'Prontidão', kpi_hrv: 'HRV Score', kpi_vo2: 'VO2 Max',
    kpi_acwr: 'ACWR',
    form_email: 'Email', form_password: 'Senha', form_name: 'Nome completo',
    form_confirm_password: 'Confirmar senha',
    form_remember: 'Lembrar sessão neste dispositivo',
    form_new_password: 'Nova senha', form_confirm_new: 'Confirmar nova senha',
    ph_email: 'seu@email.com', ph_password: '••••••••',
    ph_name: 'Seu nome completo', ph_notes: 'Notas para o atleta...',
    ph_weight: '70.5', ph_wellness_notes: 'Notas adicionais...',
    ph_group_name: 'Nome do grupo', ph_group_desc: 'Descrição...',
    auth_private: 'Acesso Privado',
    auth_credentials: 'Insira suas credenciais para continuar',
    auth_error: 'Usuário ou senha incorretos',
    auth_no_account: 'Não tem conta?', auth_have_account: 'Já tem conta?',
    auth_register: 'Cadastre-se', auth_login: 'Fazer login',
    auth_reset_sent: 'Link enviado, verifique seu email',
    auth_reset_success: 'Senha atualizada com sucesso',
    pwd_very_weak: 'Muito fraca', pwd_weak: 'Fraca', pwd_good: 'Boa', pwd_excellent: 'Excelente',
    plan_basic: 'Atleta', plan_pro: 'Agegroup', plan_elite: 'Elite', plan_coach: 'Coach',
    plan_free: 'Atleta', plan_popular: 'Mais popular', plan_current: 'Plano atual',
    plan_per_day: '/dia', plan_per_month: '/mês', plan_manages: 'gerencia 50+ atletas',
    plan_unlock_title: 'Desbloqueie seu Potencial',
    plan_unlock_sub: 'Escolha o plano que melhor se adapta ao seu treino',
    plan_secure: '🔒 Pagamento seguro via Stripe · Cancele quando quiser · Sem fidelidade',
    status_loading: 'Carregando...', status_no_data: 'Sem dados',
    status_error: 'Erro ao carregar', status_saved: 'Salvo ✓',
    status_ok: 'OK', status_alert: 'Alerta', status_moderate: 'Moderado',
    coach_garmin_ok: '● Garmin conectado', coach_no_garmin: '○ Sem Garmin',
    coach_garmin_in: '● no Garmin', coach_garmin_sys: '○ só sistema',
    coach_linked: '✓ Conta vinculada:', coach_bienestar_col: 'Bem-estar',
    coach_days_ago: 'd atrás', coach_today: 'hoje',
    note_observation: '📝 Observação', note_goal: 'Meta',
    note_race: '🏃 Corrida', note_injury: 'Lesão',
    opt_all: 'Todos', opt_swim: 'Natação', opt_bike: 'Ciclismo',
    opt_run: 'Corrida', opt_strength: 'Força', opt_all_sports: 'Todos os esportes',
    landing_hero_badge: 'Plataforma de triatlo — IA + Garmin',
    landing_hero_cta: 'Comece grátis', landing_start_free: 'Comece grátis',
    landing_no_card: 'Sem cartão de crédito',
    reg_title: 'Crie sua conta', reg_free_badge: 'Plano Básico gratuito incluído',
    reg_no_card: 'Comece grátis · Sem cartão de crédito',
    nav_disciplines: 'Disciplinas', nav_races: 'Corridas', nav_plans: 'Planos',
    nav_metrics: 'Métricas', nav_contact: 'Contato', nav_access: 'Entrar',
    filter_all: 'Todas', filter_marathon: '🏅 Maratona', filter_triathlon: '🏆 Triatlo',
    form_interest: 'Interesse', btn_send_msg: 'Enviar mensagem',
    labs_summary: '📊 Resumo Clínico', labs_trends: '📈 Tendências',
    labs_garmin_corr: '🔗 Correlação Garmin', btn_register_exam: '📥 Registrar Exame',
    btn_add_exam: '+ Registrar Exame', btn_save_exam: '💾 Salvar Exame', btn_clear: '✕ Limpar',
    labs_hemo: '🦸 Hemograma', labs_muscle: '💪 Muscular', labs_lipids: '🫀 Lipídios',
    labs_vitamins: '🌟 Vitaminas', labs_renal: '🫘 Renal', labs_hormonal: '🧪 Hormonal',
    labs_electrolytes: '⚡ Eletrólitos',
    labs_date: 'Data do exame', labs_lab: 'Laboratório', labs_context: 'Contexto / Motivo',
    chart_radar_o2: 'Transporte O₂', chart_radar_recovery: 'Recuperação',
    chart_radar_vitamins: 'Vitaminas', chart_radar_metabolism: 'Metabolismo',
    chart_radar_lipids: 'Lipídios', chart_radar_renal: 'Renal',
    chart_radar_hormonal: 'Hormonal',
    chart_tss_swim: 'Natação', chart_tss_bike: 'Ciclismo',
    chart_tss_run: 'Corrida', chart_tss_str: 'Força',
    chart_pmc_ctl: 'CTL — Forma', chart_pmc_atl: 'ATL — Fadiga', chart_pmc_tsb: 'TSB — Balanço',
    chart_pmc_x: 'Semana', chart_pmc_y: 'Carga',
    chart_score_current: 'Exame atual', chart_score_prev: 'Exame anterior',
    chart_score_optimal: 'Ótimo',
    chart_trend_label: 'Valor', chart_trend_ref_low: 'Ref. mínimo', chart_trend_ref_high: 'Ref. máximo',
    nutr_sprint: '⚡ Sprint', nutr_olympic: '🏊 Olímpico', nutr_703: '🌊 70.3',
    nutr_ironman: '🔥 Ironman', nutr_summary: '📊 Resumo',
    nutr_plan: '📋 Plano Hora a Hora', nutr_prerace: '📋 Pré-Corrida',
    nutr_cho: 'Carboidratos', nutr_pro: 'Proteínas', nutr_fat: 'Gorduras',
    nutr_kcal: 'Calorias', nutr_fluid: 'Líquidos',
    tp_discipline: 'Disciplina', tp_session_name: 'Nome da sessão',
    tp_duration: 'Duração (min)', tp_distance: 'Distância (km)',
    tp_tss_target: 'TSS Alvo', tp_notes_inst: 'Notas / Instruções',
    tp_tss_real: 'TSS Real', btn_save_session: 'Salvar Sessão',
    btn_send_garmin: 'Enviar ao Garmin Connect',
    btn_save_result: 'Salvar resultado', btn_register_result: 'Registrar resultado',
    pred_conditions: 'Condições de Corrida', pred_tsb: 'Condição do Dia (TSB)',
    pred_weather: 'Ambiente & Terreno', pred_temp: 'Temperatura',
    pred_wind: 'Vento', pred_altitude: 'Altimetria Bici',
    pred_water: 'Água', pred_splits: 'Splits Previstos',
    form_email_account: 'Email da sua conta',
    btn_send_reset: 'Enviar link de recuperação', btn_update_password: 'Atualizar senha',
    prof_identification: 'Identificação', prof_physical: 'Dados Físicos',
    prof_power_cardio: 'Potência e Cardio', prof_thresholds: 'Ritmos Limiar',
    prof_season_goal: 'Objetivo da Temporada',
    lbl_week: 'Semana', lbl_3months: '3 Meses', lbl_6months: '6 Meses',
    lbl_1year: '1 Ano', lbl_all_time: 'Tudo',
    lbl_from: 'De', lbl_to: 'Até',
    btn_apply: 'Aplicar', btn_update_plan: 'Atualizar Plano',
    btn_view_history: 'Ver histórico →', kpi_sleep: 'Sono', kpi_hr_rest: 'FC Repouso',
    td_overview: 'Resumo', td_route: 'Rota', td_laps: 'Parciais', td_hr: 'Frequência Cardíaca',
    td_power: 'Potência', td_pace: 'Ritmo', td_elevation: 'Elevação',
    td_calories: 'Calorias', td_distance: 'Distância', td_duration: 'Duração',
    td_avg_hr: 'FC Média', td_max_hr: 'FC Máxima', td_avg_power: 'Potência Média',
    td_max_power: 'Potência Máxima', td_avg_pace: 'Ritmo Médio', td_tss: 'TSS',
    td_back: '← Voltar', td_replay: '▶ Replay',
    notfound_title: 'Página não encontrada',
    notfound_go_dash: 'Ir ao Painel', notfound_go_home: 'Início',
    perf_indicator: 'INDICADOR DE DESEMPENHO',
    det_hours: 'Horas',
    det_score: 'Score',
    det_body_bat: 'Body Battery',
    det_tsb_form: 'TSB (Forma)',
    reg_have_account: 'Já tem conta?',
  },

  en: {
    /* Navigation */
    ath_portal: 'Athlete Portal',
    ath_activities: 'Garmin Activities',
    app_tagline: 'Where Champions Are Built',
    det_current_val: 'Current value',
    td_zones: 'Zone Distribution',

    det_last_record: 'Last record',
    det_energy: 'Available energy',
    det_muscle_fatigue: 'Muscle Fatigue (TSB)',
    nav_dashboard: 'Dashboard', nav_plan: 'My Plan', nav_profile: 'My Profile',
    nav_nutrition: 'Nutrition', nav_labs: 'Lab Results', nav_predictor: 'Race Predictor',
    nav_session: 'Session', nav_coach: 'Coach', nav_garmin: 'Garmin',
    nav_logout: 'Log Out', nav_team: 'Team', nav_training: 'Training',
    nav_wellness: 'Wellness', nav_modules: 'Modules',
    nav_group_daily: 'Daily use', nav_group_health: 'Tracking & health',
    nav_group_goal: 'Goal & community', nav_group_tools: 'Tools',
    nav_group_account: 'Account', nav_mobile_app: 'Mobile App',
    tab_overview: 'Overview', tab_athletes: 'Athletes', tab_groups: 'Groups',
    tab_workouts: 'Workouts', tab_planning: 'Planning',
    tab_compliance: 'Compliance', tab_team_view: 'Team View',
    tab_reports: 'Reports', tab_macrocycles: '📋 Macrocycles',
    tab_assign: 'Assign',
    tab_garmin_acts: 'Garmin Activities', tab_my_plan: 'My Plan',
    tab_my_profile: 'My Profile',
    btn_save: 'Save', btn_cancel: 'Cancel', btn_add: 'Add',
    btn_delete: 'Delete', btn_close: 'Close', btn_edit: 'Edit',
    btn_new_athlete: 'New Athlete', btn_new_group: 'New Group',
    btn_new_template: 'New Template', btn_create_group: 'Create Group',
    btn_save_changes: 'Save Changes', btn_assign: 'Assign',
    btn_connect_garmin: 'Connect Garmin', btn_disconnect_garmin: 'Disconnect',
    btn_sync_garmin: 'Sync Garmin', btn_filter: 'Filter',
    btn_login: 'Enter LabX', btn_register: 'Create my free account',
    btn_forgot: 'Forgot your password?', btn_back_login: 'Back to login',
    btn_send_link: 'Send link', btn_reset_password: 'Reset password',
    btn_prev: '◀ Previous', btn_next: 'Next ▶',
    btn_choose_plan: 'Choose',
    wellness_title: 'How do you feel today?', wellness_fatigue: 'Fatigue',
    wellness_sleep: 'Sleep Quality', wellness_soreness: 'Muscle Soreness',
    wellness_mood: 'Mood', wellness_weight: 'Weight kg',
    wellness_scale: '1 = low / 5 = high', wellness_notes: 'Additional notes...',
    wellness_save: 'Save wellness',
    sec_team_athletes: 'Team Athletes', sec_assign_workout: 'Assign Workout',
    sec_recent_assignments: 'Recent Assignments', sec_wellness_alerts: 'Wellness Alerts',
    sec_garmin_conn: 'Garmin Connection', sec_target_race: 'Target Race',
    sec_upcoming: 'Upcoming Sessions', sec_my_data: 'My Data',
    sec_bienestar: 'Wellness', sec_overview: 'General Overview',
    kpi_fitness: 'Fitness', kpi_fatigue: 'Fatigue', kpi_form: 'Form',
    kpi_load: 'Load', kpi_volume: 'Volume', kpi_tss_week: 'Weekly TSS',
    kpi_next_race: 'Next Race', kpi_compliance: 'Compliance',
    kpi_readiness: 'Readiness', kpi_hrv: 'HRV Score', kpi_vo2: 'VO2 Max',
    kpi_acwr: 'ACWR',
    form_email: 'Email', form_password: 'Password', form_name: 'Full Name',
    form_confirm_password: 'Confirm Password',
    form_remember: 'Remember session on this device',
    form_new_password: 'New password', form_confirm_new: 'Confirm new password',
    ph_email: 'you@email.com', ph_password: '••••••••',
    ph_name: 'Your full name', ph_notes: 'Notes for the athlete...',
    ph_weight: '70.5', ph_wellness_notes: 'Additional notes...',
    ph_group_name: 'Group name', ph_group_desc: 'Description...',
    auth_private: 'Private Access',
    auth_credentials: 'Enter your credentials to continue',
    auth_error: 'Wrong username or password',
    auth_no_account: "Don't have an account?", auth_have_account: 'Already have an account?',
    auth_register: 'Sign up', auth_login: 'Log in',
    auth_reset_sent: 'Link sent, check your email',
    auth_reset_success: 'Password updated successfully',
    pwd_very_weak: 'Very Weak', pwd_weak: 'Weak', pwd_good: 'Good', pwd_excellent: 'Excellent',
    plan_basic: 'Athlete', plan_pro: 'Agegroup', plan_elite: 'Elite', plan_coach: 'Coach',
    plan_free: 'Athlete', plan_popular: 'Most popular', plan_current: 'Current plan',
    plan_per_day: '/day', plan_per_month: '/mo', plan_manages: 'manages 50+ athletes',
    plan_unlock_title: 'Unlock your Potential',
    plan_unlock_sub: 'Choose the plan that best fits your training',
    plan_secure: '🔒 Secure payment via Stripe · Cancel anytime · No commitment',
    status_loading: 'Loading...', status_no_data: 'No data',
    status_error: 'Error loading', status_saved: 'Saved ✓',
    status_ok: 'OK', status_alert: 'Alert', status_moderate: 'Moderate',
    coach_garmin_ok: '● Garmin connected', coach_no_garmin: '○ No Garmin',
    coach_garmin_in: '● in Garmin', coach_garmin_sys: '○ system only',
    coach_linked: '✓ Linked account:', coach_bienestar_col: 'Wellness',
    coach_days_ago: 'd ago', coach_today: 'today',
    note_observation: '📝 Note', note_goal: 'Goal',
    note_race: '🏃 Race', note_injury: 'Injury',
    opt_all: 'All', opt_swim: 'Swimming', opt_bike: 'Cycling',
    opt_run: 'Running', opt_strength: 'Strength', opt_all_sports: 'All sports',
    landing_hero_badge: 'Triathlon platform — AI + Garmin',
    landing_hero_cta: 'Start free', landing_start_free: 'Start free',
    landing_no_card: 'No credit card required',
    reg_title: 'Create your account', reg_free_badge: 'Free Basic Plan included',
    reg_no_card: 'Start free · No credit card required',
    nav_disciplines: 'Disciplines', nav_races: 'Races', nav_plans: 'Plans',
    nav_metrics: 'Metrics', nav_contact: 'Contact', nav_access: 'Log in',
    filter_all: 'All', filter_marathon: '🏅 Marathon', filter_triathlon: '🏆 Triathlon',
    form_interest: 'Interest', btn_send_msg: 'Send message',
    labs_summary: '📊 Clinical Summary', labs_trends: '📈 Trends',
    labs_garmin_corr: '🔗 Garmin Correlation', btn_register_exam: '📥 Register Exam',
    btn_add_exam: '+ Register Exam', btn_save_exam: '💾 Save Exam', btn_clear: '✕ Clear',
    labs_hemo: '🦸 Blood Count', labs_muscle: '💪 Muscular', labs_lipids: '🫀 Lipids',
    labs_vitamins: '🌟 Vitamins', labs_renal: '🫘 Renal', labs_hormonal: '🧪 Hormonal',
    labs_electrolytes: '⚡ Electrolytes',
    labs_date: 'Exam Date', labs_lab: 'Laboratory', labs_context: 'Context / Reason',
    chart_radar_o2: 'O₂ Transport', chart_radar_recovery: 'Recovery',
    chart_radar_vitamins: 'Vitamins', chart_radar_metabolism: 'Metabolism',
    chart_radar_lipids: 'Lipids', chart_radar_renal: 'Renal',
    chart_radar_hormonal: 'Hormonal',
    chart_tss_swim: 'Swimming', chart_tss_bike: 'Cycling',
    chart_tss_run: 'Running', chart_tss_str: 'Strength',
    chart_pmc_ctl: 'CTL — Fitness', chart_pmc_atl: 'ATL — Fatigue', chart_pmc_tsb: 'TSB — Form',
    chart_pmc_x: 'Week', chart_pmc_y: 'Load',
    chart_score_current: 'Current exam', chart_score_prev: 'Previous exam',
    chart_score_optimal: 'Optimal',
    chart_trend_label: 'Value', chart_trend_ref_low: 'Min ref', chart_trend_ref_high: 'Max ref',
    nutr_sprint: '⚡ Sprint', nutr_olympic: '🏊 Olympic', nutr_703: '🌊 70.3',
    nutr_ironman: '🔥 Ironman', nutr_summary: '📊 Summary',
    nutr_plan: '📋 Hour-by-Hour Plan', nutr_prerace: '📋 Pre-Race',
    nutr_cho: 'Carbohydrates', nutr_pro: 'Proteins', nutr_fat: 'Fats',
    nutr_kcal: 'Calories', nutr_fluid: 'Fluids',
    tp_discipline: 'Discipline', tp_session_name: 'Session Name',
    tp_duration: 'Duration (min)', tp_distance: 'Distance (km)',
    tp_tss_target: 'Target TSS', tp_notes_inst: 'Notes / Instructions',
    tp_tss_real: 'Actual TSS', btn_save_session: 'Save Session',
    btn_send_garmin: 'Send to Garmin Connect',
    btn_save_result: 'Save result', btn_register_result: 'Register result',
    pred_conditions: 'Race Conditions', pred_tsb: 'Day Condition (TSB)',
    pred_weather: 'Weather & Terrain', pred_temp: 'Temperature',
    pred_wind: 'Wind', pred_altitude: 'Bike Elevation',
    pred_water: 'Water', pred_splits: 'Predicted Splits',
    form_email_account: 'Account email',
    btn_send_reset: 'Send recovery link', btn_update_password: 'Update password',
    prof_identification: 'Identification', prof_physical: 'Physical Data',
    prof_power_cardio: 'Power & Cardio', prof_thresholds: 'Threshold Paces',
    prof_season_goal: 'Season Goal',
    lbl_week: 'Week', lbl_3months: '3 Months', lbl_6months: '6 Months',
    lbl_1year: '1 Year', lbl_all_time: 'All',
    lbl_from: 'From', lbl_to: 'To',
    btn_apply: 'Apply', btn_update_plan: 'Update Plan',
    btn_view_history: 'View history →', kpi_sleep: 'Sleep', kpi_hr_rest: 'Resting HR',
    td_overview: 'Overview', td_route: 'Route', td_laps: 'Laps', td_hr: 'Heart Rate',
    td_power: 'Power', td_pace: 'Pace', td_elevation: 'Elevation',
    td_calories: 'Calories', td_distance: 'Distance', td_duration: 'Duration',
    td_avg_hr: 'Avg HR', td_max_hr: 'Max HR', td_avg_power: 'Avg Power',
    td_max_power: 'Max Power', td_avg_pace: 'Avg Pace', td_tss: 'TSS',
    td_back: '← Back', td_replay: '▶ Replay',
    notfound_title: 'Page not found',
    notfound_go_dash: 'Go to Dashboard', notfound_go_home: 'Home',
    perf_indicator: 'PERFORMANCE INDICATOR',
    det_hours: 'Hours',
    det_score: 'Score',
    det_body_bat: 'Body Battery',
    det_tsb_form: 'TSB (Form)',
    reg_have_account: 'Already have an account?',
  }
};

/* ─────────────────────────── ESTADO ─────────────────────────── */
var _lang = 'es'; /* i18n desactivado temporalmente — idioma fijo español */
var _chartRegistry = {};   /* id → { instance, getConfig } */

/* ─────────────────────────── HELPERS ─────────────────────────── */
function _t(key) {
  return (DICT[_lang] && DICT[_lang][key])
      || (DICT.es  && DICT.es[key])
      || key;
}

/* ─────────────────────────── DOM APPLY ─────────────────────────── */
function _applyDOM(lang) {
  var d = DICT[lang] || DICT.es;

  document.querySelectorAll('[data-i18n]').forEach(function(el) {
    var k = el.getAttribute('data-i18n');
    if (d[k] === undefined) return;
    /* Preserva iconos SVG o elementos hijos — actualiza solo nodos de texto */
    if (el.children.length && !el.getAttribute('data-i18n-html')) {
      Array.from(el.childNodes).forEach(function(node) {
        if (node.nodeType === 3 && node.textContent.trim()) node.textContent = d[k];
      });
    } else if (el.getAttribute('data-i18n-html')) {
      el.innerHTML = d[k];
    } else {
      el.textContent = d[k];
    }
  });

  document.querySelectorAll('[data-i18n-placeholder]').forEach(function(el) {
    var k = el.getAttribute('data-i18n-placeholder');
    if (d[k] !== undefined) el.placeholder = d[k];
  });

  document.querySelectorAll('[data-i18n-title]').forEach(function(el) {
    var k = el.getAttribute('data-i18n-title');
    if (d[k] !== undefined) el.title = d[k];
  });

  document.documentElement.lang = lang === 'pt' ? 'pt-BR' : lang === 'en' ? 'en' : 'es';
}

/* ─────────────────────────── CHART REGISTRY ─────────────────────────── */
function _applyCharts(lang) {
  Object.keys(_chartRegistry).forEach(function(id) {
    var entry = _chartRegistry[id];
    if (!entry || !entry.instance || entry.instance.destroyed) {
      delete _chartRegistry[id]; return;
    }
    var cfg = entry.getConfig(lang, _t);
    var inst = entry.instance;

    if (cfg.labels)       inst.data.labels = cfg.labels;
    if (cfg.datasetLabels) {
      cfg.datasetLabels.forEach(function(lbl, i) {
        if (inst.data.datasets[i]) inst.data.datasets[i].label = lbl;
      });
    }
    if (cfg.scaleLabels) {
      Object.keys(cfg.scaleLabels).forEach(function(axisId) {
        if (inst.options.scales && inst.options.scales[axisId] &&
            inst.options.scales[axisId].title) {
          inst.options.scales[axisId].title.text = cfg.scaleLabels[axisId];
        }
      });
    }
    if (cfg.title && inst.options.plugins && inst.options.plugins.title) {
      inst.options.plugins.title.text = cfg.title;
    }
    inst.update('none');
  });
}

/* ─────────────────────────── WIDGET ─────────────────────────── */
var svgES = '<svg width="22" height="16" viewBox="0 0 22 16" xmlns="http://www.w3.org/2000/svg">' +
  '<rect width="22" height="16" rx="2" fill="#c60b1e"/>' +
  '<rect y="4" width="22" height="8" fill="#ffc400"/>' +
  '</svg>';

var svgBR = '<svg width="22" height="16" viewBox="0 0 22 16" xmlns="http://www.w3.org/2000/svg">' +
  '<rect width="22" height="16" rx="2" fill="#009c3b"/>' +
  '<polygon points="11,1.5 20.5,8 11,14.5 1.5,8" fill="#ffdf00"/>' +
  '<circle cx="11" cy="8" r="3.5" fill="#002776"/>' +
  '</svg>';

var svgUK = '<svg width="22" height="16" viewBox="0 0 22 16" xmlns="http://www.w3.org/2000/svg">' +
  '<rect width="22" height="16" rx="2" fill="#012169"/>' +
  '<line x1="0" y1="0" x2="22" y2="16" stroke="#fff" stroke-width="3"/>' +
  '<line x1="22" y1="0" x2="0" y2="16" stroke="#fff" stroke-width="3"/>' +
  '<line x1="11" y1="0" x2="11" y2="16" stroke="#fff" stroke-width="5"/>' +
  '<line x1="0" y1="8" x2="22" y2="8" stroke="#fff" stroke-width="5"/>' +
  '<line x1="0" y1="0" x2="22" y2="16" stroke="#cf142b" stroke-width="1.8"/>' +
  '<line x1="22" y1="0" x2="0" y2="16" stroke="#cf142b" stroke-width="1.8"/>' +
  '<line x1="11" y1="0" x2="11" y2="16" stroke="#cf142b" stroke-width="3"/>' +
  '<line x1="0" y1="8" x2="22" y2="8" stroke="#cf142b" stroke-width="3"/>' +
  '</svg>';

function _buildWidget(extraClass) {
  var sw = document.createElement('div');
  sw.id = 'lx-lang-sw';
  sw.className = 'lx-lang-sw' + (extraClass ? ' ' + extraClass : '');
  sw.setAttribute('role', 'toolbar');
  sw.setAttribute('aria-label', 'Language / Idioma / Língua');

  [
    {lang:'es', svg:svgES, title:'Español'},
    {lang:'pt', svg:svgBR, title:'Português'},
    {lang:'en', svg:svgUK, title:'English'}
  ].forEach(function(item) {
    var btn = document.createElement('button');
    btn.className = 'lx-lang-btn' + (_lang === item.lang ? ' active' : ' lx-lang-soon');
    btn.setAttribute('data-lang', item.lang);
    btn.setAttribute('title', item.title + ' — Próximamente');
    btn.innerHTML = item.svg;
    if (item.lang === 'es') {
      btn.classList.remove('lx-lang-soon');
      btn.setAttribute('title', item.title);
    }
    sw.appendChild(btn);
  });
  return sw;
}

function _injectStyles() {
  if (document.getElementById('lx-i18n-style')) return;
  var style = document.createElement('style');
  style.id = 'lx-i18n-style';
  style.textContent = [
    /* ── Widget base (shared) ── */
    '.lx-lang-sw{display:flex;align-items:center;gap:5px;}',
    '.lx-lang-btn{background:none;border:2px solid transparent;cursor:default;',
    '  padding:2px;border-radius:4px;opacity:.45;line-height:0;',
    '  transition:opacity .18s,border-color .18s,transform .15s;}',
    '.lx-lang-btn svg{display:block;border-radius:2px;}',
    '.lx-lang-btn.active{opacity:1;border-color:rgba(14,165,233,.75);transform:scale(1.12);cursor:default;}',
    '.lx-lang-btn:hover{opacity:.45;}',
    '.lx-lang-soon{opacity:.2;filter:grayscale(60%);}',
    '.lx-lang-soon:hover{opacity:.25;}',

    /* ── Sidebar version (desktop) ── */
    '.lx-lang-sw.lx-in-sidebar{',
    '  justify-content:center;padding:10px 0 14px;',
    '  border-top:1px solid rgba(255,255,255,.06);margin-top:auto;',
    '  gap:8px;}',
    '.lx-lang-sw.lx-in-sidebar .lx-lang-btn{opacity:.5;padding:3px;}',
    '.lx-lang-sw.lx-in-sidebar .lx-lang-btn.active{opacity:1;border-color:rgba(14,165,233,.7);}',

    /* ── Topbar version (mobile) ── */
    '.lx-lang-sw.lx-in-topbar{gap:4px;margin-right:6px;}',
    '.lx-lang-sw.lx-in-topbar .lx-lang-btn{opacity:.55;}',

    /* ── Floating fallback (pages without sidebar) ── */
    '.lx-lang-sw.lx-floating{',
    '  position:fixed;top:12px;right:12px;z-index:9999;',
    '  background:rgba(4,8,15,.92);padding:5px 8px;border-radius:22px;',
    '  border:1px solid rgba(14,165,233,.3);backdrop-filter:blur(10px);',
    '  box-shadow:0 2px 12px rgba(0,0,0,.5);}'
  ].join('');
  document.head.appendChild(style);
}

function _injectWidget() {
  if (document.getElementById('lx-lang-sw')) return;
  _injectStyles();

  var sidebar  = document.getElementById('sidebar');
  var topbar   = document.querySelector('.sb-topbar');

  if (sidebar) {
    /* DESKTOP: inject at sidebar bottom */
    var sw = _buildWidget('lx-in-sidebar');
    sidebar.appendChild(sw);
  }

  if (topbar) {
    /* MOBILE: inject in topbar before the avatar button */
    var swMob = _buildWidget('lx-in-topbar');
    swMob.id = 'lx-lang-sw-tb';  /* different id so sidebar one doesn't conflict */
    var av = document.getElementById('kl-sb-av-tb');
    if (av) topbar.insertBefore(swMob, av);
    else    topbar.appendChild(swMob);
  }

  if (!sidebar && !topbar) {
    /* FALLBACK: floating pill for pages without sidebar (landing, login, etc.) */
    var swFloat = _buildWidget('lx-floating');
    document.body.appendChild(swFloat);
  }
}

function _updateWidgetButtons(lang) {
  document.querySelectorAll('.lx-lang-btn').forEach(function(btn) {
    btn.classList.toggle('active', btn.getAttribute('data-lang') === lang);
  });
}

/* ─────────────────────────── CORE SET ─────────────────────────── */
function _set(lang) {
  if (!DICT[lang]) return;
  _lang = lang;
  localStorage.setItem('lx_lang', lang);
  document.documentElement.setAttribute('lang', lang);
  _applyDOM(lang);
  _applyCharts(lang);
  _updateWidgetButtons(lang);
  document.dispatchEvent(new CustomEvent('lx:langchange', { detail: { lang: lang } }));
}

/* ─────────────────────────── INIT ─────────────────────────── */
function _init() {
  _injectWidget();
  _applyDOM(_lang);
  if (Object.keys(_chartRegistry).length) _applyCharts(_lang);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _init);
} else {
  _init();
}

/* ─────────────────────────── API PÚBLICA ─────────────────────────── */
window.i18n = {
  set: _set,
  t:   _t,
  get lang() { return _lang; },
  /* Registra un Chart.js instance para traducción automática.
     getConfigFn(lang, tFn) debe devolver:
       { labels?, datasetLabels?, scaleLabels?, title? } */
  registerChart: function(id, instance, getConfigFn) {
    _chartRegistry[id] = { instance: instance, getConfig: getConfigFn };
  }
};

})();
