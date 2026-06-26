/* LabX — Sidebar Navigation JS (shared) — unified auth */
(function(){

  /* ── Sidebar open/close ──────────────────────────────────── */
  function sbOpen(){
    var s=document.getElementById('sidebar');
    var o=document.getElementById('sb-overlay');
    var h=document.getElementById('sb-ham');
    if(s) s.classList.add('open');
    if(o) o.classList.add('open');
    if(h) h.classList.add('open');
    document.body.style.overflow='hidden';
  }
  function sbClose(){
    var s=document.getElementById('sidebar');
    var o=document.getElementById('sb-overlay');
    var h=document.getElementById('sb-ham');
    if(s) s.classList.remove('open');
    if(o) o.classList.remove('open');
    if(h) h.classList.remove('open');
    document.body.style.overflow='';
  }
  window.sbToggle=function(){
    var s=document.getElementById('sidebar');
    if(s&&s.classList.contains('open')) sbClose(); else sbOpen();
  };
  window.sbClose=sbClose;
  document.addEventListener('keydown',function(e){ if(e.key==='Escape') sbClose(); });

  /* ── Módulos plan → lista (debe coincidir con auth.js) ──── */
  var PLAN_MODULES = {
    basic:  ['dashboard','athlete_profile'],
    pro:    ['dashboard','athlete_profile','training_plan','nutrition'],
    elite:  ['dashboard','athlete_profile','training_plan','nutrition',
             'blood_labs','training_detail','race_predictor']
  };
  var PLAN_LABELS = { basic:'Básico', pro:'Pro', elite:'Élite' };
  var PLAN_COLORS = { basic:'#0EA5E9', pro:'#A855F7', elite:'#F0A500' };

  /* ── Hidrata nav desde la sesión unificada ───────────────── */
  document.addEventListener('DOMContentLoaded', function(){
    var sess = null;
    try{
      sess = JSON.parse(sessionStorage.getItem('kl_s') || localStorage.getItem('kl_s') || 'null');
    }catch(e){}

    /* Avatar + nombre */
    if(sess){
      var init = sess.initials || (sess.name ? sess.name[0].toUpperCase() : 'U');
      var av1=document.getElementById('kl-sb-avatar');
      var av2=document.getElementById('kl-sb-av-tb');
      var nm =document.getElementById('kl-sb-uname');
      var rl =document.getElementById('kl-sb-urole');
      if(av1) av1.textContent = init;
      if(av2) av2.textContent = init;
      if(nm)  nm.textContent  = sess.name || sess.username || 'Usuario';

      /* Badge de plan */
      var plan   = sess.plan || 'basic';
      var color  = PLAN_COLORS[plan] || '#0EA5E9';
      var label  = PLAN_LABELS[plan]  || 'Básico';
      var apiRol = sess.api_rol || localStorage.getItem('lx_co_rol') || '';

      /* Mostrar rol enriquecido en sidebar */
      var roleText = label;
      if(apiRol==='admin')  roleText = 'Élite · Admin';
      else if(apiRol==='coach') roleText = label + ' · Coach';
      if(rl) rl.textContent = roleText;

      /* Badge de plan en sidebar */
      var badge = document.getElementById('kl-plan-badge');
      if(badge){
        badge.textContent   = label;
        badge.style.color   = color;
        badge.style.borderColor = color+'55';
        badge.style.background  = color+'18';
      }

      /* Control de módulos: bloquear los que no corresponden al plan */
      var allowed = (PLAN_MODULES[plan] || []).slice();

      document.querySelectorAll('[data-kl-module]').forEach(function(link){
        var mod = link.getAttribute('data-kl-module');

        /* Módulo Coach: visible solo si api_rol = coach | admin */
        if(mod === 'coach'){
          var hasCoach = (apiRol==='coach' || apiRol==='admin');
          link.style.display = hasCoach ? '' : 'none';
          return;
        }

        /* Módulo Sync: visible solo para admin */
        if(mod === 'sync'){
          link.style.display = apiRol==='admin' ? '' : 'none';
          return;
        }

        /* Módulos del plan */
        if(allowed.indexOf(mod) === -1){
          link.classList.add('kl-locked');
          link.removeAttribute('href');
          link.style.opacity = '0.45';
          link.style.cursor  = 'not-allowed';
          link.title = 'Requiere plan superior';
        }
      });
    }

    /* ── Botón Sync Garmin (si existe en la página) ── */
    var syncBtn = document.getElementById('kl-sync-btn');
    if(syncBtn){
      syncBtn.addEventListener('click', function(){
        var tok = localStorage.getItem('lx_co_token');
        if(!tok){ alert('Sesión no disponible'); return; }
        syncBtn.disabled = true;
        syncBtn.textContent = 'Sincronizando…';
        var _syncApi = (window.location.protocol==='file:'?'http://localhost:8000/api':window.location.origin+'/api');
        fetch(_syncApi+'/personal/sync', {
          method: 'POST',
          headers: {Authorization: 'Bearer '+tok}
        }).then(function(r){ return r.json(); })
        .then(function(d){
          syncBtn.textContent = 'Sync iniciado ✓';
          setTimeout(function(){ syncBtn.textContent='↻ Sync Garmin'; syncBtn.disabled=false; }, 4000);
        }).catch(function(){
          syncBtn.textContent = 'Error';
          setTimeout(function(){ syncBtn.textContent='↻ Sync Garmin'; syncBtn.disabled=false; }, 2000);
        });
      });
    }
  });


  /* ── Toast global de errores de API ─────────────────────── */
  window.lxToast = (function(){
    var el = null;
    var timer = null;

    function ensureEl(){
      if(el) return el;
      el = document.createElement('div');
      el.id = 'lx-toast';
      el.style.cssText = [
        'position:fixed','bottom:1.5rem','left:50%','transform:translateX(-50%) translateY(8px)',
        'z-index:99999','min-width:280px','max-width:480px',
        'display:flex','align-items:center','gap:.65rem',
        'padding:.7rem 1rem .7rem .85rem',
        'border-radius:8px','border:1px solid var(--border)',
        'font-family:"Inter",sans-serif','font-size:.8rem','line-height:1.4',
        'background:#08121E','color:#F0F9FF',
        'box-shadow:0 6px 32px rgba(0,0,0,.6)',
        'opacity:0','transition:opacity .22s ease,transform .22s ease',
        'pointer-events:none'
      ].join(';');
      document.body.appendChild(el);
      return el;
    }

    function show(msg, type, duration){
      var t = ensureEl();
      var colors = {
        error:   {border:'rgba(239,68,68,.35)',  icon:'⚠',  color:'#FCA5A5'},
        success: {border:'rgba(16,185,129,.35)', icon:'✓',  color:'#6EE7B7'},
        info:    {border:'rgba(14,165,233,.35)', icon:'ℹ',  color:'#7FB3CC'},
        warn:    {border:'rgba(240,165,0,.35)',  icon:'⚡', color:'#FCD34D'}
      };
      var c = colors[type] || colors.info;
      t.style.borderColor = c.border;
      t.innerHTML = '<span style="color:'+c.color+';font-size:1rem;flex-shrink:0">'+c.icon+'</span>'
        + '<span style="flex:1">'+msg+'</span>'
        + '<button onclick="lxToast.hide()" style="background:none;border:none;cursor:pointer;color:#3D6880;font-size:.85rem;padding:.1rem .2rem;flex-shrink:0;line-height:1">✕</button>';
      t.style.pointerEvents = 'auto';
      t.style.transform = 'translateX(-50%) translateY(0)';
      t.style.opacity   = '1';

      if(timer) clearTimeout(timer);
      timer = setTimeout(function(){ hide(); }, duration || (type==='error' ? 5000 : 3000));
    }

    function hide(){
      if(!el) return;
      el.style.opacity   = '0';
      el.style.transform = 'translateX(-50%) translateY(8px)';
      el.style.pointerEvents = 'none';
      if(timer){ clearTimeout(timer); timer = null; }
    }

    return { show:show, hide:hide,
      error:   function(m){ show(m,'error');   },
      success: function(m){ show(m,'success'); },
      info:    function(m){ show(m,'info');    },
      warn:    function(m){ show(m,'warn');    }
    };
  })();

  /* Patch global fetch para interceptar 401 y errores de red ─ */
  (function(){
    var _fetch = window.fetch;
    window.fetch = function(url, opts){
      return _fetch(url, opts).then(function(r){
        if(r.status === 401){
          lxToast.warn('Sesión expirada — vuelve a ingresar');
          setTimeout(function(){ location.replace('login.html'); }, 2200);
        }
        return r;
      }).catch(function(err){
        var urlStr = typeof url === 'string' ? url : url.url;
        if(urlStr && urlStr.indexOf('/api/') >= 0){
          lxToast.error('Sin conexión al servidor — modo offline');
        }
        return Promise.reject(err);
      });
    };
  })();

})();
