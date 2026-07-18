/**
 * footer.js — Pie de página estándar de LabX, compartido por todas las
 * páginas de la plataforma (antes cada página tenía su propio footer
 * ad-hoc: "Sprint 15", "Sprint 17", módulo por módulo — inconsistente).
 * Mismo patrón que dash-header.js: se incluye con un solo
 * <script src="footer.js"></script>, sin duplicar HTML/CSS en cada página.
 */
(function(){
'use strict';

var MONTHS = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];

function injectCSS(){
  if(document.getElementById('lx-foot-css')) return;
  var s = document.createElement('style');
  s.id = 'lx-foot-css';
  s.textContent = [
    '.lx-foot{background:linear-gradient(180deg,#060E1C 0%,var(--bg,#04080F) 100%);border-top:1px solid rgba(8,145,178,.1);padding:1.5rem 0;margin-top:1.5rem}',
    '.lx-foot-c{max-width:1280px;margin:0 auto;padding:0 clamp(1.25rem,4vw,2.5rem)}',
    '.lx-foot-in{display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap}',
    '.lx-foot-brand{font-family:"Barlow Condensed",sans-serif;font-size:1.1rem;font-weight:900;display:flex;align-items:center;gap:.3rem;color:var(--text,#F0F9FF)}',
    '.lx-foot-brand span{color:var(--orange,#FF6535)}',
    '.lx-foot-info{font-size:.74rem;color:var(--dim,#3D6880)}',
    '.lx-foot-kona{font-size:.74rem;color:var(--orange,#FF6535);font-weight:600}',
  ].join('\n');
  document.head.appendChild(s);
}

function buildHTML(dateStr){
  return ''
    + '<footer class="lx-foot">'
    +   '<div class="lx-foot-c">'
    +     '<div class="lx-foot-in">'
    +       '<div class="lx-foot-brand">'
    +         '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="var(--orange,#FF6535)" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>'
    +         'Lab<span>X</span>'
    +       '</div>'
    +       '<p class="lx-foot-info">Dashboard v1.0 &middot; ' + dateStr + ' &middot; Datos Garmin Connect</p>'
    +       '<p class="lx-foot-kona">Plataforma privada de rendimiento atlético</p>'
    +     '</div>'
    +   '</div>'
    + '</footer>';
}

function todayLabel(){
  var n = new Date(), d = n.getDate(), mo = n.getMonth(), y = n.getFullYear();
  return d + ' ' + MONTHS[mo] + ' ' + y;
}

function mount(){
  if(document.querySelector('.lx-foot')) return;
  // Reemplaza cualquier <footer> ad-hoc que la página ya tuviera (cada
  // módulo traía el suyo, con texto distinto) — se deja solo el estándar.
  document.querySelectorAll('footer').forEach(function(f){ f.remove(); });
  var wrap = document.createElement('div');
  wrap.innerHTML = buildHTML(todayLabel());
  document.body.appendChild(wrap.firstElementChild);
}

function init(){
  injectCSS();
  mount();
}

if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

})();
