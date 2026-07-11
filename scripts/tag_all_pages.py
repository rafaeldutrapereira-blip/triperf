"""
Add data-i18n attributes to all LabX HTML pages.
Run from the LabX project root.
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = 'C:/Users/rafae/projects/LabX/'

def patch(fname, replacements):
    path = BASE + fname
    with open(path, encoding='utf-8') as f:
        c = f.read()
    applied = 0
    missed = []
    for old, new in replacements:
        if old in c:
            c = c.replace(old, new, 1)
            applied += 1
        else:
            missed.append(repr(old[:60]))
    with open(path, 'w', encoding='utf-8') as f:
        f.write(c)
    print(f'  {fname}: {applied}/{len(replacements)} applied', end='')
    if missed:
        print(f'  MISS: {missed[:3]}', end='')
    print()

# ─── landing.html ─────────────────────────────────────────────────────────────
patch('landing.html', [
    # Nav links
    ('<a href="#disciplines">Disciplinas</a>',
     '<a href="#disciplines" data-i18n="nav_disciplines">Disciplinas</a>'),
    ('<a href="#calendar">Carreras</a>',
     '<a href="#calendar" data-i18n="nav_races">Carreras</a>'),
    ('<a href="#plans">Planes</a>',
     '<a href="#plans" data-i18n="nav_plans">Planes</a>'),
    ('<a href="#metrics">Métricas</a>',
     '<a href="#metrics" data-i18n="nav_metrics">Métricas</a>'),
    ('<a href="#contact">Contacto</a>',
     '<a href="#contact" data-i18n="nav_contact">Contacto</a>'),
    # Nav CTA button
    ('<a href="login.html" class="btn btn-primary">Acceder</a>',
     '<a href="login.html" class="btn btn-primary" data-i18n="nav_access">Acceder</a>'),
    # Calendar filter buttons
    ('onclick="calFilter(this,\'all\')">Todas</button>',
     'onclick="calFilter(this,\'all\')" data-i18n="filter_all">Todas</button>'),
    ('onclick="calFilter(this,\'marathon\')">🏅 Maratón</button>',
     'onclick="calFilter(this,\'marathon\')" data-i18n="filter_marathon">🏅 Maratón</button>'),
    ('onclick="calFilter(this,\'triathlon\')">🏆 Triatlón</button>',
     'onclick="calFilter(this,\'triathlon\')" data-i18n="filter_triathlon">🏆 Triatlón</button>'),
    # Contact form labels
    ('<label for="nombre">Nombre</label>',
     '<label for="nombre" data-i18n="form_name">Nombre</label>'),
    ('<label for="email">Email</label>',
     '<label for="email" data-i18n="form_email">Email</label>'),
    ('<label for="interes">Interés</label>',
     '<label for="interes" data-i18n="form_interest">Interés</label>'),
    # Send message button (text node after SVG)
    ('\n          Enviar mensaje\n        </button>',
     '\n          <span data-i18n="btn_send_msg">Enviar mensaje</span>\n        </button>'),
])

# ─── blood_labs.html ──────────────────────────────────────────────────────────
patch('blood_labs.html', [
    # Main tab bar
    ('onclick="switchTab(\'resumen\',this)">📊  Resumen Clínico</button>',
     'onclick="switchTab(\'resumen\',this)" data-i18n="labs_summary">📊  Resumen Clínico</button>'),
    ('onclick="switchTab(\'trends\',this)">📈 Tendencias</button>',
     'onclick="switchTab(\'trends\',this)" data-i18n="labs_trends">📈 Tendencias</button>'),
    ('onclick="switchTab(\'garmin\',this)">🔗 Correlación Garmin</button>',
     'onclick="switchTab(\'garmin\',this)" data-i18n="labs_garmin_corr">🔗 Correlación Garmin</button>'),
    ('onclick="switchTab(\'import\',this)">📥 Registrar Examen</button>',
     'onclick="switchTab(\'import\',this)" data-i18n="btn_register_exam">📥 Registrar Examen</button>'),
    # Header add button
    ('>+ Registrar Examen</button>',
     ' data-i18n="btn_add_exam">+ Registrar Examen</button>'),
    # Panel sub-tabs (stab-btn)
    ('onclick="switchStab(\'hemo\',this)">🩸 Hemograma</button>',
     'onclick="switchStab(\'hemo\',this)" data-i18n="labs_hemo">🩸 Hemograma</button>'),
    ('onclick="switchStab(\'musc\',this)">💪 Muscular</button>',
     'onclick="switchStab(\'musc\',this)" data-i18n="labs_muscle">💪 Muscular</button>'),
    ('onclick="switchStab(\'lipid\',this)">🫀 Lípidos</button>',
     'onclick="switchStab(\'lipid\',this)" data-i18n="labs_lipids">🫀 Lípidos</button>'),
    ('onclick="switchStab(\'vit\',this)">🌟 Vitaminas</button>',
     'onclick="switchStab(\'vit\',this)" data-i18n="labs_vitamins">🌟 Vitaminas</button>'),
    ('onclick="switchStab(\'renal\',this)">🫘 Renal</button>',
     'onclick="switchStab(\'renal\',this)" data-i18n="labs_renal">🫘 Renal</button>'),
    ('onclick="switchStab(\'horm\',this)">🧪 Hormonal</button>',
     'onclick="switchStab(\'horm\',this)" data-i18n="labs_hormonal">🧪 Hormonal</button>'),
    # Form labels
    ('<label class="form-label">Fecha del examen</label>',
     '<label class="form-label" data-i18n="labs_date">Fecha del examen</label>'),
    ('<label class="form-label">Laboratorio</label>',
     '<label class="form-label" data-i18n="labs_lab">Laboratorio</label>'),
    ('<label class="form-label">Contexto / Motivo</label>',
     '<label class="form-label" data-i18n="labs_context">Contexto / Motivo</label>'),
    # Action buttons
    ('onclick="saveExam()">💾 Guardar Examen</button>',
     'onclick="saveExam()" data-i18n="btn_save_exam">💾 Guardar Examen</button>'),
    ('onclick="clearForm()">✕ Limpiar</button>',
     'onclick="clearForm()" data-i18n="btn_clear">✕ Limpiar</button>'),
])

# Find the Electrolitos button which has partial text after truncation
patch('blood_labs.html', [
    ('onclick="switchStab(\'elec\',this)">⚡ ',
     'onclick="switchStab(\'elec\',this)" data-i18n="labs_electrolytes">⚡ '),
])

# ─── nutrition.html ───────────────────────────────────────────────────────────
patch('nutrition.html', [
    # Race type buttons
    ("onclick=\"setRace('sprint',this)\">⚡ Sprint</button>",
     "onclick=\"setRace('sprint',this)\" data-i18n=\"nutr_sprint\">⚡ Sprint</button>"),
    ("onclick=\"setRace('olympic',this)\">🏊  Olímpico</button>",
     "onclick=\"setRace('olympic',this)\" data-i18n=\"nutr_olympic\">🏊  Olímpico</button>"),
    ("onclick=\"setRace('703',this)\">🌊 70.3</button>",
     "onclick=\"setRace('703',this)\" data-i18n=\"nutr_703\">🌊 70.3</button>"),
    ("onclick=\"setRace('ironman',this)\">🔥 Ironman</button>",
     "onclick=\"setRace('ironman',this)\" data-i18n=\"nutr_ironman\">🔥 Ironman</button>"),
    # Summary / Plan tabs
    ("onclick=\"switchTab('res',this)\">📊 Resumen</button>",
     "onclick=\"switchTab('res',this)\" data-i18n=\"nutr_summary\">📊 Resumen</button>"),
    ("onclick=\"switchTab('plan',this)\">📋  Plan Hora a Hora</button>",
     "onclick=\"switchTab('plan',this)\" data-i18n=\"nutr_plan\">📋  Plan Hora a Hora</button>"),
    ("onclick=\"switchTab('pre',this)\">📋 Pre-Carrera</button>",
     "onclick=\"switchTab('pre',this)\" data-i18n=\"nutr_prerace\">📋 Pre-Carrera</button>"),
])

# ─── training_plan.html ───────────────────────────────────────────────────────
patch('training_plan.html', [
    # Form labels
    ('<label class="form-label">Disciplina</label>',
     '<label class="form-label" data-i18n="tp_discipline">Disciplina</label>'),
    ('<label class="form-label">Nombre de la sesión</label>',
     '<label class="form-label" data-i18n="tp_session_name">Nombre de la sesión</label>'),
    ('<label class="form-label">Duración (min)</label>',
     '<label class="form-label" data-i18n="tp_duration">Duración (min)</label>'),
    ('<label class="form-label">TSS Objetivo</label>',
     '<label class="form-label" data-i18n="tp_tss_target">TSS Objetivo</label>'),
    ('<label class="form-label">Notas / Instrucciones</label>',
     '<label class="form-label" data-i18n="tp_notes_inst">Notas / Instrucciones</label>'),
    ('<label class="form-label">TSS Real</label>',
     '<label class="form-label" data-i18n="tp_tss_real">TSS Real</label>'),
    # Buttons
    ('onclick="saveSession()">Guardar Sesión</button>',
     'onclick="saveSession()" data-i18n="btn_save_session">Guardar Sesión</button>'),
    ('onclick="fakeSync()">Enviar a Garmin Connect</button>',
     'onclick="fakeSync()" data-i18n="btn_send_garmin">Enviar a Garmin Connect</button>'),
    ('onclick="submitLog()">Guardar resultado</button>',
     'onclick="submitLog()" data-i18n="btn_save_result">Guardar resultado</button>'),
    # Cancel/close buttons (use existing keys)
    ("onclick=\"closeModal('modal-add')\">Cancelar</button>",
     "onclick=\"closeModal('modal-add')\" data-i18n=\"btn_cancel\">Cancelar</button>"),
    ("onclick=\"closeModal('modal-garmin')\">Cerrar</button>",
     "onclick=\"closeModal('modal-garmin')\" data-i18n=\"btn_close\">Cerrar</button>"),
    # Filter buttons
    ('>Todos<', ' data-i18n="opt_all">Todos<'),
    ('>🏊 Natación<', ' data-i18n="opt_swim">🏊 Natación<'),
    ('>🚴 Ciclismo<', ' data-i18n="opt_bike">🚴 Ciclismo<'),
    ('>🏃 Carrera<', ' data-i18n="opt_run">🏃 Carrera<'),
    ('>💪 Fuerza<', ' data-i18n="opt_strength">💪 Fuerza<'),
])

# ─── race_predictor.html ──────────────────────────────────────────────────────
patch('race_predictor.html', [
    # Section titles
    ('<span class="cond-panel-title">Condiciones de Carrera</span>',
     '<span class="cond-panel-title" data-i18n="pred_conditions">Condiciones de Carrera</span>'),
    ('<span class="cond-label-sm">Condición del Día (TSB)</span>',
     '<span class="cond-label-sm" data-i18n="pred_tsb">Condición del Día (TSB)</span>'),
    ('>Ambiente &amp; Terreno</span>',
     ' data-i18n="pred_weather">Ambiente &amp; Terreno</span>'),
    ('<span class="cond-label-sm">Temperatura</span>',
     '<span class="cond-label-sm" data-i18n="pred_temp">Temperatura</span>'),
    ('<span class="cond-label-sm">Viento</span>',
     '<span class="cond-label-sm" data-i18n="pred_wind">Viento</span>'),
    ('<span class="cond-label-sm">Altimetría Bici</span>',
     '<span class="cond-label-sm" data-i18n="pred_altitude">Altimetría Bici</span>'),
    ('<span class="cond-label-sm">Agua</span>',
     '<span class="cond-label-sm" data-i18n="pred_water">Agua</span>'),
    ('<span class="panel-title">Splits Predichos</span>',
     '<span class="panel-title" data-i18n="pred_splits">Splits Predichos</span>'),
    # Race distance buttons (reuse existing keys)
    ('>Sprint<', ' data-i18n="nutr_sprint">Sprint<'),
    ('>Olímpico<', ' data-i18n="nutr_olympic">Olímpico<'),
    ('>70.3<', ' data-i18n="nutr_703">70.3<'),
    ('>Ironman<', ' data-i18n="nutr_ironman">Ironman<'),
])

# ─── reset-password.html ─────────────────────────────────────────────────────
patch('reset-password.html', [
    ('<label class="form-label" for="req-email">Email de tu cuenta</label>',
     '<label class="form-label" for="req-email" data-i18n="form_email_account">Email de tu cuenta</label>'),
    ('<label class="form-label">Nueva contraseña</label>',
     '<label class="form-label" data-i18n="form_new_password">Nueva contraseña</label>'),
    ('<label class="form-label">Confirmar contraseña</label>',
     '<label class="form-label" data-i18n="form_confirm_password">Confirmar contraseña</label>'),
    ('<span class="btn-text">Enviar link de recuperación</span>',
     '<span class="btn-text" data-i18n="btn_send_reset">Enviar link de recuperación</span>'),
    ('<span class="btn-text">Actualizar contraseña</span>',
     '<span class="btn-text" data-i18n="btn_update_password">Actualizar contraseña</span>'),
])

# ─── athlete_profile.html ────────────────────────────────────────────────────
patch('athlete_profile.html', [
    ('<div class="ap-form-label">Identificación</div>',
     '<div class="ap-form-label" data-i18n="prof_identification">Identificación</div>'),
    ('<div class="ap-form-label">Datos Físicos</div>',
     '<div class="ap-form-label" data-i18n="prof_physical">Datos Físicos</div>'),
    ('<div class="ap-form-label">Potencia y Cardio</div>',
     '<div class="ap-form-label" data-i18n="prof_power_cardio">Potencia y Cardio</div>'),
    ('<div class="ap-form-label">Ritmos Umbral</div>',
     '<div class="ap-form-label" data-i18n="prof_thresholds">Ritmos Umbral</div>'),
    ('<div class="ap-form-label">Objetivo Temporada</div>',
     '<div class="ap-form-label" data-i18n="prof_season_goal">Objetivo Temporada</div>'),
])

# ─── detalle.html ─────────────────────────────────────────────────────────────
patch('detalle.html', [
    ('role="tab">Semana</button>',
     'role="tab" data-i18n="lbl_week">Semana</button>'),
    ('role="tab">3 Meses</button>',
     'role="tab" data-i18n="lbl_3months">3 Meses</button>'),
    ('role="tab">6 Meses</button>',
     'role="tab" data-i18n="lbl_6months">6 Meses</button>'),
    ('role="tab">Todo</button>',
     'role="tab" data-i18n="lbl_all_time">Todo</button>'),
    ('<span id="foot-metric">INDICADOR DE RENDIMIENTO</span>',
     '<span id="foot-metric" data-i18n="perf_indicator">INDICADOR DE RENDIMIENTO</span>'),
])

# ─── 404.html ─────────────────────────────────────────────────────────────────
patch('404.html', [
    ('<h1>Página no encontrada</h1>',
     '<h1 data-i18n="notfound_title">Página no encontrada</h1>'),
    ('>Ir al Dashboard\n    </a>',
     ' data-i18n="notfound_go_dash">Ir al Dashboard\n    </a>'),
    # "Inicio" link to landing
    ('>Inicio<', ' data-i18n="notfound_go_home">Inicio<'),
])

# ─── dashboard.html ───────────────────────────────────────────────────────────
patch('dashboard.html', [
    ('>6 Meses<', ' data-i18n="lbl_6months">6 Meses<'),
    ('>1 Año<', ' data-i18n="lbl_1year">1 Año<'),
    ('>Aplicar<', ' data-i18n="btn_apply">Aplicar<'),
    ('>Desde<', ' data-i18n="lbl_from">Desde<'),
    ('>Hasta<', ' data-i18n="lbl_to">Hasta<'),
    ('>Actualizar Plan<', ' data-i18n="btn_update_plan">Actualizar Plan<'),
    ('>Ver histórico →<', ' data-i18n="btn_view_history">Ver histórico →<'),
    ('>VER HISTÓRICO ›<', ' data-i18n="btn_view_history">VER HISTÓRICO ›<'),
    # Sueño
    ('>Sueño<', ' data-i18n="kpi_sleep">Sueño<'),
    # FC Reposo
    ('>FC Reposo<', ' data-i18n="kpi_hr_rest">FC Reposo<'),
    # Race distance filter buttons
    ('>Sprint<', ' data-i18n="nutr_sprint">Sprint<'),
    ('>Olímpico<', ' data-i18n="nutr_olympic">Olímpico<'),
    ('>70.3<', ' data-i18n="nutr_703">70.3<'),
    ('>Ironman<', ' data-i18n="nutr_ironman">Ironman<'),
    ('>Todos<', ' data-i18n="opt_all">Todos<'),
])

print('\nDone.')
