/**
 * LabX — Single Source of Truth para Rutas, Módulos y Permisos
 * Cargado ANTES que auth.js y nav.js en todas las páginas.
 * Cualquier cambio de permisos se hace SOLO aquí.
 */
(function(w) {

  /* ─────────────────────────────────────────────────────────────
     1. REGISTRO DE MÓDULOS
     Cada módulo tiene: id, file, label, icon, plan mínimo,
     visibilidad por rol, y si aparece en el sidebar.
  ───────────────────────────────────────────────────────────── */
  var MODULES = [
    /* ── Siempre disponibles ─────────────────────────── */
    {
      id:      'dashboard',
      file:    'dashboard.html',
      label:   'Dashboard',
      labelI18n: 'nav_dashboard',
      icon:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></svg>',
      minPlan: 'basic',
      roles:   ['athlete','coach','admin'],
      sidebar: true,
      public:  false
    },
    {
      id:      'athlete_profile',
      file:    'athlete_profile.html',
      label:   'Perfil',
      labelI18n: 'nav_profile',
      icon:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>',
      minPlan: 'basic',
      roles:   ['athlete','coach','admin'],
      sidebar: true,
      public:  false
    },
    /* ── Plan Agegroup ────────────────────────────────── */
    {
      id:      'huella',
      file:    'huella.html',
      label:   'Mi Huella',
      labelI18n: 'nav_huella',
      icon:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2a7 7 0 0 1 7 7c0 4-3 6-7 13C8 15 5 13 5 9a7 7 0 0 1 7-7z"/><circle cx="12" cy="9" r="2.5"/></svg>',
      minPlan: 'agegroup', /* antes 'basic' — Básico ahora es solo Dashboard+Perfil */
      roles:   ['athlete','coach','admin'],
      sidebar: true,
      public:  false
    },
    {
      id:      'training_plan',
      file:    'training_plan.html',
      label:   'Plan',
      labelI18n: 'nav_plan',
      icon:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
      minPlan: 'agegroup',
      roles:   ['athlete','coach','admin'],
      sidebar: true,
      public:  false
    },
    {
      id:      'nutrition',
      file:    'nutrition.html',
      label:   'Nutrición',
      labelI18n: 'nav_nutrition',
      icon:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2a7 7 0 0 1 7 7c0 4-3 6-7 13C8 15 5 13 5 9a7 7 0 0 1 7-7z"/></svg>',
      minPlan: 'agegroup',
      roles:   ['athlete','coach','admin'],
      sidebar: true,
      public:  false
    },
    {
      id:      'analytics',
      file:    'analytics.html',
      label:   'Analytics',
      labelI18n: 'nav_analytics',
      icon:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
      minPlan: 'agegroup',
      roles:   ['athlete','coach','admin'],
      sidebar: true,
      public:  false
    },
    {
      id:      'recovery',
      file:    'recovery.html',
      label:   'Recuperación',
      labelI18n: 'nav_recovery',
      icon:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>',
      minPlan: 'agegroup',
      roles:   ['athlete','coach','admin'],
      sidebar: true,
      public:  false
    },
    {
      id:      'mental',
      file:    'mental.html',
      label:   'Mental',
      labelI18n: 'nav_mental',
      icon:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>',
      minPlan: 'agegroup',
      roles:   ['athlete','coach','admin'],
      sidebar: true,
      public:  false
    },
    {
      id:      'race_day',
      file:    'race_day.html',
      label:   'Race Day',
      labelI18n: 'nav_race_day',
      icon:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
      minPlan: 'agegroup',
      roles:   ['athlete','coach','admin'],
      sidebar: true,
      public:  false
    },
    /* race_predictor.html fusionado en race_day.html (Generar Plan: confianza+rango,
       meta vs predicción, condición de agua) — ver [[project-labx-huella-yir-merge]] */
    {
      id:      'community',
      file:    'community.html',
      label:   'Comunidad',
      labelI18n: 'nav_community',
      icon:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="9" cy="7" r="4"/><path d="M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2"/><circle cx="19" cy="7" r="2"/><path d="M23 21v-1a3 3 0 0 0-2-2.83"/></svg>',
      minPlan: 'agegroup',
      roles:   ['athlete','coach','admin'],
      sidebar: true,
      public:  false
    },
    /* year_in_review.html fusionado en huella.html (Mi Huella) — ver [[project-labx-huella-yir-merge]] */
    /* ── Plan Elite ──────────────────────────────────── */
    {
      id:      'blood_labs',
      file:    'blood_labs.html',
      label:   'Labs',
      labelI18n: 'nav_labs',
      icon:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2l5.5 9.5A6.5 6.5 0 1 1 6.5 11.5z"/></svg>',
      minPlan: 'elite',
      roles:   ['athlete','coach','admin'],
      sidebar: true,
      public:  false
    },
    {
      id:      'training_detail',
      file:    'training_detail.html',
      label:   'Sesión',
      labelI18n: 'nav_session',
      icon:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
      minPlan: 'elite',
      roles:   ['athlete','coach','admin'],
      sidebar: false,
      public:  false
    },
    {
      id:      'adaptive',
      file:    'adaptive.html',
      label:   'Adaptativo',
      labelI18n: 'nav_adaptive',
      icon:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>',
      minPlan: 'elite',
      roles:   ['athlete','coach','admin'],
      sidebar: true,
      public:  false
    },
    {
      id:      'ai_coach',
      file:    'ai_coach.html',
      label:   'AI Coach',
      labelI18n: 'nav_ai_coach',
      icon:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>',
      minPlan: 'elite',
      roles:   ['athlete','coach','admin'],
      sidebar: true,
      public:  false
    },
    {
      id:      'indoor_workout',
      file:    'indoor_workout.html',
      label:   'Indoor',
      labelI18n: 'nav_indoor',
      icon:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
      minPlan: 'elite',
      roles:   ['athlete','coach','admin'],
      sidebar: true,
      public:  false
    },
    /* ── Solo Coach / Admin ──────────────────────────── */
    {
      id:      'coach',
      file:    'coach.html',
      label:   'Coach',
      labelI18n: 'nav_coach',
      icon:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
      minPlan: 'basic',
      roles:   ['coach','admin'],
      sidebar: true,
      public:  false
    },
    /* ── Páginas sin sidebar (públicas o utilitarias) ───── */
    { id:'landing',    file:'landing.html',    sidebar:false, public:true  },
    { id:'login',      file:'login.html',      sidebar:false, public:true  },
    { id:'registro',   file:'registro.html',   sidebar:false, public:true  },
    { id:'onboarding', file:'onboarding.html', sidebar:false, public:false },
    { id:'athlete_app',file:'athlete-app.html',sidebar:false, public:false },
    { id:'gps_tracker',file:'gps_tracker.html',sidebar:false, public:false },
    { id:'detalle',    file:'detalle.html',    sidebar:false, public:false },
    { id:'privacy',    file:'privacy.html',    sidebar:false, public:true  },
    { id:'tos',        file:'tos.html',        sidebar:false, public:true  }
  ];

  /* ─────────────────────────────────────────────────────────────
     2. JERARQUÍA DE PLANES
     El orden importa: cada plan hereda acceso de los anteriores.
  ───────────────────────────────────────────────────────────── */
  var PLAN_HIERARCHY = ['basic', 'agegroup', 'elite'];

  var PLAN_META = {
    basic:    { label:'Básico',   color:'#0EA5E9', upgradeLabel:'Agegroup' },
    agegroup: { label:'Agegroup', color:'#A855F7', upgradeLabel:'Elite'    },
    elite:    { label:'Élite',    color:'#F0A500', upgradeLabel:null       }
  };

  /* ─────────────────────────────────────────────────────────────
     3. HELPERS DERIVADOS (calculados una sola vez al cargar)
  ───────────────────────────────────────────────────────────── */

  /* Mapa id → módulo para lookup O(1) */
  var _byId = {};
  MODULES.forEach(function(m){ if(m.id) _byId[m.id] = m; });

  /* Mapa filename → módulo para el guard de URL */
  var _byFile = {};
  MODULES.forEach(function(m){ if(m.file) _byFile[m.file] = m; });

  /* Lista de módulos permitidos para un plan (incluye herencia) */
  function allowedForPlan(plan) {
    var planIdx = PLAN_HIERARCHY.indexOf(plan);
    if (planIdx === -1) planIdx = 0; /* fallback a basic */
    return MODULES.filter(function(m) {
      if (!m.minPlan) return true;
      return PLAN_HIERARCHY.indexOf(m.minPlan) <= planIdx;
    }).map(function(m){ return m.id; });
  }

  /* ¿Puede un usuario (sesión) acceder a un módulo? */
  function canAccess(session, moduleId) {
    if (!session) return false;
    var mod = _byId[moduleId];
    if (!mod) return false; /* módulo desconocido → denegar */

    var apiRol = session.api_rol || '';

    /* coach/admin tienen acceso a todo */
    if (apiRol === 'coach' || apiRol === 'admin') return true;

    /* Módulo restringido solo a coach/admin */
    if (mod.roles && mod.roles.length > 0) {
      var coachOnly = mod.roles.every(function(r){ return r === 'coach' || r === 'admin'; });
      if (coachOnly) return false; /* atleta no puede acceder */
    }

    /* Para todos los demás módulos: verificar plan únicamente.
       La API puede devolver 'atleta' o 'athlete' — ambos son atletas. */
    var plan = session.plan || 'basic';
    return allowedForPlan(plan).indexOf(moduleId) !== -1;
  }

  /* Plan mínimo requerido (como label legible) para el upgrade wall */
  function requiredPlanLabel(moduleId) {
    var mod = _byId[moduleId];
    if (!mod || !mod.minPlan) return 'Pro';
    return PLAN_META[mod.minPlan] ? PLAN_META[mod.minPlan].label : 'Pro';
  }

  /* ─────────────────────────────────────────────────────────────
     4. GUARD CENTRALIZADO
     Reemplaza: inline guards en <head> + nav.js guard + auth.js guard
     Uso: LX_ROUTES.guard()  ← sin argumentos, detecta la página actual
  ───────────────────────────────────────────────────────────── */
  function guard() {
    var pageName = window.location.pathname.split('/').pop() || 'dashboard.html';
    /* normalizar rutas vacías o index */
    if (!pageName || pageName === '/' || pageName === 'index.html') {
      pageName = 'dashboard.html';
    }

    var mod = _byFile[pageName];

    /* Página pública → sin restricción */
    if (!mod || mod.public) return;

    /* Leer sesión */
    var sess = null;
    try {
      var raw = sessionStorage.getItem('kl_s') || localStorage.getItem('kl_s');
      sess = raw ? JSON.parse(raw) : null;
    } catch(e) { sess = null; }

    /* Sin sesión → login */
    if (!sess) {
      /* Evitar loop: si YA estamos en login, no redirigir */
      if (pageName === 'login.html') return;
      window.location.replace('login.html');
      return;
    }

    /* Verificar acceso al módulo */
    if (mod.sidebar !== false && mod.id && !canAccess(sess, mod.id)) {
      /* Evitar loop: si YA estamos en dashboard, no redirigir de nuevo */
      if (pageName === 'dashboard.html') return;
      window.location.replace('dashboard.html?locked=' + encodeURIComponent(mod.id));
      return;
    }
  }

  /* ─────────────────────────────────────────────────────────────
     5. API PÚBLICA
  ───────────────────────────────────────────────────────────── */
  w.LX_ROUTES = {
    modules:          MODULES,
    planHierarchy:    PLAN_HIERARCHY,
    planMeta:         PLAN_META,
    byId:             _byId,
    byFile:           _byFile,
    allowedForPlan:   allowedForPlan,
    canAccess:        canAccess,
    requiredPlanLabel: requiredPlanLabel,
    guard:            guard
  };

}(window));
