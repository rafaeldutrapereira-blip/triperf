/**
 * dash-header.js — Header compartido (fecha + saludo + chips Readiness/Garmin
 * + botones Perfil/Actualizar Plan) para todas las páginas del atleta con
 * sidebar. dashboard.html NO lo usa: ya tiene esta misma estructura nativa
 * (con su propia lógica ligada al resto del dashboard); este módulo replica
 * ese mismo estándar visual para el resto de las páginas sin duplicar HTML/JS
 * en cada una — se incluye con un solo <script src="dash-header.js"></script>.
 */
(function(){
'use strict';

function esc(s){
  return String(s==null?'':s).replace(/[&<>"']/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}

function apiBase(){
  return window.location.protocol === 'file:' ? 'http://localhost:8000/api' : window.location.origin + '/api';
}
function authToken(){
  // El JWT real vive en localStorage.lx_co_token (mismo patrón que
  // athlete_profile.html/dashboard.html) — kl_s NUNCA trae un campo
  // "token", así que leerlo de ahí siempre devolvía vacío y dejaba los
  // fetches de este módulo sin Authorization (401 silencioso para
  // cualquier usuario recién registrado que no hubiera pasado por login.html).
  var direct = localStorage.getItem('lx_co_token');
  if(direct) return direct;
  try{
    var s = JSON.parse(sessionStorage.getItem('kl_s') || localStorage.getItem('kl_s') || 'null');
    return s && s.token ? s.token : '';
  }catch(e){ return ''; }
}
function session(){
  try{ return JSON.parse(sessionStorage.getItem('kl_s') || localStorage.getItem('kl_s') || 'null'); }
  catch(e){ return null; }
}

function pageLabel(){
  try{
    var pageName = window.location.pathname.split('/').pop() || 'dashboard.html';
    var mod = window.LX_ROUTES && window.LX_ROUTES.byFile[pageName];
    return (mod && mod.label) ? mod.label : 'Dashboard';
  }catch(e){ return 'Dashboard'; }
}

function injectCSS(){
  if(document.getElementById('dhx-css')) return;
  var s = document.createElement('style');
  s.id = 'dhx-css';
  s.textContent = [
    '.dhx{padding-top:1.5rem;background:linear-gradient(180deg,#060E1C 0%,var(--bg) 100%);border-bottom:1px solid var(--border2)}',
    '.dhx-c{max-width:1400px;margin:0 auto;padding:0 1.5rem}',
    '.dhx-inner{display:flex;align-items:center;justify-content:space-between;gap:1.25rem;flex-wrap:wrap;padding:1.5rem 0 1.4rem}',
    '.dhx-eye{font-family:"Oswald",sans-serif;font-size:.68rem;font-weight:500;letter-spacing:.2em;text-transform:uppercase;color:var(--dim);margin-bottom:.2rem}',
    /* Sin uppercase acá — es un saludo humano ("Buenos días, Rafael"), no
       una etiqueta de UI. Gritado en mayúsculas se sentía agresivo/frío
       apilado justo arriba de cualquier otro título de página. */
    '.dhx-h1{font-family:"Barlow Condensed",sans-serif;font-size:clamp(1.3rem,2.1vw,1.6rem);font-weight:800;letter-spacing:-.01em;line-height:1.1}',
    '.dhx-h1 em{color:var(--orange);font-style:normal}',
    '.dhx-right{display:flex;align-items:center;gap:.75rem;flex-wrap:wrap}',
    '.dhx-chip-row{display:flex;align-items:center;gap:.65rem;flex-wrap:wrap}',
    '.dhx-chip{display:flex;align-items:center;gap:.45rem;padding:.42rem .9rem;font-size:.78rem;color:var(--muted);background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm,8px);white-space:nowrap}',
    '.dhx-chip strong{color:var(--text);font-weight:600}',
    '.dhx-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;animation:dhx-blink 2s ease-in-out infinite}',
    '.dhx-dot-g{background:var(--green);box-shadow:0 0 7px var(--green)}',
    '.dhx-dot-c{background:var(--aqua);box-shadow:0 0 7px var(--aqua);animation:none}',
    '@keyframes dhx-blink{0%,100%{opacity:1}50%{opacity:.3}}',
    '.dhx-btn{display:flex;align-items:center;gap:.4rem;padding:.38rem .85rem;border-radius:20px;border:1px solid var(--border);background:transparent;color:var(--muted);font-family:"Oswald",sans-serif;font-size:.72rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;cursor:pointer;transition:all .2s;text-decoration:none}',
    '.dhx-btn:hover{border-color:var(--orange);color:var(--orange)}',
    // Campana de notificaciones sociales (kudos/comentarios/follows) —
    // el backend (CommunityNotification, /community/notifications*) ya
    // existía completo desde antes, disparándose en cada kudo/comentario/
    // follow real, pero no había NINGÚN consumidor en ningún lado (ni
    // web ni app) — el atleta nunca se enteraba. Mismo criterio de fetch
    // que readiness/garmin-sync de este archivo: una vez al cargar +
    // al abrir el dropdown, sin polling — no hay cliente SSE en el
    // frontend todavía (fuera de alcance acá, backend ya emite por SSE
    // para quien lo conecte a futuro).
    '.dhx-bell-wrap{position:relative}',
    '.dhx-bell-btn{display:flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:50%;border:1px solid var(--border);background:transparent;color:var(--muted);cursor:pointer;position:relative}',
    '.dhx-bell-btn:hover{border-color:var(--orange);color:var(--orange)}',
    '.dhx-bell-badge{position:absolute;top:-3px;right:-3px;min-width:16px;height:16px;padding:0 3px;border-radius:8px;background:var(--orange);color:#fff;font-family:"Oswald",sans-serif;font-size:.6rem;font-weight:700;display:flex;align-items:center;justify-content:center;display:none}',
    '.dhx-bell-badge.on{display:flex}',
    '.dhx-bell-panel{position:absolute;top:calc(100% + .6rem);right:0;width:320px;max-width:90vw;max-height:420px;overflow-y:auto;background:#0A1626;border:1px solid var(--border2);border-radius:12px;box-shadow:0 12px 32px rgba(0,0,0,.4);z-index:60;display:none}',
    '.dhx-bell-panel.on{display:block}',
    '.dhx-bell-head{display:flex;align-items:center;justify-content:space-between;padding:.8rem 1rem;border-bottom:1px solid var(--border2)}',
    '.dhx-bell-title{font-family:"Oswald",sans-serif;font-size:.7rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--text)}',
    '.dhx-bell-mark{font-family:"Oswald",sans-serif;font-size:.62rem;font-weight:600;color:var(--orange);cursor:pointer;background:none;border:none;letter-spacing:.04em}',
    '.dhx-bell-item{display:flex;gap:.6rem;padding:.7rem 1rem;border-bottom:1px solid rgba(255,255,255,.04);cursor:pointer}',
    '.dhx-bell-item:hover{background:rgba(255,255,255,.02)}',
    '.dhx-bell-item.unread{background:rgba(255,101,53,.06)}',
    '.dhx-bell-ico{width:28px;height:28px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:.85rem;background:var(--bg3)}',
    '.dhx-bell-body{flex:1;min-width:0}',
    '.dhx-bell-text{font-size:.76rem;color:var(--text);line-height:1.35}',
    '.dhx-bell-text strong{font-weight:700}',
    '.dhx-bell-time{font-size:.62rem;color:var(--dim);margin-top:.15rem}',
    '.dhx-bell-empty{padding:1.6rem 1rem;text-align:center;font-size:.76rem;color:var(--dim)}',
    // Páginas con wrapper .app/.main (style.css) envuelven TODO su contenido
    // -incluido este header- en el padding de .main (1.5rem arriba +
    // clamp(1rem,3vw,2rem) a los lados). Las páginas con <header
    // class="sb-topbar"> plano no tienen ese padding extra. Sin esto, el
    // mismo header queda en dos posiciones distintas según la página
    // (ver mount()) — se cancela acá para que la posición sea idéntica
    // siempre, independiente de cuál de los dos layouts use la página.
    '.dhx-in-main{margin:calc(-1*(56px + 1.5rem)) clamp(-2rem,-3vw,-1rem) 0}',
    '@media (min-width:769px){.dhx-in-main{margin-top:-1.5rem}}',
  ].join('\n');
  document.head.appendChild(s);
}

function buildHTML(){
  return ''
    + '<div class="dhx" role="banner">'
    +   '<div class="dhx-c">'
    +     '<div class="dhx-inner">'
    +       '<div>'
    +         '<div class="dhx-eye" id="dhx-date-lbl">Cargando...</div>'
    +         '<h1 class="dhx-h1"><span id="dhx-greeting-txt">Buenos días</span>, <em id="dhx-greeting-name">Atleta</em></h1>'
    +       '</div>'
    +       '<div class="dhx-right">'
    +         '<div class="dhx-chip-row" role="status" aria-live="polite">'
    +           '<div class="dhx-chip"><span class="dhx-dot dhx-dot-g"></span>Readiness <strong id="dhx-readiness-val">— / 100</strong></div>'
    +           '<div class="dhx-chip" style="border-color:rgba(34,211,238,.22)"><span class="dhx-dot dhx-dot-c"></span><span style="color:var(--aqua);font-size:.7rem;font-weight:700;letter-spacing:.05em">GARMIN</span><span id="dhx-garmin-chip">—</span></div>'
    +         '</div>'
    +         '<div class="dhx-bell-wrap">'
    +           '<button class="dhx-bell-btn" id="dhx-bell-btn" aria-label="Notificaciones" onclick="window.__dhxToggleBell && window.__dhxToggleBell()">'
    +             '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>'
    +             '<span class="dhx-bell-badge" id="dhx-bell-badge">0</span>'
    +           '</button>'
    +           '<div class="dhx-bell-panel" id="dhx-bell-panel">'
    +             '<div class="dhx-bell-head"><span class="dhx-bell-title">Notificaciones</span><button class="dhx-bell-mark" onclick="window.__dhxMarkRead && window.__dhxMarkRead()">Marcar leídas</button></div>'
    +             '<div id="dhx-bell-list"><div class="dhx-bell-empty">Cargando...</div></div>'
    +           '</div>'
    +         '</div>'
    +         '<a href="athlete_profile.html" class="dhx-btn" aria-label="Ir al Perfil del Atleta">'
    +           '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>'
    +           'Perfil del Atleta'
    +         '</a>'
    +         '<button class="dhx-btn" id="dhx-btn-upgrade" style="border-color:rgba(168,85,247,.35);color:#C084FC;display:none" aria-label="Actualizar plan">'
    +           '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>'
    +           '<span id="dhx-btn-upgrade-label">Actualizar Plan</span>'
    +         '</button>'
    +       '</div>'
    +     '</div>'
    +   '</div>'
    + '</div>';
}

function mount(){
  if(document.getElementById('dhx-root')) return null;
  var host = document.getElementById('dash-header-host');
  var wrap = document.createElement('div');
  wrap.id = 'dhx-root';
  if(host){
    host.appendChild(wrap);
  } else {
    var topbar = document.querySelector('.sb-topbar');
    var mainEl = document.querySelector('main.main, #main-content');
    // Algunas páginas envuelven #sidebar + .sb-topbar + <main class="main">
    // en un <div class="app"> con display:flex (ej. athlete_profile.html,
    // analytics.html). Insertar ahí como hermano del topbar lo vuelve un
    // ítem flex extra y aplasta el ancho de <main> a casi nada — en ese
    // caso hay que insertarlo DENTRO de <main>, como primer hijo.
    if(mainEl && topbar && topbar.parentElement === mainEl.parentElement
       && getComputedStyle(topbar.parentElement).display === 'flex'){
      wrap.classList.add('dhx-in-main');
      mainEl.insertBefore(wrap, mainEl.firstChild);
    } else if(topbar && topbar.parentNode){
      topbar.parentNode.insertBefore(wrap, topbar.nextSibling);
    } else {
      document.body.insertBefore(wrap, document.body.firstChild);
    }
  }
  wrap.innerHTML = buildHTML();
  return wrap;
}

function updateDateGreeting(){
  var D = ['Domingo','Lunes','Martes','Miércoles','Jueves','Viernes','Sábado'];
  var M = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
  var n = new Date(), d = n.getDate(), mo = n.getMonth(), y = n.getFullYear();
  var lbl = document.getElementById('dhx-date-lbl');
  if(lbl) lbl.textContent = D[n.getDay()] + ', ' + d + ' ' + M[mo] + ' ' + y + ' · LabX ' + pageLabel();

  var h = n.getHours();
  var txt = h >= 5 && h < 12 ? 'Buenos días' : h >= 12 && h < 19 ? 'Buenas tardes' : 'Buenas noches';
  var g = document.getElementById('dhx-greeting-txt');
  if(g) g.textContent = txt;

  var nameEl = document.getElementById('dhx-greeting-name');
  if(nameEl){
    var sess = session();
    var fullName = (sess && sess.name) || null;
    if(!fullName){
      try{
        var prof = JSON.parse(localStorage.getItem('kl_athlete_data') || 'null');
        if(prof && prof.name) fullName = prof.name;
      }catch(e){}
    }
    if(fullName) nameEl.textContent = esc(fullName);
  }
}

function loadReadiness(){
  var el = document.getElementById('dhx-readiness-val');
  if(!el) return;
  var tok = authToken();
  fetch(apiBase() + '/readiness/daily', { headers: tok ? { Authorization: 'Bearer ' + tok } : {} })
    .then(function(r){ return r.ok ? r.json() : null; })
    .then(function(d){ if(d && d.drs != null) el.textContent = Math.round(d.drs) + ' / 100'; })
    .catch(function(){});
}

function loadGarminSync(){
  var el = document.getElementById('dhx-garmin-chip');
  if(!el) return;
  var tok = authToken();
  fetch(apiBase() + '/athlete/garmin/sync-status', { headers: { Authorization: 'Bearer ' + tok }, credentials: 'include' })
    .then(function(r){ return r.ok ? r.json() : null; })
    .then(function(d){
      if(!d || !d.last_sync){ el.textContent = 'sin sync'; return; }
      var diff = Math.round((Date.now() - new Date(d.last_sync).getTime()) / 60000);
      var label = diff < 1 ? 'ahora' : diff < 60 ? 'hace ' + diff + 'min' : diff < 1440 ? 'hace ' + Math.round(diff/60) + 'h' : 'hace ' + Math.round(diff/1440) + 'd';
      el.textContent = label;
      el.title = 'Último sync: ' + d.last_sync + ' · ' + (d.activities_total || 0) + ' actividades';
    })
    .catch(function(){ el.textContent = '—'; });
}

function setupUpgradeBtn(){
  var btn = document.getElementById('dhx-btn-upgrade');
  if(!btn) return;
  var sess = session();
  var plan = sess && (sess.plan_nivel || sess.plan);
  if(sess && plan !== 'elite' && plan !== 'coach'){
    btn.style.display = 'flex';
    var lbl = document.getElementById('dhx-btn-upgrade-label');
    if(lbl) lbl.textContent = plan === 'agegroup' ? 'Ir a Elite' : 'Actualizar Plan';
  }
  btn.addEventListener('click', function(){
    // Cada página con su propio modal interactivo de planes (dashboard.html)
    // puede exponer openUpgrade() global; el resto va directo a la
    // comparación de planes del landing — mismo destino, sin duplicar el
    // modal completo (con checkout Stripe) en 15+ páginas.
    if(typeof window.openUpgrade === 'function') window.openUpgrade();
    else window.location.href = 'landing.html#planes';
  });
}

var _DHX_NOTIF_ICO = { kudo:'🔥', comment:'💬', follow:'➕', challenge:'🏆', mention:'📣' };
function _dhxRelTime(iso){
  if(!iso) return '';
  var diff = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if(diff < 1) return 'ahora';
  if(diff < 60) return 'hace ' + diff + 'min';
  if(diff < 1440) return 'hace ' + Math.round(diff/60) + 'h';
  return 'hace ' + Math.round(diff/1440) + 'd';
}
function _dhxNotifText(n){
  var actor = '<strong>' + esc(n.actor) + '</strong>';
  if(n.notif_type === 'kudo')      return actor + ' le dio kudo a tu actividad';
  if(n.notif_type === 'comment')   return actor + ' comentó tu actividad' + (n.body ? ': "' + esc(n.body) + '"' : '');
  if(n.notif_type === 'follow')    return actor + ' empezó a seguirte';
  if(n.notif_type === 'challenge') return actor + ' ' + esc(n.body || 'te invitó a un desafío');
  if(n.notif_type === 'mention')   return actor + ' te mencionó' + (n.body ? ': "' + esc(n.body) + '"' : '');
  return esc(n.body || 'Nueva notificación');
}
function loadNotifCount(){
  var badge = document.getElementById('dhx-bell-badge');
  if(!badge) return;
  var tok = authToken();
  if(!tok) return;
  fetch(apiBase() + '/community/notifications/count', { headers: { Authorization: 'Bearer ' + tok } })
    .then(function(r){ return r.ok ? r.json() : null; })
    .then(function(d){
      var n = d && d.unread || 0;
      badge.textContent = n > 9 ? '9+' : String(n);
      badge.classList.toggle('on', n > 0);
    })
    .catch(function(){});
}
function loadNotifList(){
  var list = document.getElementById('dhx-bell-list');
  if(!list) return;
  var tok = authToken();
  fetch(apiBase() + '/community/notifications?per_page=20', { headers: { Authorization: 'Bearer ' + tok } })
    .then(function(r){ return r.ok ? r.json() : null; })
    .then(function(d){
      var items = d && d.items || [];
      if(!items.length){ list.innerHTML = '<div class="dhx-bell-empty">Sin notificaciones todavía</div>'; return; }
      list.innerHTML = items.map(function(n){
        return '<div class="dhx-bell-item' + (n.read ? '' : ' unread') + '" onclick="window.location.href=\'community.html\'">'
          + '<div class="dhx-bell-ico">' + (_DHX_NOTIF_ICO[n.type] || '🔔') + '</div>'
          + '<div class="dhx-bell-body"><div class="dhx-bell-text">' + _dhxNotifText({actor:n.actor, notif_type:n.type, body:n.body}) + '</div>'
          + '<div class="dhx-bell-time">' + _dhxRelTime(n.created_at) + '</div></div>'
          + '</div>';
      }).join('');
    })
    .catch(function(){ list.innerHTML = '<div class="dhx-bell-empty">Error al cargar</div>'; });
}
function setupBell(){
  var panel = document.getElementById('dhx-bell-panel');
  if(!panel) return;
  var loaded = false;
  window.__dhxToggleBell = function(){
    var on = panel.classList.toggle('on');
    if(on && !loaded){ loaded = true; loadNotifList(); }
  };
  window.__dhxMarkRead = function(){
    var tok = authToken();
    fetch(apiBase() + '/community/notifications/mark-read', { method:'POST', headers: { Authorization: 'Bearer ' + tok } })
      .then(function(){
        loadNotifCount();
        panel.querySelectorAll('.dhx-bell-item.unread').forEach(function(el){ el.classList.remove('unread'); });
      }).catch(function(){});
  };
  document.addEventListener('click', function(e){
    if(!panel.classList.contains('on')) return;
    if(panel.contains(e.target) || e.target.closest('#dhx-bell-btn')) return;
    panel.classList.remove('on');
  });
}

function init(){
  injectCSS();
  mount();
  updateDateGreeting();
  loadReadiness();
  loadGarminSync();
  setupUpgradeBtn();
  setupBell();
  loadNotifCount();
}

if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

})();
