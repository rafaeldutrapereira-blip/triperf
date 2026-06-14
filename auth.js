/* KonaLabs — Authentication & Module Access */
(function(w){

  var USERS = {
    rafael: {
      pw:       'kona2026',
      name:     'Rafael Dutra',
      initials: 'R',
      role:     'Ironman 70.3',
      plan:     'elite'
    },
    demo: {
      pw:       'demo123',
      name:     'Atleta Demo',
      initials: 'A',
      role:     'Triatleta',
      plan:     'basic'
    },
    pro: {
      pw:       'pro2026',
      name:     'Usuario Pro',
      initials: 'U',
      role:     'Ironman 70.3',
      plan:     'pro'
    }
  };

  var PLANS = {
    basic: {
      label:   'Básico',
      color:   '#0EA5E9',
      modules: ['dashboard', 'athlete_profile']
    },
    pro: {
      label:   'Pro',
      color:   '#A855F7',
      modules: ['dashboard', 'athlete_profile', 'training_plan', 'nutrition']
    },
    elite: {
      label:   'Élite',
      color:   '#F0A500',
      modules: ['dashboard', 'athlete_profile', 'training_plan', 'nutrition',
                'blood_labs', 'training_detail', 'race_predictor']
    }
  };

  var MODULES = {
    dashboard:       'dashboard.html',
    athlete_profile: 'athlete_profile.html',
    training_plan:   'training_plan.html',
    nutrition:       'nutrition.html',
    blood_labs:      'blood_labs.html',
    training_detail: 'training_detail.html',
    race_predictor:  'race_predictor.html'
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
  }

  /* ── Auth API ─────────────────────────────────────────────── */
  function login(username, password, remember) {
    var u = USERS[username.toLowerCase().trim()];
    if (!u || u.pw !== password) return { ok: false };
    var data = {
      username: username.toLowerCase(),
      name:     u.name,
      initials: u.initials,
      role:     u.role,
      plan:     u.plan,
      ts:       Date.now()
    };
    saveSession(data, remember);
    return { ok: true, session: data };
  }

  function logout() {
    clearSession();
    window.location.replace('login.html');
  }

  /* ── Guard ────────────────────────────────────────────────── */
  function guard(moduleId) {
    var s = getSession();
    if (!s) { window.location.replace('login.html'); return; }

    var plan = PLANS[s.plan];
    if (!plan || plan.modules.indexOf(moduleId) === -1) {
      window.location.replace('login.html?denied=' + moduleId);
      return;
    }

    /* inject user info into nav once DOM is ready */
    function hydrate() {
      var el;
      el = document.getElementById('kl-uname');   if (el) el.textContent = s.name.split(' ')[0];
      el = document.getElementById('kl-urole');   if (el) el.textContent = s.role;
      el = document.getElementById('kl-avatar');  if (el) el.textContent = s.initials;
      el = document.getElementById('kl-plan-badge');
      if (el) {
        el.textContent = plan.label;
        el.style.color = plan.color;
        el.style.borderColor = plan.color + '55';
        el.style.background = plan.color + '18';
      }
      /* also update profile page hero if present */
      el = document.getElementById('kl-fullname'); if (el) el.textContent = s.name;
      el = document.getElementById('kl-role-tag'); if (el) el.textContent = s.role;

      /* lock nav links the user can't access */
      document.querySelectorAll('[data-kl-module]').forEach(function(link) {
        var mod = link.getAttribute('data-kl-module');
        if (plan.modules.indexOf(mod) === -1) {
          link.classList.add('kl-locked');
          link.href = '#';
          link.onclick = function(e) {
            e.preventDefault();
            showUpgradeToast(mod, plan.label);
          };
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
          '<div style="font-size:.75rem;color:#7FB3CC;margin-top:.1rem">Actualiza tu plan para acceder a este módulo.</div>' +
        '</div>' +
        '<a href="landing.html#plans" style="margin-left:auto;font-family:Oswald,sans-serif;font-size:.72rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#FF6535;white-space:nowrap">Ver Planes ›</a>' +
      '</div>';
    Object.assign(t.style, {
      position:     'fixed',
      bottom:       '1.5rem',
      left:         '50%',
      transform:    'translateX(-50%) translateY(20px)',
      background:   '#08121E',
      border:       '1px solid rgba(240,165,0,.35)',
      borderRadius: '10px',
      padding:      '1rem 1.25rem',
      zIndex:       '9999',
      minWidth:     '320px',
      maxWidth:     '460px',
      boxShadow:    '0 8px 32px rgba(0,0,0,.5)',
      opacity:      '0',
      transition:   'all .3s cubic-bezier(.4,0,.2,1)'
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

  /* ── Public API ───────────────────────────────────────────── */
  w.KL = { login: login, logout: logout, guard: guard, getSession: getSession };

}(window));
