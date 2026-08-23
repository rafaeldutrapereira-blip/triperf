/**
 * lx-audit.js — Panel de auditoría de datos en vivo para LabX.
 * Muestra qué campos llegaron de la API y cuáles son null.
 * Uso: lxAudit.show(data, fields?)  donde fields es [{key,label,unit}]
 * Si no se pasa fields, muestra todos los keys del objeto data.
 * Incluir al final de cualquier página HTML:  <script src="lx-audit.js"></script>
 */
(function(){
'use strict';

var _tok = null;
function _getToken(){
  if(_tok) return _tok;
  _tok = localStorage.getItem('lx_co_token');
  if(!_tok){
    try{
      var s = JSON.parse(sessionStorage.getItem('kl_s') || localStorage.getItem('kl_s') || 'null');
      if(s && s.token) _tok = s.token;
    }catch(e){}
  }
  return _tok;
}

function _apiBase(){
  if (window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform()) {
    return 'https://labxperformanceapp.com/api';
  }
  return window.location.protocol === 'file:' ? 'http://localhost:8000/api' : window.location.origin + '/api';
}

/* ── CSS ──────────────────────────────────────────────────────────────────── */
function _injectCSS(){
  if(document.getElementById('_lxaudit-css')) return;
  var s = document.createElement('style');
  s.id  = '_lxaudit-css';
  s.textContent = [
    '#_audit-btn{position:fixed;bottom:1.2rem;right:1.2rem;z-index:8000;background:#0F172A;border:1px solid rgba(255,255,255,.12);color:#94A3B8;font-size:.68rem;font-family:Inter,sans-serif;padding:.35rem .7rem;border-radius:999px;cursor:pointer;display:flex;align-items:center;gap:.35rem;box-shadow:0 4px 20px rgba(0,0,0,.4);-webkit-appearance:none;appearance:none;outline:none}',
    '#_audit-btn:hover{border-color:rgba(14,165,233,.4);color:#7DD3FC}',
    '#_audit-panel{display:none;position:fixed;bottom:3.5rem;right:1.2rem;z-index:8001;background:#0F172A;border:1px solid rgba(255,255,255,.12);border-radius:12px;padding:1rem;min-width:320px;max-width:360px;box-shadow:0 8px 40px rgba(0,0,0,.6);flex-direction:column;gap:.6rem;max-height:75vh;overflow-y:auto}',
    '#_audit-panel.open{display:flex}',
    '._aud-hd{font-family:Oswald,sans-serif;font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;color:#64748B;margin-bottom:.2rem;display:flex;justify-content:space-between;align-items:center}',
    '._aud-close{background:none;border:none;color:#64748B;cursor:pointer;font-size:.9rem;padding:0;line-height:1}',
    '._aud-close:hover{color:#F9FAFB}',
    '._aud-table{width:100%;border-collapse:collapse}',
    '._aud-table td{padding:.3rem .45rem;font-size:.71rem;border-bottom:1px solid rgba(255,255,255,.04)}',
    '._aud-table tr:last-child td{border-bottom:none}',
    '._aud-lbl{color:#D1D5DB}',
    '._aud-val{text-align:right;font-weight:600}',
    '._aud-icon{text-align:center;width:1.2rem}',
    '._aud-note{font-size:.67rem;color:#94A3B8;line-height:1.55;padding:.5rem .65rem;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);border-radius:7px}',
    '._aud-sync{display:block;width:100%;margin-top:.5rem;padding:.42rem;background:rgba(14,165,233,.12);border:1px solid rgba(14,165,233,.28);color:#7DD3FC;border-radius:6px;font-size:.71rem;cursor:pointer;font-family:Inter,sans-serif;-webkit-appearance:none;appearance:none}',
    '._aud-sync:hover:not(:disabled){background:rgba(14,165,233,.22)}',
    '._aud-sync:disabled{opacity:.6;cursor:not-allowed}',
    '._aud-foot{font-size:.63rem;color:#475569;margin-top:.3rem}',
  ].join('');
  document.head.appendChild(s);
}

/* ── Botón flotante ───────────────────────────────────────────────────────── */
function _ensureBtn(){
  var btn = document.getElementById('_audit-btn');
  if(!btn){
    btn = document.createElement('button');
    btn.id = '_audit-btn';
    btn.type = 'button';
    btn.onclick = function(){
      var p = document.getElementById('_audit-panel');
      if(p) p.classList.toggle('open');
    };
    document.body.appendChild(btn);
  }
  return btn;
}

function _ensurePanel(){
  var panel = document.getElementById('_audit-panel');
  if(!panel){
    panel = document.createElement('div');
    panel.id = '_audit-panel';
    document.body.appendChild(panel);
  }
  return panel;
}

/* ── Sincronizar Garmin ───────────────────────────────────────────────────── */
function _doSync(btn){
  var tok = _getToken();
  if(!tok){ btn.textContent = 'Sin sesión — inicia sesión primero'; return; }
  btn.disabled = true;
  fetch(_apiBase() + '/athlete/garmin/sync?force=true', {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + tok }
  })
  .then(function(r){ return r.json(); })
  .then(function(res){
    if(res.ok){
      var secs = 35;
      btn.textContent = '✓ Sync iniciado — recargando en ' + secs + 's...';
      var iv = setInterval(function(){
        secs--;
        btn.textContent = '✓ Sync en progreso — recargando en ' + secs + 's...';
        if(secs <= 0){ clearInterval(iv); location.reload(); }
      }, 1000);
    } else {
      btn.textContent = 'Error: ' + (res.detail || res.message || 'ver consola');
      btn.disabled = false;
    }
  })
  .catch(function(e){
    btn.textContent = 'Error de red';
    btn.disabled = false;
  });
}

/* ── Renderizar panel ─────────────────────────────────────────────────────── */
function show(data, fields, sourceLabel){
  if(!data){ _showSyncOnly(sourceLabel); return; }

  _injectCSS();
  var btn   = _ensureBtn();
  var panel = _ensurePanel();

  // Si no se pasan fields explícitos, generar desde todas las keys del objeto
  var FIELDS = fields || Object.keys(data)
    .filter(function(k){ return !Array.isArray(data[k]) && typeof data[k] !== 'object'; })
    .map(function(k){ return {key:k, label:k, unit:''}; });

  var ok = 0, miss = 0;
  var rows = FIELDS.map(function(f){
    var val  = data[f.key];
    var live = val != null;
    if(live) ok++; else miss++;
    var color = live ? '#10B981' : '#EF4444';
    var disp  = live ? val + (f.unit ? ' '+f.unit : '') : '—';
    return '<tr>'
      + '<td class="_aud-lbl">' + (f.label||f.key) + '</td>'
      + '<td class="_aud-val" style="color:'+color+'">' + disp + '</td>'
      + '<td class="_aud-icon" style="color:'+color+'">' + (live?'✓':'✗') + '</td>'
      + '</tr>';
  }).join('');

  var pct = FIELDS.length > 0 ? Math.round(ok / FIELDS.length * 100) : 0;
  var dotColor = pct === 100 ? '#10B981' : pct >= 70 ? '#F0A500' : '#EF4444';

  // Badge
  btn.innerHTML = '<span style="width:7px;height:7px;border-radius:50%;background:'+dotColor+';flex-shrink:0;display:inline-block"></span> API '+ok+'/'+FIELDS.length;

  // Nota + botón sync cuando hay campos nulos
  var noteHtml = '';
  if(miss > 0){
    noteHtml = '<div class="_aud-note">'
      + '<strong style="color:#F9FAFB">'+miss+' campo'+(miss>1?'s':'s')+' sin datos</strong> — '
      + 'posibles causas: (1) tu Garmin no reporta esa métrica '
      + '(HRV, Body Battery, Training Readiness requieren Fenix / Forerunner 955+), '
      + 'o (2) el sync no ha corrido hoy.'
      + '<button id="_sync-now-btn" class="_aud-sync">⟳ Sincronizar Garmin ahora</button>'
      + '</div>';
  }

  var src   = sourceLabel || (data.source ? data.source + ' · ' + (data.generated||'') : '');
  panel.innerHTML = '<div class="_aud-hd">Datos en vivo<button class="_aud-close" onclick="document.getElementById(\'_audit-panel\').classList.remove(\'open\')">✕</button></div>'
    + '<table class="_aud-table">' + rows + '</table>'
    + (src ? '<div class="_aud-foot">'+src+'</div>' : '')
    + noteHtml;

  var syncBtn = document.getElementById('_sync-now-btn');
  if(syncBtn) syncBtn.addEventListener('click', function(){ _doSync(this); });
}

/* ── Modo sin datos: solo botón sync ─────────────────────────────────────── */
function _showSyncOnly(sourceLabel){
  _injectCSS();
  var btn   = _ensureBtn();
  var panel = _ensurePanel();

  btn.innerHTML = '<span style="width:7px;height:7px;border-radius:50%;background:#64748B;flex-shrink:0;display:inline-block"></span> Sin datos API';

  panel.innerHTML = '<div class="_aud-hd">Datos en vivo<button class="_aud-close" onclick="document.getElementById(\'_audit-panel\').classList.remove(\'open\')">✕</button></div>'
    + '<div class="_aud-note">No hay datos de API cargados en esta página aún.'
    + '<button id="_sync-now-btn" class="_aud-sync">⟳ Sincronizar Garmin ahora</button>'
    + '</div>';

  var syncBtn = document.getElementById('_sync-now-btn');
  if(syncBtn) syncBtn.addEventListener('click', function(){ _doSync(this); });
}

/* ── API pública ──────────────────────────────────────────────────────────── */
window.lxAudit = { show: show };

})();
