/**
 * lx-upgrade.js — Modal de comparación de planes + checkout, compartido.
 * dashboard.html tiene su propia copia inline (con el resto de su JS ya
 * ligado); este módulo replica exactamente el mismo modal para el resto de
 * las páginas — expone window.openUpgrade/closeUpgrade/doCheckout, que es
 * justo lo que dash-header.js ya intenta llamar desde el botón "Actualizar
 * Plan" (si no las encuentra, hoy cae a un redirect a landing.html#planes).
 */
(function(){
'use strict';

if(window.openUpgrade) return; // dashboard.html ya trae su propia versión

function ensureToast(){
  var t = document.getElementById('ed-toast');
  if(t) return t;
  t = document.createElement('div');
  t.id = 'ed-toast';
  t.className = 'ed-toast';
  document.body.appendChild(t);
  if(!document.getElementById('lx-upgrade-toast-css')){
    var s = document.createElement('style');
    s.id = 'lx-upgrade-toast-css';
    s.textContent = [
      '.ed-toast{position:fixed;bottom:1.5rem;left:50%;transform:translateX(-50%) translateY(20px);background:#08121E;border:1px solid rgba(8,116,174,.3);color:#F0F9FF;padding:.7rem 1.3rem;border-radius:10px;font-size:.85rem;z-index:9999;opacity:0;pointer-events:none;transition:all .3s}',
      '.ed-toast.show{opacity:1;transform:translateX(-50%) translateY(0)}',
      '.ed-toast-err{border-color:rgba(239,68,68,.4);color:#FCA5A5}',
    ].join('\n');
    document.head.appendChild(s);
  }
  return t;
}

function showToast(msg, type){
  var t = ensureToast();
  t.textContent = msg;
  t.className = 'ed-toast show' + (type === 'err' ? ' ed-toast-err' : '');
  setTimeout(function(){ t.className = 'ed-toast'; }, 4000);
}

function injectCSS(){
  if(document.getElementById('lx-upgrade-css')) return;
  var s = document.createElement('style');
  s.id = 'lx-upgrade-css';
  s.textContent = [
    '#upgrade-overlay .up-plan-card{transition:transform .2s ease,box-shadow .2s ease,opacity .2s ease}',
    '#upgrade-overlay .up-plan-card:hover{transform:translateY(-6px);box-shadow:0 20px 50px rgba(0,0,0,.45),0 0 0 1px var(--pc,#0EA5E9),0 0 40px -12px var(--pc,#0EA5E9);z-index:2}',
    '#upgrade-overlay .up-plans-grid:hover .up-plan-card:not(:hover){opacity:.6;transform:scale(.98)}',
    '#upgrade-overlay .up-plan-card ul{color:#7FB3CC}',
    '#upgrade-overlay .up-feat-on{color:#10B981}',
    '#upgrade-overlay .up-feat-off{color:#ef4444}',
  ].join('\n');
  document.head.appendChild(s);
}

function buildHTML(){
  return ''
    + '<div style="background:#08121E;border:1px solid rgba(8,116,174,.22);border-radius:20px;width:100%;max-width:920px;max-height:90vh;overflow-y:auto;position:relative">'
    +   '<button onclick="closeUpgrade()" style="position:absolute;top:1rem;right:1rem;background:none;border:none;color:#3D6880;cursor:pointer;font-size:1.4rem;line-height:1">&times;</button>'
    +   '<div style="padding:2rem 2rem 1rem;text-align:center">'
    +     '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:1.8rem;font-weight:900;letter-spacing:.04em;text-transform:uppercase;margin-bottom:.3rem">'
    +       'Desbloquea tu <span style="background:linear-gradient(125deg,#A855F7,#6366F1);-webkit-background-clip:text;-webkit-text-fill-color:transparent">Potencial</span>'
    +     '</div>'
    +     '<p style="color:#7FB3CC;font-size:.9rem">Elige el plan que mejor se adapta a tu entrenamiento</p>'
    +   '</div>'
    +   '<div class="up-plans-grid" style="display:grid;grid-template-columns:repeat(4,minmax(180px,1fr));gap:.75rem;padding:1rem 1.25rem 1.5rem">'

    +     '<div id="plan-basico" class="up-plan-card" style="--pc:#0EA5E9;border:1px solid rgba(8,116,174,.2);border-radius:14px;padding:1.25rem;background:rgba(14,165,233,.03);display:flex;flex-direction:column">'
    +       '<div style="font-family:\'Oswald\',sans-serif;font-size:.6rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:#0EA5E9;margin-bottom:.6rem">Básico</div>'
    +       '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:2rem;font-weight:900;line-height:1;margin-bottom:.2rem">Atleta</div>'
    +       '<div style="font-size:.7rem;color:#7FB3CC;margin-bottom:.8rem">sin tarjeta de crédito</div>'
    +       '<ul style="list-style:none;font-size:.78rem;line-height:1.8;margin-bottom:1.2rem;flex:1">'
    +         '<li><span class="up-feat-on">✓</span> Dashboard + histórico completo</li>'
    +         '<li><span class="up-feat-on">✓</span> Sync Garmin Connect automático</li>'
    +         '<li><span class="up-feat-on">✓</span> CTL / ATL / TSB</li>'
    +         '<li><span class="up-feat-off">✗</span> Plan, Nutrición, Analytics</li>'
    +         '<li><span class="up-feat-off">✗</span> Blood Labs + AI Coach</li>'
    +       '</ul>'
    +       '<div id="current-plan-badge" style="display:none;text-align:center;font-family:\'Oswald\',sans-serif;font-size:.65rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#0EA5E9;padding:.5rem;border:1px solid rgba(14,165,233,.3);border-radius:8px">Plan actual</div>'
    +     '</div>'

    +     '<div class="up-plan-card" style="--pc:#A855F7;border:1px solid rgba(168,85,247,.3);border-radius:14px;padding:1.25rem;background:rgba(168,85,247,.05);position:relative;display:flex;flex-direction:column">'
    +       '<div style="position:absolute;top:-10px;left:50%;transform:translateX(-50%);background:linear-gradient(135deg,#A855F7,#6366F1);color:#fff;font-family:\'Oswald\',sans-serif;font-size:.55rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;padding:.2rem .7rem;border-radius:20px">Más popular</div>'
    +       '<div style="font-family:\'Oswald\',sans-serif;font-size:.6rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:#C084FC;margin-bottom:.6rem">Agegroup</div>'
    +       '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:2rem;font-weight:900;line-height:1;margin-bottom:.2rem">$19<span style="font-size:1rem;color:#7FB3CC">/mes</span></div>'
    +       '<div style="font-size:.7rem;color:#7FB3CC;margin-bottom:.8rem">~$0.63/día</div>'
    +       '<ul style="list-style:none;font-size:.78rem;line-height:1.8;margin-bottom:1.2rem;flex:1">'
    +         '<li><span class="up-feat-on">✓</span> Todo del plan Atleta</li>'
    +         '<li><span class="up-feat-on">✓</span> Plan de entrenamiento + Nutrición</li>'
    +         '<li><span class="up-feat-on">✓</span> Analytics avanzado + Predictor de carrera</li>'
    +         '<li><span class="up-feat-on">✓</span> Recuperación (HRV) + Estado mental</li>'
    +         '<li><span class="up-feat-off">✗</span> Blood Labs + AI Coach (Elite)</li>'
    +       '</ul>'
    +       '<button onclick="doCheckout(\'agegroup\')" style="width:100%;background:linear-gradient(135deg,#A855F7,#6366F1);color:#fff;border:none;border-radius:10px;padding:.7rem;font-family:\'Barlow Condensed\',sans-serif;font-size:.9rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;cursor:pointer">Elegir Agegroup →</button>'
    +     '</div>'

    +     '<div class="up-plan-card" style="--pc:#F0A500;border:1px solid rgba(240,165,0,.25);border-radius:14px;padding:1.25rem;background:rgba(240,165,0,.04);display:flex;flex-direction:column">'
    +       '<div style="font-family:\'Oswald\',sans-serif;font-size:.6rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:#F0A500;margin-bottom:.6rem">Élite</div>'
    +       '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:2rem;font-weight:900;line-height:1;margin-bottom:.2rem">$39<span style="font-size:1rem;color:#7FB3CC">/mes</span></div>'
    +       '<div style="font-size:.7rem;color:#7FB3CC;margin-bottom:.8rem">~$1.30/día</div>'
    +       '<ul style="list-style:none;font-size:.78rem;line-height:1.8;margin-bottom:1.2rem;flex:1">'
    +         '<li><span class="up-feat-on">✓</span> Todo del plan Agegroup</li>'
    +         '<li><span class="up-feat-on">✓</span> Blood Labs + biomarcadores</li>'
    +         '<li><span class="up-feat-on">✓</span> AI Coach — forecast CTL + riesgo de lesión</li>'
    +         '<li><span class="up-feat-on">✓</span> Plan adaptativo automático</li>'
    +         '<li><span class="up-feat-on">✓</span> Indoor Workout Builder (Zwift-style)</li>'
    +       '</ul>'
    +       '<button onclick="doCheckout(\'elite\')" style="width:100%;background:linear-gradient(135deg,#F0A500,#D97706);color:#000;border:none;border-radius:10px;padding:.7rem;font-family:\'Barlow Condensed\',sans-serif;font-size:.9rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;cursor:pointer">Elegir Élite →</button>'
    +     '</div>'

    +     '<div class="up-plan-card" style="--pc:#FF6535;border:1px solid rgba(255,101,53,.25);border-radius:14px;padding:1.25rem;background:rgba(255,101,53,.04);display:flex;flex-direction:column">'
    +       '<div style="font-family:\'Oswald\',sans-serif;font-size:.6rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:#FF6535;margin-bottom:.6rem">Coach</div>'
    +       '<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:2rem;font-weight:900;line-height:1;margin-bottom:.2rem">$49<span style="font-size:1rem;color:#7FB3CC">/mes</span></div>'
    +       '<div style="font-size:.7rem;color:#7FB3CC;margin-bottom:.8rem">gestiona 50+ atletas</div>'
    +       '<ul style="list-style:none;font-size:.78rem;line-height:1.8;margin-bottom:1.2rem;flex:1">'
    +         '<li><span class="up-feat-on">✓</span> Squad Overview — riesgo de tus atletas</li>'
    +         '<li><span class="up-feat-on">✓</span> Prescripción de entrenamientos</li>'
    +         '<li><span class="up-feat-on">✓</span> Mensajería con tus atletas</li>'
    +         '<li><span class="up-feat-on">✓</span> Gestión de 50+ atletas</li>'
    +         '<li><span class="up-feat-on">✓</span> Acceso completo a funciones Elite incluido</li>'
    +       '</ul>'
    +       '<button onclick="doCheckout(\'coach\')" style="width:100%;background:linear-gradient(135deg,#FF6535,#E8490A);color:#fff;border:none;border-radius:10px;padding:.7rem;font-family:\'Barlow Condensed\',sans-serif;font-size:.9rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;cursor:pointer">Elegir Coach →</button>'
    +     '</div>'

    +   '</div>'
    +   '<div style="text-align:center;padding:.5rem 1.5rem 1.5rem;font-size:.72rem;color:#3D6880">'
    +     '🔒 Pago seguro via Stripe · Cancela cuando quieras · Sin permanencia'
    +   '</div>'
    + '</div>';
}

function ensureOverlay(){
  var ov = document.getElementById('upgrade-overlay');
  if(ov) return ov;
  injectCSS();
  ov = document.createElement('div');
  ov.id = 'upgrade-overlay';
  ov.style.cssText = 'display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);backdrop-filter:blur(4px);z-index:9000;align-items:center;justify-content:center;padding:1rem';
  ov.innerHTML = buildHTML();
  document.body.appendChild(ov);
  ov.addEventListener('click', function(e){ if(e.target === ov) window.closeUpgrade(); });
  return ov;
}

window.openUpgrade = function(){
  var ov = ensureOverlay();
  ov.style.display = 'flex';
  var s = window.KL && KL.getSession();
  var badge = document.getElementById('current-plan-badge');
  if(badge) badge.style.display = (s && s.plan_nivel === 'basico') ? 'block' : 'none';
};

window.closeUpgrade = function(){
  var ov = document.getElementById('upgrade-overlay');
  if(ov) ov.style.display = 'none';
};

window.doCheckout = async function(plan){
  var s = window.KL && KL.getSession();
  if(!s){ window.location.href = 'login.html'; return; }
  try{
    var r = await fetch(KL.API_BASE + '/stripe/checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + s.token },
      body: JSON.stringify({ plan: plan }),
    });
    var d = await r.json();
    if(!r.ok) throw new Error(d.detail || 'Error al iniciar pago');
    window.location.href = d.checkout_url;
  }catch(err){
    showToast(err.message, 'err');
  }
};

})();
