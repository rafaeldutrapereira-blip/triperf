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

function init(){
  injectCSS();
  mount();
  updateDateGreeting();
  loadReadiness();
  loadGarminSync();
  setupUpgradeBtn();
}

if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

})();
