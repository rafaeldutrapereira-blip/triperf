/* LabX — Authentication & Module Access — unified with Coach API */
(function(w){

  /* En producción (servido desde FastAPI) la origin es la misma;
     en desarrollo local los HTML se abren como file:// → usa localhost:8000 */
  var API_BASE = (window.location.protocol === 'file:')
    ? 'http://localhost:8000/api'
    : window.location.origin + '/api';

  /* Mapa shorthand → email para la Coach API */
  var USER_EMAIL = {
    'rafael': 'rafael@labx.com',
    'demo':   'demo@labx.com'
  };

  /* plan_nivel API → plan key local */
  var PLAN_MAP = { elite:'elite', agegroup:'agegroup', basico:'basic' };

  /* rol API → etiqueta amigable */
  var ROLE_LABELS = {
    admin:  'Admin · Coach',
    coach:  'Coach',
    atleta: 'Atleta' /* el rol real en la BD es 'atleta' (español), no 'athlete' */
  };

  /* PLANS derivado de LX_ROUTES para evitar duplicación.
     Si routes.config.js no cargó, usar defaults seguros. */
  var PLANS = (function(){
    if(window.LX_ROUTES) {
      var out = {};
      ['basic','agegroup','elite'].forEach(function(p){
        var meta = window.LX_ROUTES.planMeta[p] || {};
        out[p] = {
          label:   meta.label  || p,
          color:   meta.color  || '#0EA5E9',
          modules: window.LX_ROUTES.allowedForPlan(p)
        };
      });
      return out;
    }
    return {
      basic:    { label:'Básico',   color:'#0EA5E9', modules:['dashboard','athlete_profile'] },
      agegroup: { label:'Agegroup', color:'#A855F7', modules:['dashboard','athlete_profile','training_plan','nutrition','analytics','race_predictor','year_in_review','community','recovery','mental','race_day','gear'] },
      elite:    { label:'Élite',    color:'#F0A500', modules:['dashboard','athlete_profile','training_plan','nutrition','analytics','blood_labs','training_detail','race_predictor','year_in_review','community','recovery','mental','race_day','ai_coach','adaptive','indoor_workout','gear'] }
    };
  }());

  var MODULES = {
    dashboard:       'dashboard.html',
    athlete_profile: 'athlete_profile.html',
    training_plan:   'training_plan.html',
    nutrition:       'nutrition.html',
    blood_labs:      'blood_labs.html',
    training_detail: 'training_detail.html',
    race_predictor:  'race_predictor.html',
    coach:           'coach.html',
    indoor_workout:  'indoor_workout.html',
    community:       'community.html'
  };

  /* ── Session ──────────────────────────────────────────────── */
  function getSession() {
    try {
      var s = sessionStorage.getItem('kl_s') || localStorage.getItem('kl_s');
      return s ? JSON.parse(s) : null;
    } catch(e) { return null; }
  }

  function saveSession(data, remember) {
    var json = JSON.stringify(data);
    sessionStorage.setItem('kl_s', json);
    if (remember) localStorage.setItem('kl_s', json);
  }

  function clearSession() {
    sessionStorage.removeItem('kl_s');
    localStorage.removeItem('kl_s');
    /* limpiar también tokens de la Coach API */
    localStorage.removeItem('lx_co_token');
    localStorage.removeItem('lx_co_rol');
    localStorage.removeItem('lx_co_nombre');
    localStorage.removeItem('lx_ath_token');
    localStorage.removeItem('lx_ath_portal_token');
  }

  function _initials(name) {
    if (!name) return 'U';
    return name.split(' ').slice(0,2).map(function(w){ return w[0] || ''; }).join('').toUpperCase();
  }

  /* ── Auth — falla cerrado: sin backend no hay login ───────── */
  function login(usernameOrEmail, password, remember) {
    var input = (usernameOrEmail || '').toLowerCase().trim();
    var email = USER_EMAIL[input] || input; /* si ya es email, úsalo directo */

    return fetch(API_BASE + '/auth/login', {
      method:  'POST',
      headers: {'Content-Type': 'application/json'},
      credentials: 'include',
      body:    JSON.stringify({ email: email, password: password })
    })
    .then(function(r) {
      if (!r.ok) return Promise.reject('bad_credentials');
      return r.json();
    })
    .then(function(data) {
      /* lx_co_token es el bearer token GENERAL que usan dashboard.html,
         training_plan.html, athlete_profile.html, etc. para CUALQUIER
         usuario logueado (nombre histórico confuso, no es exclusivo de
         coach) — por eso se guarda siempre, sin filtrar por rol. Filtrarlo
         acá rompería el login normal de cualquier atleta en esas páginas.
         (Se probó gatear esto por rol para evitar que un login de atleta
         pisara una sesión de coach abierta en coach.html en el MISMO
         navegador — pero es un escenario de testing con 2 identidades a
         la vez en la misma pestaña, no un caso real de uso; coach.html
         para "ver mi propio plan como atleta" ya usa una clave separada,
         lx_ath_token, precisamente para no chocar con esto.) */
      localStorage.setItem('lx_co_token',  data.access_token);
      localStorage.setItem('lx_co_rol',    data.rol);
      localStorage.setItem('lx_co_nombre', data.nombre);

      /* El idioma solo se guardaba cliente→servidor (PATCH en 'lx:langchange',
         ver abajo). Nunca se releía servidor→cliente, así que un usuario que
         cambiaba de dispositivo o borraba localStorage perdía su preferencia
         aunque el backend la tuviera guardada en user.lang. */
      try {
        if (data.lang && window.i18n && typeof window.i18n.set === 'function' &&
            window.i18n.lang !== data.lang) {
          window.i18n.set(data.lang);
        }
      } catch (e) {}

      var plan = PLAN_MAP[data.plan_nivel] || 'basic';
      var sess = {
        username: input,
        email:    email,
        name:     data.nombre,
        initials: _initials(data.nombre),
        role:     ROLE_LABELS[data.rol] || data.rol,
        plan:     plan,
        api_rol:  data.rol,
        user_id:  data.user_id,
        ts:       Date.now()
      };
      saveSession(sess, remember);
      return { ok: true, session: sess };
    })
    .catch(function() {
      /* Falla cerrado: si el backend no responde o rechaza las
         credenciales, el login falla. Nunca hubo (ni debe haber) una
         autenticación local de respaldo con contraseñas embebidas en el
         cliente — eso era un bypass total del backend. */
      return { ok: false };
    });
  }

  function logout() {
    /* Llamar al API para revocar token y limpiar cookie HttpOnly */
    var API = window._LX_API || 'http://localhost:8000/api';
    fetch(API + '/auth/logout', { method: 'POST', credentials: 'include' })
      .catch(function(){})
      .finally(function(){
        clearSession();
        window.location.replace('landing.html');
      });
  }

  /* ── Guard ────────────────────────────────────────────────── */
  function guard(moduleId) {
    var s = getSession();

    if (!s) {
      window.location.replace('login.html');
      return;
    }

    /* Coach/admin tienen acceso a todos los módulos */
    if (s.api_rol === 'coach' || s.api_rol === 'admin') return;

    var plan = PLANS[s.plan];
    if (!plan || plan.modules.indexOf(moduleId) === -1) {
      /* Evitar loop: no redirigir si ya estamos en dashboard */
      var pg = window.location.pathname.split('/').pop();
      if (pg === 'dashboard.html') return;
      window.location.replace('dashboard.html?locked=' + moduleId);
      return;
    }

    function hydrate() {
      var el;
      el = document.getElementById('kl-uname');   if (el) el.textContent = s.name ? s.name.split(' ')[0] : s.username;
      el = document.getElementById('kl-urole');   if (el) el.textContent = s.role;
      el = document.getElementById('kl-avatar');  if (el) el.textContent = s.initials;
      el = document.getElementById('kl-plan-badge');
      if (el) {
        el.textContent = plan.label;
        el.style.color       = plan.color;
        el.style.borderColor = plan.color + '55';
        el.style.background  = plan.color + '18';
      }
      el = document.getElementById('kl-fullname'); if (el) el.textContent = s.name;
      el = document.getElementById('kl-role-tag'); if (el) el.textContent = s.role;

      /* bloquear módulos sin acceso */
      document.querySelectorAll('[data-kl-module]').forEach(function(link) {
        var mod = link.getAttribute('data-kl-module');
        if (mod === 'coach') return; /* coach lo maneja nav.js */
        if (plan.modules.indexOf(mod) === -1) {
          link.classList.add('kl-locked');
          link.href = '#';
          link.onclick = function(e) { e.preventDefault(); showUpgradeToast(mod, plan.label); };
        }
      });
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', hydrate);
    } else {
      hydrate();
    }
  }

  /* ── Upgrade Toast ────────────────────────────────────────── */
  function showUpgradeToast(mod, currentPlan) {
    var existing = document.getElementById('kl-toast');
    if (existing) existing.remove();
    var t = document.createElement('div');
    t.id = 'kl-toast';
    t.innerHTML =
      '<div style="display:flex;align-items:center;gap:.75rem">' +
        '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#F0A500" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>' +
        '<div>' +
          '<div style="font-family:Oswald,sans-serif;font-size:.82rem;font-weight:600;letter-spacing:.08em;color:#F0F9FF">Módulo no incluido en plan ' + currentPlan + '</div>' +
          '<div style="font-size:.75rem;color:#7FB3CC;margin-top:.1rem">Actualiza tu plan para acceder.</div>' +
        '</div>' +
        '<a href="landing.html#plans" style="margin-left:auto;font-family:Oswald,sans-serif;font-size:.72rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#FF6535;white-space:nowrap">Ver Planes ›</a>' +
      '</div>';
    Object.assign(t.style, {
      position:'fixed', bottom:'1.5rem', left:'50%',
      transform:'translateX(-50%) translateY(20px)',
      background:'#08121E', border:'1px solid rgba(240,165,0,.35)',
      borderRadius:'10px', padding:'1rem 1.25rem', zIndex:'9999',
      minWidth:'320px', maxWidth:'460px',
      boxShadow:'0 8px 32px rgba(0,0,0,.5)',
      opacity:'0', transition:'all .3s cubic-bezier(.4,0,.2,1)'
    });
    document.body.appendChild(t);
    requestAnimationFrame(function() {
      t.style.opacity = '1';
      t.style.transform = 'translateX(-50%) translateY(0)';
    });
    setTimeout(function() {
      t.style.opacity = '0';
      t.style.transform = 'translateX(-50%) translateY(10px)';
      setTimeout(function() { t.remove(); }, 300);
    }, 4000);
  }

  /* Sincroniza el idioma elegido al backend — i18n.js solo lo guarda en
     localStorage (cliente), pero los emails transaccionales (bienvenida,
     drips, alertas) se generan en background sin contexto de request, así
     que necesitan el idioma persistido en el User (ver User.lang,
     migración o1p2q3r4s5t6). Fire-and-forget: si falla, el usuario sigue
     viendo la UI traducida igual (localStorage ya tiene la verdad), solo
     los emails quedarían en el idioma anterior hasta el próximo cambio. */
  document.addEventListener('lx:langchange', function(e){
    var tok = localStorage.getItem('lx_co_token');
    if(!tok || !e.detail || !e.detail.lang) return;
    fetch(API_BASE + '/athlete/profile', {
      method: 'PATCH',
      headers: {'Content-Type':'application/json', 'Authorization':'Bearer '+tok},
      body: JSON.stringify({lang: e.detail.lang})
    }).catch(function(){});
  });

  /* ── Public API ───────────────────────────────────────────── */
  w.KL = {
    login:       login,
    logout:      logout,
    guard:       guard,
    getSession:  getSession,
    saveSession: saveSession,
    clearSession: clearSession,
    API_BASE:    API_BASE
  };

}(window));
