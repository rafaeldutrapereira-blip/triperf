/* LabX — nav.js  v3 — Sidebar dinámico desde routesConfig
   Patrón: datos (LX_ROUTES) → renderSidebar() → DOM
   Las páginas solo necesitan: <aside id="sidebar"></aside>
                               <header class="sb-topbar"></header>
                               <div class="sb-overlay" id="sb-overlay"></div>    */
(function(){

  /* ═══════════════════════════════════════════════════════════════
     1.  SIDEBAR OPEN / CLOSE
  ═══════════════════════════════════════════════════════════════ */
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
  window.sbToggle = function(){ var s=document.getElementById('sidebar'); if(s&&s.classList.contains('open')) sbClose(); else sbOpen(); };
  window.sbClose  = sbClose;
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') sbClose(); });

  /* ═══════════════════════════════════════════════════════════════
     2.  HELPERS — se leen de LX_ROUTES en tiempo de ejecución
         (no en captura del IIFE) para garantizar que
         routes.config.js ya cargó antes de DOMContentLoaded
  ═══════════════════════════════════════════════════════════════ */
  function _routes(){ return window.LX_ROUTES || null; }

  function _canAccess(sess, modId){
    var R = _routes();
    if(R) return R.canAccess(sess, modId);
    /* fallback mínimo */
    var p = (sess && sess.plan) || 'basic';
    var m = {
      basic:    ['dashboard','athlete_profile'],
      agegroup: ['dashboard','athlete_profile','training_plan','nutrition','analytics',
               'race_predictor','year_in_review','community','recovery','mental','race_day'],
      elite:  ['dashboard','athlete_profile','training_plan','nutrition','analytics',
               'blood_labs','training_detail','race_predictor','year_in_review','community',
               'recovery','mental','race_day','ai_coach','adaptive','indoor_workout']
    };
    return ((m[p]||m.basic).indexOf(modId) !== -1);
  }

  function _reqPlanLabel(modId){
    var R = _routes();
    if(R) return R.requiredPlanLabel(modId);
    var e = ['blood_labs','training_detail','ai_coach','adaptive','indoor_workout'];
    return e.indexOf(modId) !== -1 ? 'Elite' : 'Agegroup';
  }

  var PLAN_LABELS = { basic:'Básico', agegroup:'Agegroup', elite:'Élite' };
  var PLAN_COLORS = { basic:'#0EA5E9', agegroup:'#A855F7', elite:'#F0A500' };

  function _escH(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

  /* ═══════════════════════════════════════════════════════════════
     3.  SVG CONSTANTS
  ═══════════════════════════════════════════════════════════════ */
  var _FLOWER_36 =
    '<svg class="sbl-svg" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
    '<defs><radialGradient id="sbl-gw" cx="50%" cy="50%" r="50%">' +
    '<stop offset="0%" stop-color="#FF6535" stop-opacity=".6"/>' +
    '<stop offset="100%" stop-color="#FF6535" stop-opacity="0"/>' +
    '</radialGradient></defs>' +
    '<g class="sbl-arcs">' +
      '<circle cx="50" cy="50" r="44" stroke="#F0A500" stroke-width="1.5" stroke-dasharray="62 214" stroke-linecap="round" transform="rotate(28 50 50)" stroke-opacity=".7"/>' +
      '<circle cx="50" cy="50" r="40" stroke="#0EA5E9" stroke-width=".8" stroke-dasharray="23 231" stroke-linecap="round" transform="rotate(-90 50 50)" stroke-opacity=".6"/>' +
    '</g>' +
    '<g class="sbl-flower">' +
      '<circle cx="50" cy="50" r="13" stroke="rgba(255,101,53,.28)" stroke-width=".8" fill="rgba(255,101,53,.05)"/>' +
      '<circle cx="63" cy="50" r="13" stroke="rgba(255,101,53,.2)" stroke-width=".6" fill="rgba(255,101,53,.03)"/>' +
      '<circle cx="56.5" cy="38.8" r="13" stroke="rgba(240,165,0,.2)" stroke-width=".6" fill="rgba(240,165,0,.03)"/>' +
      '<circle cx="43.5" cy="38.8" r="13" stroke="rgba(14,165,233,.2)" stroke-width=".6" fill="rgba(14,165,233,.03)"/>' +
      '<circle cx="37" cy="50" r="13" stroke="rgba(255,101,53,.2)" stroke-width=".6" fill="rgba(255,101,53,.03)"/>' +
      '<circle cx="43.5" cy="61.2" r="13" stroke="rgba(240,165,0,.2)" stroke-width=".6" fill="rgba(240,165,0,.03)"/>' +
      '<circle cx="56.5" cy="61.2" r="13" stroke="rgba(14,165,233,.2)" stroke-width=".6" fill="rgba(14,165,233,.03)"/>' +
    '</g>' +
    '<circle cx="50" cy="50" r="9.5" fill="url(#sbl-gw)"/>' +
    '<circle cx="50" cy="50" r="6" fill="rgba(255,101,53,.12)" stroke="rgba(255,101,53,.35)" stroke-width=".8"/>' +
    '<text x="50" y="55.5" text-anchor="middle" font-size="7.5" font-family="serif" style="filter:drop-shadow(0 0 3px rgba(255,101,53,.8))">&#x1F33A;</text>' +
    '</svg>';

  /* versión 28px para topbar mobile */
  var _FLOWER_28 = _FLOWER_36.replace('class="sbl-svg"','class="sbl-svg" style="width:28px;height:28px"');

  var _LOCK_SVG =
    '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">' +
    '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';

  var _SYNC_SVG =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">' +
    '<path d="M23 4v6h-6"/><path d="M1 20v-6h6"/>' +
    '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10"/>' +
    '<path d="M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>';

  var _LOGOUT_SVG =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">' +
    '<path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/>' +
    '<polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>';

  /* ═══════════════════════════════════════════════════════════════
     4.  RENDER SIDEBAR  ← núcleo del patrón routesConfig
         Lee sesión + LX_ROUTES, genera HTML completo en un solo
         paso. No hay parche post-render, no hay flash de contenido.
  ═══════════════════════════════════════════════════════════════ */
  function renderSidebar(sess){
    var sidebar = document.getElementById('sidebar');
    var topbar  = document.querySelector('header.sb-topbar');
    var overlay = document.getElementById('sb-overlay');
    if(!sidebar) return;

    var page   = (window.location.pathname.split('/').pop() || 'dashboard.html');
    var plan   = (sess && sess.plan)   || 'basic';
    var apiRol = (sess && sess.api_rol)|| '';
    var name   = (sess && (sess.name || sess.username)) || 'Usuario';
    var init   = (sess && (sess.initials || (sess.name ? sess.name[0].toUpperCase() : 'U'))) || '?';
    var label  = PLAN_LABELS[plan] || 'Básico';
    var color  = PLAN_COLORS[plan] || '#0EA5E9';

    var roleText = label;
    if(apiRol === 'admin')      roleText = 'Élite · Admin';
    else if(apiRol === 'coach') roleText = label + ' · Coach';

    /* ── Construir links desde routesConfig ─── */
    var R     = _routes();
    var mods  = R ? R.modules.filter(function(m){ return m.sidebar && m.id; }) : [];
    var links = '';

    mods.forEach(function(m){
      /* Coach/admin only → hide for athletes */
      var coachOnly = m.roles && m.roles.length > 0 &&
                      m.roles.every(function(r){ return r==='coach'||r==='admin'; });
      if(coachOnly && apiRol!=='coach' && apiRol!=='admin') return;

      var active   = (m.file === page);
      var allowed  = sess ? _canAccess(sess, m.id) : false;
      var reqPlan  = allowed ? '' : _reqPlanLabel(m.id);
      var cls      = 'sb-lnk' + (active ? ' on' : '') + (allowed ? '' : ' kl-locked');
      var icon     = m.icon || '';
      var lockEl   = allowed ? '' : '<span class="sb-lock-icon">' + _LOCK_SVG + '</span>';

      if(allowed){
        links += '<a href="' + _escH(m.file) + '" class="' + cls + '" data-kl-module="' + m.id + '">' +
                 icon + m.label + '</a>';
      } else {
        /* Locked: sin href, click → upgrade wall */
        links += '<a class="' + cls + '" data-kl-module="' + m.id + '"' +
                 ' title="Requiere plan ' + _escH(reqPlan) + '"' +
                 ' onclick="showUpgradeWall(\'' + _escH(reqPlan) + '\',\'' + m.id + '\')">' +
                 icon + m.label + lockEl + '</a>';
      }
    });

    /* ── Sidebar HTML ─── */
    sidebar.innerHTML =
      '<div class="sb-brand">' +
        '<a href="landing.html" class="sb-logo">Lab' + _FLOWER_36 + '<span>X</span></a>' +
        '<div class="sb-tagline" data-i18n="app_tagline">Where Champions Are Built</div>' +
      '</div>' +
      '<nav class="sb-nav" aria-label="M&#xF3;dulos">' +
        '<span class="sb-sect" data-i18n="nav_modules">M&#xF3;dulos</span>' +
        links +
      '</nav>' +
      '<div class="sb-sep"></div>' +
      '<div class="sb-foot">' +
        '<div class="sb-user">' +
          '<div class="sb-avatar" id="kl-sb-avatar">' + _escH(init) + '</div>' +
          '<div>' +
            '<div class="sb-uname" id="kl-sb-uname">' + _escH(name) + '</div>' +
            '<div class="sb-urole" id="kl-sb-urole">' + _escH(roleText) + '</div>' +
          '</div>' +
        '</div>' +
        '<button onclick="KL.logout()" class="sb-logout" title="Salir" aria-label="Salir">' + _LOGOUT_SVG + '</button>' +
      '</div>';

    /* ── Topbar mobile ─── */
    if(topbar){
      topbar.innerHTML =
        '<button class="sb-hamburger" id="sb-ham" onclick="sbToggle()" aria-label="Menu">' +
          '<span></span><span></span><span></span>' +
        '</button>' +
        '<a href="landing.html" class="sb-tb-logo">Lab' + _FLOWER_28 + '<span>X</span></a>' +
        '<div class="sb-tb-av" id="kl-sb-av-tb">' + _escH(init) + '</div>';
    }

    /* ── Overlay ─── */
    if(overlay) overlay.onclick = sbClose;
  }

  /* ═══════════════════════════════════════════════════════════════
     5.  SYNC GARMIN (privado, expuesto vía window para compatibilidad)
  ═══════════════════════════════════════════════════════════════ */
  function _syncGarmin(btn){
    var tok = localStorage.getItem('lx_co_token');
    if(!tok){ lxToast && lxToast.warn('Sesión no disponible'); return; }
    if(btn){ btn.disabled=true; btn.classList.add('spin'); }
    var API = (window.location.protocol==='file:' ? 'http://localhost:8000/api' : window.location.origin+'/api');
    fetch(API+'/personal/sync', { method:'POST', headers:{Authorization:'Bearer '+tok} })
      .then(function(r){ return r.json(); })
      .then(function(){ if(btn){ btn.textContent='Sync ✓'; setTimeout(function(){ btn.innerHTML=_SYNC_SVG+'Sync Garmin'; btn.disabled=false; btn.classList.remove('spin'); },4000); } })
      .catch(function(){ if(btn){ btn.textContent='Error'; setTimeout(function(){ btn.innerHTML=_SYNC_SVG+'Sync Garmin'; btn.disabled=false; btn.classList.remove('spin'); },2000); } });
  }
  window.syncGarmin = _syncGarmin; /* compatibilidad con onclicks existentes */

  /* ═══════════════════════════════════════════════════════════════
     6.  DOM READY — punto de entrada principal
  ═══════════════════════════════════════════════════════════════ */
  function _onReady(){
    var sess = null;
    try{ sess = JSON.parse(sessionStorage.getItem('kl_s') || localStorage.getItem('kl_s') || 'null'); }catch(e){}

    /* 1. Renderizar sidebar completo con estado correcto desde el inicio */
    renderSidebar(sess);

    /* 2. Guard de URL (LX_ROUTES ya está cargado en este punto) */
    if(sess && _routes()) _routes().guard();

    /* 3. Rellenar elementos fuera del sidebar que usen session */
    if(sess){
      var init = sess.initials || (sess.name ? sess.name[0].toUpperCase() : 'U');
      ['kl-uname','kl-greeting-name'].forEach(function(id){
        var el = document.getElementById(id);
        if(el) el.textContent = sess.name ? sess.name.split(' ')[0] : sess.username;
      });
      var av = document.getElementById('kl-avatar');
      if(av) av.textContent = init;
      var fn = document.getElementById('kl-fullname');
      if(fn) fn.textContent = sess.name || '';
      var rt = document.getElementById('kl-role-tag');
      if(rt) rt.textContent = sess.role || '';
    }

    /* 4. Dashboard: manejar ?locked= param */
    var params = new URLSearchParams(window.location.search);
    var locked = params.get('locked');
    if(locked){
      history.replaceState({}, '', window.location.pathname);
      showUpgradeWall(null, locked);
    }
  }

  /* nav.js está al final del <body>: el <aside id="sidebar"> ya existe en el DOM.
     Llamar _onReady() directo en sincrónico. No usar DOMContentLoaded. */
  _onReady();

  /* ═══════════════════════════════════════════════════════════════
     7.  TOAST GLOBAL
  ═══════════════════════════════════════════════════════════════ */
  window.lxToast = (function(){
    var el=null, timer=null;
    function ensure(){
      if(el) return el;
      el=document.createElement('div'); el.id='lx-toast';
      el.style.cssText='position:fixed;bottom:1.5rem;left:50%;transform:translateX(-50%) translateY(8px);z-index:99999;min-width:280px;max-width:480px;display:flex;align-items:center;gap:.65rem;padding:.7rem 1rem .7rem .85rem;border-radius:8px;border:1px solid var(--border);font-family:"Inter",sans-serif;font-size:.8rem;line-height:1.4;background:#08121E;color:#F0F9FF;box-shadow:0 6px 32px rgba(0,0,0,.6);opacity:0;transition:opacity .22s ease,transform .22s ease;pointer-events:none';
      document.body.appendChild(el); return el;
    }
    function show(msg, type, dur){
      var t=ensure();
      var C={error:{border:'rgba(239,68,68,.35)',icon:'⚠',color:'#FCA5A5'},
             success:{border:'rgba(16,185,129,.35)',icon:'✓',color:'#6EE7B7'},
             info:{border:'rgba(14,165,233,.35)',icon:'ℹ',color:'#7FB3CC'},
             warn:{border:'rgba(240,165,0,.35)',icon:'⚡',color:'#FCD34D'}};
      var c=C[type]||C.info;
      t.style.borderColor=c.border;
      t.innerHTML='<span style="color:'+c.color+';font-size:1rem;flex-shrink:0">'+c.icon+'</span>'+
        '<span style="flex:1">'+_escH(msg)+'</span>'+
        '<button onclick="lxToast.hide()" style="background:none;border:none;cursor:pointer;color:#3D6880;font-size:.85rem;padding:.1rem .2rem;flex-shrink:0;line-height:1">✕</button>';
      t.style.pointerEvents='auto'; t.style.transform='translateX(-50%) translateY(0)'; t.style.opacity='1';
      if(timer) clearTimeout(timer);
      timer=setTimeout(hide, dur||(type==='error'?5000:3000));
    }
    function hide(){ if(!el) return; el.style.opacity='0'; el.style.transform='translateX(-50%) translateY(8px)'; el.style.pointerEvents='none'; if(timer){clearTimeout(timer);timer=null;} }
    return { show:show, hide:hide, error:function(m){show(m,'error');}, success:function(m){show(m,'success');}, info:function(m){show(m,'info');}, warn:function(m){show(m,'warn');} };
  })();

  /* ═══════════════════════════════════════════════════════════════
     8.  AI COACH WIDGET FLOTANTE
  ═══════════════════════════════════════════════════════════════ */
  (function(){
    var API=(window.location.protocol==='file:'?'http://localhost:8000':'')+'/api';
    var hist=[]; var open=false;
    function tok(){ return localStorage.getItem('lx_co_token')||''; }

    function injectStyles(){
      if(document.getElementById('lx-ai-style')) return;
      var s=document.createElement('style'); s.id='lx-ai-style';
      s.textContent='#lx-ai-btn{position:fixed;bottom:1.5rem;right:1.5rem;z-index:9990;width:52px;height:52px;border-radius:50%;border:none;cursor:pointer;background:linear-gradient(135deg,#FF6535,#E8490A);box-shadow:0 4px 20px rgba(255,101,53,.45);display:flex;align-items:center;justify-content:center;transition:transform .18s,box-shadow .18s;}#lx-ai-btn:hover{transform:scale(1.08);box-shadow:0 6px 28px rgba(255,101,53,.6);}#lx-ai-panel{position:fixed;bottom:4.8rem;right:1.5rem;z-index:9991;width:340px;max-width:calc(100vw - 2rem);background:#08121E;border:1px solid rgba(8,116,174,.28);border-radius:14px;box-shadow:0 12px 48px rgba(0,0,0,.75);display:none;flex-direction:column;overflow:hidden;}#lx-ai-panel.open{display:flex;}#lx-ai-head{padding:.7rem 1rem;border-bottom:1px solid rgba(8,116,174,.18);display:flex;align-items:center;justify-content:space-between;background:rgba(255,101,53,.06);}.lx-ai-title{font-family:"Oswald",sans-serif;font-size:.82rem;font-weight:600;text-transform:uppercase;letter-spacing:.07em;color:#FF6535;}.lx-ai-close{background:none;border:none;cursor:pointer;color:#4A7A96;font-size:1rem;line-height:1;padding:.1rem .3rem;}#lx-ai-msgs{flex:1;max-height:340px;overflow-y:auto;padding:.8rem;display:flex;flex-direction:column;gap:.55rem;}.lx-ai-msg{padding:.55rem .75rem;border-radius:8px;font-size:.78rem;line-height:1.5;max-width:94%;}.lx-ai-msg.user{background:rgba(255,101,53,.12);border:1px solid rgba(255,101,53,.2);align-self:flex-end;color:#E8F4F8;}.lx-ai-msg.ai{background:rgba(14,165,233,.07);border:1px solid rgba(14,165,233,.18);align-self:flex-start;color:rgba(232,244,248,.88);}.lx-ai-msg.loading{color:#4A7A96;font-style:italic;}#lx-ai-form{padding:.65rem;border-top:1px solid rgba(8,116,174,.18);display:flex;gap:.4rem;background:#06101A;}#lx-ai-inp{flex:1;background:rgba(255,255,255,.04);border:1px solid rgba(8,116,174,.2);border-radius:7px;padding:.45rem .65rem;color:#E8F4F8;font-size:.78rem;font-family:"Inter",sans-serif;outline:none;resize:none;}#lx-ai-inp:focus{border-color:rgba(255,101,53,.4);}#lx-ai-send{background:#FF6535;border:none;cursor:pointer;border-radius:7px;padding:.45rem .7rem;color:#fff;font-size:.8rem;font-weight:600;transition:background .15s;}#lx-ai-send:hover{background:#E8490A;}#lx-ai-send:disabled{background:#444;cursor:not-allowed;}';
      document.head.appendChild(s);
    }

    function injectWidget(){
      if(document.getElementById('lx-ai-btn')) return;
      injectStyles();
      var btn=document.createElement('button'); btn.id='lx-ai-btn'; btn.title='Coach IA';
      btn.innerHTML='<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><path d="M12 2a10 10 0 0 1 10 10c0 5.52-4.48 10-10 10a9.95 9.95 0 0 1-4.77-1.21L2 22l1.21-5.23A9.95 9.95 0 0 1 2 12 10 10 0 0 1 12 2z"/><path d="M8 12h8M8 8h5"/></svg>';
      btn.onclick=togglePanel;
      var panel=document.createElement('div'); panel.id='lx-ai-panel';
      panel.innerHTML='<div id="lx-ai-head"><span class="lx-ai-title">&#x26A1; Coach IA &middot; LabX</span><button class="lx-ai-close" onclick="document.getElementById(\'lx-ai-panel\').classList.remove(\'open\')">&#x2715;</button></div><div id="lx-ai-msgs"><div class="lx-ai-msg ai">Hola! Soy tu Coach IA. Pref&uacute;ntame sobre tu entrenamiento, carga, nutrici&oacute;n o estrategia de carrera.</div></div><form id="lx-ai-form" onsubmit="return false;"><textarea id="lx-ai-inp" rows="2" placeholder="Pregunta algo sobre tu entrenamiento&hellip;" onkeydown="lxAiKey(event)"></textarea><button id="lx-ai-send" type="button" onclick="lxAiSend()">&#x2192;</button></form>';
      document.body.appendChild(btn); document.body.appendChild(panel);
    }

    function togglePanel(){ var p=document.getElementById('lx-ai-panel'); if(p){ p.classList.toggle('open'); if(p.classList.contains('open')){ var i=document.getElementById('lx-ai-inp'); if(i)i.focus(); } } }

    window.lxAiKey=function(e){ if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();window.lxAiSend();} };
    window.lxAiSend=function(){
      var inp=document.getElementById('lx-ai-inp');
      var msgs=document.getElementById('lx-ai-msgs');
      var btn=document.getElementById('lx-ai-send');
      var msg=(inp.value||'').trim(); if(!msg) return;
      inp.value=''; btn.disabled=true;
      var uDiv=document.createElement('div'); uDiv.className='lx-ai-msg user'; uDiv.textContent=msg; msgs.appendChild(uDiv);
      var loading=document.createElement('div'); loading.className='lx-ai-msg ai loading'; loading.textContent='Pensando…'; msgs.appendChild(loading);
      msgs.scrollTop=msgs.scrollHeight;
      var t=tok();
      fetch(API+'/ai/coach-suggest',{method:'POST',headers:Object.assign({'Content-Type':'application/json'},t?{'Authorization':'Bearer '+t}:{}),credentials:'include',body:JSON.stringify({message:msg,history:hist})})
        .then(function(r){return r.json();})
        .then(function(d){ loading.remove(); var aDiv=document.createElement('div'); aDiv.className='lx-ai-msg ai'; aDiv.textContent=d.answer||d.detail||'Sin respuesta.'; msgs.appendChild(aDiv); msgs.scrollTop=msgs.scrollHeight; hist.push({role:'user',content:msg}); hist.push({role:'assistant',content:d.answer||''}); if(hist.length>20)hist=hist.slice(-20); })
        .catch(function(){ loading.textContent='Error de conexi\xf3n. Intenta de nuevo.'; loading.style.color='#FCA5A5'; })
        .finally(function(){ btn.disabled=false; inp.focus(); });
    };
    injectWidget();
  })();

  /* ═══════════════════════════════════════════════════════════════
     9.  FETCH PATCH — credentials + 401 intercept
  ═══════════════════════════════════════════════════════════════ */
  (function(){
    var _f=window.fetch;
    window.fetch=function(url,opts){
      var u=typeof url==='string'?url:(url&&url.url)||'';
      if(u.indexOf('/api/')>=0){ opts=Object.assign({},opts||{}); opts.credentials=opts.credentials||'include'; }
      return _f(url,opts).then(function(r){
        if(r.status===401){ lxToast.warn('Sesi\xf3n expirada — vuelve a ingresar'); setTimeout(function(){ sessionStorage.setItem('lx_next_url',window.location.href); location.replace('login.html'); },2200); }
        return r;
      }).catch(function(err){
        var us=typeof url==='string'?url:url.url;
        if(us&&us.indexOf('/api/')>=0) lxToast.error('Sin conexi\xf3n al servidor — modo offline');
        return Promise.reject(err);
      });
    };
  })();

  /* ═══════════════════════════════════════════════════════════════
     10. lxUI — estados loading / error / vacío
  ═══════════════════════════════════════════════════════════════ */
  window.lxUI=(function(){
    var SP='<svg width="32" height="32" viewBox="0 0 32 32" fill="none"><circle cx="16" cy="16" r="12" stroke="rgba(8,116,174,.25)" stroke-width="3"/><path d="M16 4a12 12 0 0 1 12 12" stroke="#0EA5E9" stroke-width="3" stroke-linecap="round"><animateTransform attributeName="transform" type="rotate" from="0 16 16" to="360 16 16" dur=".8s" repeatCount="indefinite"/></path></svg>';
    function wrap(content){ return '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:40px;color:#7FB3CC;font-size:.85rem">'+content+'</div>'; }
    function setLoading(el,msg){ if(el) el.innerHTML=wrap(SP+'<span>'+_escH(msg||'Cargando…')+'</span>'); }
    function setError(el,msg,retry){
      if(!el) return;
      var bid='lx-rt-'+Math.random().toString(36).slice(2);
      el.innerHTML=wrap('<span style="font-size:28px">&#x26A0;&#xFE0F;</span><span>'+_escH(msg||'Error al cargar datos')+'</span>'+(retry?'<button id="'+_escH(bid)+'" style="margin-top:4px;background:rgba(14,165,233,.12);border:1px solid rgba(14,165,233,.3);color:#0EA5E9;border-radius:6px;padding:6px 16px;cursor:pointer;font-size:.82rem">Reintentar</button>':''));
      if(retry){ var b=el.querySelector('#'+bid); if(b) b.addEventListener('click',retry); }
    }
    function setEmpty(el,msg,icon){ if(el) el.innerHTML=wrap('<span style="font-size:32px">'+_escH(icon||'&#x1F4CB;')+'</span><span>'+_escH(msg||'Sin datos a\xfan')+'</span>'); }
    function clear(el){ if(el) el.innerHTML=''; }
    return { loading:setLoading, error:setError, empty:setEmpty, clear:clear };
  })();

  /* ═══════════════════════════════════════════════════════════════
     11. UPGRADE WALL
  ═══════════════════════════════════════════════════════════════ */
  window.showUpgradeWall=function(reqPlan, modName){
    if(document.getElementById('lx-upgrade-wall')) return;
    if(!reqPlan) reqPlan=_reqPlanLabel(modName);
    var modLabels={
      training_plan:'Plan de Entrenamiento',nutrition:'Nutrici\xf3n Inteligente',
      analytics:'Analytics Avanzado',blood_labs:'Blood Labs',
      training_detail:'Detalle de Sesi\xf3n',race_predictor:'Predictor de Carrera',
      year_in_review:'Year in Review',community:'Comunidad',
      recovery:'Recuperaci\xf3n &amp; HRV',mental:'Rendimiento Mental',
      race_day:'Race Day Intelligence',ai_coach:'AI Coach',
      adaptive:'Plan Adaptativo',indoor_workout:'Indoor Workout'
    };
    var modLabel=modLabels[modName]||'este m\xf3dulo';
    var wall=document.createElement('div'); wall.id='lx-upgrade-wall';
    wall.innerHTML=
      '<div class="lx-uw-box">'+
        '<div class="lx-uw-lock">&#x1F512;</div>'+
        '<div class="lx-uw-plan-badge">Requiere Plan '+_escH(reqPlan)+'</div>'+
        '<div class="lx-uw-title">M\xf3dulo Premium</div>'+
        '<div class="lx-uw-sub"><strong>'+modLabel+'</strong> no est\xe1 incluido en tu plan actual.<br>'+
        'Actualiza a <strong>'+_escH(reqPlan)+'</strong> para desbloquear este y m\xe1s m\xf3dulos.</div>'+
        '<a href="landing.html#planes" class="lx-uw-upgrade">'+
          '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>'+
          'Ver Planes'+
        '</a>'+
        '<a href="dashboard.html" class="lx-uw-back">← Volver al Dashboard</a>'+
      '</div>';
    document.body.appendChild(wall);
  };

  /* ═══════════════════════════════════════════════════════════════
     12. SESSION IDLE TIMEOUT (30 min)
  ═══════════════════════════════════════════════════════════════ */
  (function(){
    var IDLE=30*60*1000, WARN=60*1000, _t=null, _w=false;
    function reset(){ clearTimeout(_t); _w=false; _t=setTimeout(onIdle, IDLE-WARN); }
    function onIdle(){ if(!_w){ _w=true; lxToast.warn('Tu sesi\xf3n expirará en 1 minuto por inactividad.'); _t=setTimeout(doOut,WARN); return; } doOut(); }
    function doOut(){
      var API=(window.location.protocol==='file:'?'http://localhost:8000':'')+'/api';
      var tok=localStorage.getItem('lx_co_token')||'';
      fetch(API+'/auth/logout',{method:'POST',headers:tok?{'Authorization':'Bearer '+tok}:{},credentials:'include'})
        .finally(function(){ localStorage.removeItem('lx_co_token'); sessionStorage.removeItem('kl_s'); window.location.href='/landing.html'; });
    }
    var has=sessionStorage.getItem('kl_s')||localStorage.getItem('kl_s')||localStorage.getItem('lx_co_token');
    if(has){ ['click','keydown','scroll','mousemove','touchstart'].forEach(function(ev){ document.addEventListener(ev,reset,{passive:true}); }); reset(); }
  })();

})();
