
/* ── Defaults del atleta — fuente única de verdad ── */
var _PROFILE_DEFAULTS = {name:'Rafael',ftp:235,weight:62,height:175,vo2max:54.2,fcmax:180,css:'1:48',runPace:'4:52',goal:'5:00:00'};

document.getElementById('yr').textContent = new Date().getFullYear();

// Season bars (PMC weeks from KL_DATA if available, else demo)
var pmc = (window.KL_DATA && window.KL_DATA.pmc) ? window.KL_DATA.pmc : [
  {l:'S1',tss:320},{l:'S2',tss:450},{l:'S3',tss:390},{l:'S4',tss:510},
  {l:'S5',tss:480},{l:'S6',tss:540},{l:'S7',tss:320},{l:'S8',tss:590},
  {l:'S9',tss:610},{l:'S10',tss:570},{l:'S11',tss:540},{l:'S12',tss:280},
  {l:'HOY',tss:378}
];
var maxT = Math.max.apply(null, pmc.map(function(p){return p.tss||0}));
var barsEl = document.getElementById('season-bars');
var lblsEl = document.getElementById('season-labels');
pmc.forEach(function(p,i){
  var h = maxT > 0 ? Math.round((p.tss||0)/maxT*100) : 0;
  var bar = document.createElement('div');
  bar.className = 's-bar' + (p.l==='HOY'?' current':i===pmc.indexOf(pmc.reduce(function(a,b){return (a.tss||0)>(b.tss||0)?a:b}))?' peak':'');
  bar.style.height = h + '%';
  bar.title = p.l + ': ' + (p.tss||0) + ' TSS';
  barsEl.appendChild(bar);
  var lbl = document.createElement('div');
  lbl.className = 's-lbl';
  lbl.textContent = p.l;
  lblsEl.appendChild(lbl);
});

// Scroll reveal
var io = new IntersectionObserver(function(entries){
  entries.forEach(function(e){
    if(e.isIntersecting){
      e.target.classList.add('vis');
      e.target.querySelectorAll('.zone-bar-f[data-w],.load-bar-f[data-w]').forEach(function(b){
        setTimeout(function(){b.style.width=b.dataset.w+'%'},250);
      });
    }
  });
},{threshold:.12});
document.querySelectorAll('.sr').forEach(function(el){io.observe(el)});

// Sync kl-avatar-big with session initial
var s = KL && KL.getSession ? KL.getSession() : null;
if(s){
  var big = document.getElementById('kl-avatar-big');
  if(big) big.textContent = s.initials || 'R';
}

/* ════════════════════════ EDIT PROFILE DRAWER ════════════════════════════ */
function openProfileDrawer(){
  var d = JSON.parse(localStorage.getItem('kl_athlete_data') || '{}');
  var D = _PROFILE_DEFAULTS;
  document.getElementById('ed-name').value    = d.name    || D.name;
  document.getElementById('ed-weight').value  = d.weight  || D.weight;
  document.getElementById('ed-height').value  = d.height  || D.height;
  document.getElementById('ed-ftp').value     = d.ftp     || D.ftp;
  document.getElementById('ed-vo2max').value  = d.vo2max  || D.vo2max;
  document.getElementById('ed-fcmax').value   = d.fcmax   || D.fcmax;
  document.getElementById('ed-css').value     = d.css     || D.css;
  document.getElementById('ed-runpace').value = d.runPace || D.runPace;
  document.getElementById('ed-goal').value    = d.goal    || D.goal;
  pfUpdateCalc();
  document.getElementById('ed-overlay').classList.add('open');
  document.getElementById('ed-drawer').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeProfileDrawer(){
  document.getElementById('ed-overlay').classList.remove('open');
  document.getElementById('ed-drawer').classList.remove('open');
  document.body.style.overflow = '';
}

function pfUpdateCalc(){
  var ftp = parseFloat(document.getElementById('ed-ftp').value)    || 0;
  var wt  = parseFloat(document.getElementById('ed-weight').value) || 0;
  var ht  = parseFloat(document.getElementById('ed-height').value) || 0;
  var fcm = parseFloat(document.getElementById('ed-fcmax').value)  || 0;
  var vo2 = parseFloat(document.getElementById('ed-vo2max').value) || 0;
  var css = document.getElementById('ed-css').value.trim();
  var run = document.getElementById('ed-runpace').value.trim();

  var wkg = (ftp > 0 && wt > 0) ? (ftp/wt).toFixed(2) : null;

  /* ── Drawer inline calcs ── */
  var wkgEl  = document.getElementById('ed-wkg-calc');
  var imcEl  = document.getElementById('ed-imc-calc');
  var thrEl  = document.getElementById('ed-fcthr-calc');

  if(wkgEl) wkgEl.textContent = wkg ? wkg+' W/kg' : '– W/kg';

  if(imcEl){
    if(wt > 0 && ht > 0){
      var imc = (wt / Math.pow(ht/100, 2)).toFixed(1);
      imcEl.textContent = imc + ' kg/m²';
      imcEl.style.color = imc < 18.5 ? 'var(--cyan)' : imc < 25 ? 'var(--green)' : imc < 30 ? 'var(--gold)' : 'var(--red)';
    } else { imcEl.textContent = '– kg/m²'; }
  }

  if(thrEl) thrEl.textContent = (fcm > 0) ? Math.round(fcm * 0.78) + ' bpm' : '– bpm';

  /* ── Live preview → KPI Performance Panel ── */
  var g = function(id){ return document.getElementById(id); };

  /* Power pillars */
  if(ftp > 0){
    var ftpEl=g('kpi-ftp'); if(ftpEl) ftpEl.textContent=ftp;
    var bkEl=g('kpi-bike'); if(bkEl) bkEl.textContent=ftp;
    var fL=kpiLevel('ftp',ftp);
    var fBar=g('kpi-ftp-bar'); if(fBar) fBar.style.width=fL.pct+'%';
    var fLvl=g('kpi-ftp-level'); if(fLvl){fLvl.textContent=fL.label;fLvl.style.color=fL.c;}
  }
  if(vo2 > 0){
    var vo2El=g('kpi-vo2max'); if(vo2El) vo2El.textContent=vo2;
    var vL=kpiLevel('vo2max',vo2);
    var vBar=g('kpi-vo2-bar'); if(vBar) vBar.style.width=vL.pct+'%';
    var vLvl=g('kpi-vo2-level'); if(vLvl){vLvl.textContent=vL.label;vLvl.style.color=vL.c;}
  }
  if(wkg){
    var wkgN2=parseFloat(wkg);
    var wkgEl=g('kpi-wkg'); if(wkgEl) wkgEl.textContent=wkg;
    var wL=kpiLevel('wkg',wkgN2);
    var wBar=g('kpi-wkg-bar'); if(wBar) wBar.style.width=wL.pct+'%';
    var wLvl=g('kpi-wkg-level'); if(wLvl){wLvl.textContent=wL.label;wLvl.style.color=wL.c;}
  }

  /* Bio strip */
  var bwEl2=g('kpi-weight'),bwU2=g('kpi-weight-u');
  if(wt > 0){ if(bwEl2){bwEl2.textContent=wt;bwEl2.style.color='var(--text)';} if(bwU2) bwU2.style.display=''; }
  else { if(bwEl2){bwEl2.textContent='—';bwEl2.style.color='var(--dim)';} if(bwU2) bwU2.style.display='none'; }
  var bhEl2=g('kpi-height'),bhU2=g('kpi-height-u');
  if(ht > 0){ if(bhEl2){bhEl2.textContent=ht;bhEl2.style.color='var(--text)';} if(bhU2) bhU2.style.display=''; }
  else { if(bhEl2){bhEl2.textContent='—';bhEl2.style.color='var(--dim)';} if(bhU2) bhU2.style.display='none'; }
  if(wt > 0 && ht > 0){
    var imc2=(wt/Math.pow(ht/100,2)).toFixed(1);
    var imcEl2=g('kpi-imc-val'); var imcLbl2=g('kpi-imc-lbl');
    var imcC2=imc2<18.5?'var(--cyan)':imc2<25?'var(--green)':imc2<30?'var(--gold)':'var(--red)';
    var imcT2=imc2<18.5?'Bajo peso':imc2<25?'Normal':imc2<30?'Sobrepeso':'Obesidad';
    if(imcEl2){imcEl2.textContent=imc2;imcEl2.style.color=imcC2;}
    if(imcLbl2){imcLbl2.textContent=imcT2;imcLbl2.style.color=imcC2;}
  }

  /* Discipline cards */
  if(css){ var cEl2=g('kpi-css'); if(cEl2) cEl2.textContent=css; }
  if(run){ var rEl2=g('kpi-run'); if(rEl2) rEl2.textContent=run; }
  if(fcm > 0){
    var fmEl2=g('kpi-fcmax'); if(fmEl2) fmEl2.textContent=fcm;
    var ftEl2=g('kpi-fcthr'); if(ftEl2) ftEl2.textContent=Math.round(fcm*0.78);
  }

  /* ── Live preview → Hero stats ── */
  if(ftp > 0){ var ef=g('pf-ftp');    if(ef) ef.textContent = ftp; }
  if(vo2 > 0){ var ev=g('pf-vo2max'); if(ev) ev.textContent = vo2; }
  if(fcm > 0){ var ec=g('pf-fcmax');  if(ec) ec.textContent = fcm; }
  if(wkg)    { var ew=g('pf-wkg');    if(ew) ew.textContent = wkg; }

  /* ── Live preview → Page header chips ── */
  if(ftp > 0){ var phf=g('ph-ftp');   if(phf) phf.textContent = ftp; }
  if(fcm > 0){ var phm=g('ph-fcmax'); if(phm) phm.textContent = fcm; }
  if(wkg)    { var phw=g('ph-wkg');   if(phw) phw.textContent = wkg; }
}

/* Re-calc on any relevant input change */
document.addEventListener('input', function(e){
  if(e.target && ['ed-ftp','ed-weight','ed-height','ed-fcmax','ed-vo2max','ed-css','ed-runpace'].indexOf(e.target.id) !== -1) pfUpdateCalc();
});

/* Alias kept for compatibility */
function pfUpdateWkg(){ pfUpdateCalc(); }

function saveProfileData(){
  var d = {
    name:    document.getElementById('ed-name').value.trim()         || 'Rafael',
    weight:  parseFloat(document.getElementById('ed-weight').value)  || _PROFILE_DEFAULTS.weight,
    height:  parseFloat(document.getElementById('ed-height').value)  || _PROFILE_DEFAULTS.height,
    ftp:     parseInt(document.getElementById('ed-ftp').value)       || 235,
    vo2max:  parseFloat(document.getElementById('ed-vo2max').value)  || 54.2,
    fcmax:   parseInt(document.getElementById('ed-fcmax').value)     || 180,
    css:     document.getElementById('ed-css').value.trim()          || null,
    runPace: document.getElementById('ed-runpace').value.trim()      || null,
    goal:    document.getElementById('ed-goal').value.trim()         || null
  };
  /* Preserve CTL / readiness set via inline edit or Garmin sync */
  var prev = JSON.parse(localStorage.getItem('kl_athlete_data') || '{}');
  if(prev.ctl)       d.ctl       = prev.ctl;
  if(prev.readiness) d.readiness = prev.readiness;
  /* Preserve weight/height from existing data if user left inputs blank */
  if(!d.weight  && prev.weight)  d.weight  = prev.weight;
  if(!d.height  && prev.height)  d.height  = prev.height;
  if(!d.css     && prev.css)     d.css     = prev.css;
  if(!d.runPace && prev.runPace) d.runPace = prev.runPace;
  if(!d.goal    && prev.goal)    d.goal    = prev.goal;

  var _json = JSON.stringify(d);
  localStorage.setItem('kl_athlete_data', _json);
  try{ sessionStorage.setItem('kl_athlete_data', _json); }catch(e){}
  applyProfileData(d);
  pfShowToast('✓ Perfil guardado — sincronizado con todos los módulos');
  setTimeout(closeProfileDrawer, 1000);
}

/* ── KPI level calculator ── */
function kpiLevel(type, val){
  var tiers = {
    wkg:[
      {max:2.0, label:'INICIACIÓN', c:'var(--dim)'},
      {max:2.5, label:'RECREATIVO', c:'var(--muted)'},
      {max:3.0, label:'ENTRENADO',  c:'var(--cyan)'},
      {max:3.5, label:'AVANZADO',   c:'var(--green)'},
      {max:4.0, label:'ÉLITE',      c:'var(--gold)'},
      {max:999, label:'PRO',        c:'var(--orange)'}
    ],
    vo2max:[
      {max:40,  label:'BÁSICO',        c:'var(--dim)'},
      {max:46,  label:'MODERADO',      c:'var(--muted)'},
      {max:52,  label:'BUENO',         c:'var(--cyan)'},
      {max:58,  label:'AVANZADO',      c:'var(--green)'},
      {max:65,  label:'ÉLITE',         c:'var(--gold)'},
      {max:999, label:'CLASE MUNDIAL', c:'var(--orange)'}
    ],
    ftp:[
      {max:150, label:'INICIACIÓN', c:'var(--dim)'},
      {max:200, label:'RECREATIVO', c:'var(--muted)'},
      {max:260, label:'ENTRENADO',  c:'var(--cyan)'},
      {max:320, label:'AVANZADO',   c:'var(--green)'},
      {max:380, label:'ÉLITE',      c:'var(--gold)'},
      {max:999, label:'PRO',        c:'var(--orange)'}
    ]
  };
  var maxRef = {wkg:5, vo2max:70, ftp:450};
  var list = tiers[type] || tiers.ftp;
  var ref  = maxRef[type] || 450;
  for(var i=0;i<list.length;i++){
    if(val < list[i].max) return {label:list[i].label, c:list[i].c, pct:Math.min((val/ref)*100,100)};
  }
  return {label:'PRO', c:'var(--orange)', pct:100};
}

function applyProfileData(d){
  var ftp    = parseFloat(d.ftp)    || 235;
  var weight = parseFloat(d.weight) || 62;
  var height = parseFloat(d.height) || 175;
  var wkg    = (ftp / weight).toFixed(2);
  var wkgN   = parseFloat(wkg);

  var fcmax  = parseFloat(d.fcmax)  || 180;
  var vo2max = parseFloat(d.vo2max) || 54.2;
  var name   = d.name || 'Rafael';

  /* ── Hero stats ── */
  var ef = document.getElementById('pf-ftp');         if(ef)  ef.textContent = ftp;
  var ev = document.getElementById('pf-vo2max');      if(ev)  ev.textContent = vo2max;
  var ec = document.getElementById('pf-fcmax');       if(ec)  ec.textContent = fcmax;
  var ew = document.getElementById('pf-wkg');         if(ew)  ew.textContent = wkg;
  var ectl = document.getElementById('pf-ctl');       if(ectl && d.ctl)      ectl.textContent = d.ctl;
  var erd  = document.getElementById('pf-readiness'); if(erd && d.readiness) erd.textContent = d.readiness;

  /* ── Hero name ── */
  var en = document.getElementById('kl-fullname');
  if(en){ var pts=name.trim().split(' '); en.innerHTML=pts[0]+' <em>'+(pts.slice(1).join(' ')||'')+'</em>'; }

  /* ── Page header chips ── */
  var phFtp  = document.getElementById('ph-ftp');  if(phFtp)  phFtp.textContent  = ftp;
  var phFcm  = document.getElementById('ph-fcmax');if(phFcm)  phFcm.textContent  = fcmax;
  var phCtl  = document.getElementById('ph-ctl');  if(phCtl && d.ctl) phCtl.textContent = d.ctl;
  var phWkg  = document.getElementById('ph-wkg');  if(phWkg)  phWkg.textContent  = wkg;

  /* ── KPI Performance Panel ── */
  var g = function(id){ return document.getElementById(id); };

  /* Power pillars */
  var ftpEl=g('kpi-ftp'); if(ftpEl) ftpEl.textContent = ftp;
  var fBar=g('kpi-ftp-bar'); var fLvl=g('kpi-ftp-level');
  var fL = kpiLevel('ftp', ftp);
  if(fBar) setTimeout(function(){fBar.style.width=fL.pct+'%';},120);
  if(fLvl){fLvl.textContent=fL.label; fLvl.style.color=fL.c;}
  var bkEl=g('kpi-bike'); if(bkEl) bkEl.textContent = ftp;

  var vo2El=g('kpi-vo2max'); if(vo2El) vo2El.textContent = vo2max;
  var vBar=g('kpi-vo2-bar'); var vLvl=g('kpi-vo2-level');
  var vL = kpiLevel('vo2max', vo2max);
  if(vBar) setTimeout(function(){vBar.style.width=vL.pct+'%';},200);
  if(vLvl){vLvl.textContent=vL.label; vLvl.style.color=vL.c;}
  var wkgEl=g('kpi-wkg'); if(wkgEl) wkgEl.textContent = wkg;
  var wBar=g('kpi-wkg-bar'); var wLvl=g('kpi-wkg-level');
  if(!isNaN(wkgN) && wkgN > 0){
    var wL = kpiLevel('wkg', wkgN);
    if(wBar) setTimeout(function(){wBar.style.width=wL.pct+'%';},280);
    if(wLvl){wLvl.textContent=wL.label; wLvl.style.color=wL.c;}
  } else {
    if(wBar) wBar.style.width='0%';
    if(wLvl){wLvl.textContent='SIN DATOS'; wLvl.style.color='var(--dim)';}
  }

  /* Bio strip */
  var bwEl=g('kpi-weight'), bwU=g('kpi-weight-u');
  if(bwEl){ bwEl.textContent=weight; bwEl.style.color='var(--text)'; }
  if(bwU)  bwU.style.display='';
  var bhEl=g('kpi-height'), bhU=g('kpi-height-u');
  if(bhEl){ bhEl.textContent=height; bhEl.style.color='var(--text)'; }
  if(bhU)  bhU.style.display='';
  var imc    = (weight / Math.pow(height/100, 2)).toFixed(1);
  var imcEl  = g('kpi-imc-val'); var imcLbl = g('kpi-imc-lbl');
  var imcC   = imc<18.5?'var(--cyan)':imc<25?'var(--green)':imc<30?'var(--gold)':'var(--red)';
  var imcT   = imc<18.5?'Bajo peso':imc<25?'Normal':imc<30?'Sobrepeso':'Obesidad';
  if(imcEl){ imcEl.textContent=imc; imcEl.style.color=imcC; }
  if(imcLbl){ imcLbl.textContent=imcT; imcLbl.style.color=imcC; }

  /* Discipline cards */
  if(d.css){   var cEl=g('kpi-css'); if(cEl) cEl.textContent=d.css; }
  if(d.runPace){var rEl=g('kpi-run'); if(rEl) rEl.textContent=d.runPace; }
  if(d.fcmax){
    var fmEl=g('kpi-fcmax'); if(fmEl) fmEl.textContent=d.fcmax;
    var ftEl=g('kpi-fcthr'); if(ftEl) ftEl.textContent=Math.round(d.fcmax*0.78);
  }

  /* ── Zones FC panel header ── */
  var zf = document.getElementById('zones-fcmax'); if(zf && d.fcmax) zf.textContent = d.fcmax;
}

function pfShowToast(msg){
  var t = document.getElementById('ed-toast-center');
  if(!t) return;
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(function(){ t.classList.remove('show'); }, 2600);
}

// Close on overlay click — event delegation (ed-overlay is injected after this script tag)
window.addEventListener('click', function(e){
  if(e.target && e.target.id === 'ed-overlay') closeProfileDrawer();
});

// Close on ESC
document.addEventListener('keydown', function(e){
  if(e.key==='Escape') closeProfileDrawer();
});


/* ════════════ INLINE HERO STAT EDIT ════════════ */
var _hsEl = null;

function hsEdit(el, e){
  if(e) e.stopPropagation();
  if(el.classList.contains('readonly') || el.classList.contains('editing')) return;
  if(_hsEl && _hsEl !== el) hsDone(_hsEl, false);

  var field  = el.dataset.hfield;
  var inp    = el.querySelector('.hs-input');
  var valEl  = el.querySelector('.hs-val');
  if(!inp || !valEl) return;

  inp.value = valEl.textContent.trim();
  el.classList.add('editing');
  _hsEl = el;
  requestAnimationFrame(function(){ inp.focus(); inp.select(); });

  inp.onkeydown = function(ev){
    if(ev.key === 'Enter') { ev.preventDefault(); hsDone(el, true); }
    if(ev.key === 'Escape'){ ev.preventDefault(); hsDone(el, false); }
    ev.stopPropagation();
  };
  inp.onblur = function(){ setTimeout(function(){ if(_hsEl===el) hsDone(el,true); },180); };
}

function hsDone(el, save){
  var field  = el.dataset.hfield;
  var inp    = el.querySelector('.hs-input');
  var valEl  = el.querySelector('.hs-val');

  if(save && inp && inp.value.trim() && valEl){
    var num = parseFloat(inp.value.trim());
    if(isNaN(num)) { el.classList.remove('editing'); _hsEl=null; return; }
    valEl.textContent = num;

    var d = JSON.parse(localStorage.getItem('kl_athlete_data') || '{}');
    d[field] = num;

    // Recalculate W/kg if FTP changes
    if(field === 'ftp'){
      var _w = parseFloat(d.weight) || 62;
      var wkg = (num / _w).toFixed(2);
      var wkgH = document.getElementById('pf-wkg');
      var wkgB = document.getElementById('pf-bio-wkg');
      var wkgP = document.getElementById('ph-wkg');
      if(wkgH) wkgH.textContent = wkg;
      if(wkgB) wkgB.textContent = wkg + ' W/kg';
      if(wkgP) wkgP.textContent = wkg;
      var bf  = document.getElementById('pf-bio-ftp');  if(bf)  bf.textContent  = num;
      var phf = document.getElementById('ph-ftp');      if(phf) phf.textContent = num;
    }
    // Sync FCMax
    if(field === 'fcmax'){
      var thrEl = document.getElementById('pf-bio-fc-thr');
      if(thrEl) thrEl.textContent = Math.round(num*0.78);
      var bfm  = document.getElementById('pf-bio-fcmax'); if(bfm) bfm.textContent = num;
      var phfc = document.getElementById('ph-fcmax');     if(phfc) phfc.textContent = num;
    }
    // Sync CTL
    if(field === 'ctl'){
      var phctl = document.getElementById('ph-ctl'); if(phctl) phctl.textContent = num;
    }
    // Sync VO2Max
    if(field === 'vo2max'){
      var bv = document.getElementById('pf-bio-vo2max'); if(bv) bv.textContent = num;
    }

    localStorage.setItem('kl_athlete_data', JSON.stringify(d));
  }

  el.classList.remove('editing');
  if(_hsEl === el) _hsEl = null;
}

// Close hero stat inline edit when clicking elsewhere
document.addEventListener('click', function(e){
  if(_hsEl && !_hsEl.contains(e.target)) hsDone(_hsEl, false);
});

/* ════════════ PAGE INIT ════════════ */
(function(){
  function _applyFromStorage(){
    var raw = localStorage.getItem('kl_athlete_data');
    var stored = raw ? JSON.parse(raw) : {};
    var D = _PROFILE_DEFAULTS;
    /* Mezcla: stored gana, pero null/undefined/0 caen al default */
    var d = {
      name:      stored.name     || D.name,
      ftp:       stored.ftp      || D.ftp,
      weight:    stored.weight   || D.weight,
      height:    stored.height   || D.height,
      vo2max:    stored.vo2max   || D.vo2max,
      fcmax:     stored.fcmax    || D.fcmax,
      css:       stored.css      || D.css,
      runPace:   stored.runPace  || D.runPace,
      goal:      stored.goal     || D.goal,
      ctl:       stored.ctl,
      readiness: stored.readiness
    };
    try{ applyProfileData(d); }catch(err){ console.error('LabX profile init error:', err); }
  }
  _applyFromStorage();
  window.addEventListener('pageshow', function(){ _applyFromStorage(); });
  window.addEventListener('storage', function(e){ if(e.key==='kl_athlete_data') _applyFromStorage(); });
})();


/* ── MIS CARRERAS — Race display & management ── */
/* ── MC_RACES: base de datos de carreras ── */
var MC_RACES = [
  // ── CHILE — FTECH ───────────────────────────────────────────────────────
  {id:'concon-oly-26',     name:'TOPMAN Concón',             type:'Olímpico',typeClass:'olimpico',date:'2026-08-23',dateLabel:'23 AGO 2026',location:'Concón, Valparaíso',           flag:'🇨🇱',org:'TOPMAN'},
  {id:'tri-stgo-26',       name:'Triatlón Santiago',         type:'Olímpico',typeClass:'olimpico',date:'2026-11-15',dateLabel:'15 NOV 2026',location:'Santiago, R. Metropolitana',   flag:'🇨🇱',org:'FTECH'},
  {id:'tri-renaca-27',     name:'Triatlón Reñaca Sprint',    type:'Sprint',  typeClass:'sprint',  date:'2027-01-10',dateLabel:'10 ENE 2027',location:'Reñaca, Valparaíso',           flag:'🇨🇱',org:'FTECH'},
  {id:'tri-pvaras-27',     name:'Triatlón Puerto Varas',     type:'Olímpico',typeClass:'olimpico',date:'2027-01-31',dateLabel:'31 ENE 2027',location:'Puerto Varas, Los Lagos',      flag:'🇨🇱',org:'FTECH'},
  {id:'tri-villarrica-27', name:'Triatlón Villarrica',       type:'Olímpico',typeClass:'olimpico',date:'2027-02-14',dateLabel:'14 FEB 2027',location:'Villarrica, Araucanía',        flag:'🇨🇱',org:'FTECH'},
  {id:'tri-osorno-27',     name:'Triatlón Osorno Sprint',    type:'Sprint',  typeClass:'sprint',  date:'2027-03-14',dateLabel:'14 MAR 2027',location:'Osorno, Los Lagos',             flag:'🇨🇱',org:'FTECH'},
  {id:'tri-pucon-spr-27',  name:'Triatlón Pucón Sprint',     type:'Sprint',  typeClass:'sprint',  date:'2027-01-25',dateLabel:'25 ENE 2027',location:'Pucón, Araucanía',             flag:'🇨🇱',org:'FTECH'},
  {id:'tri-cart-spr-27',   name:'Triatlón Cartagena Sprint', type:'Sprint',  typeClass:'sprint',  date:'2027-02-07',dateLabel:'07 FEB 2027',location:'Cartagena, Valparaíso',        flag:'🇨🇱',org:'FTECH'},
  {id:'tri-temuco-27',     name:'Triatlón Temuco',           type:'Olímpico',typeClass:'olimpico',date:'2027-03-07',dateLabel:'07 MAR 2027',location:'Temuco, Araucanía',            flag:'🇨🇱',org:'FTECH'},
  {id:'tri-vdm-spr-26',   name:'Triatlón Viña del Mar Spr', type:'Sprint',  typeClass:'sprint',  date:'2026-10-11',dateLabel:'11 OCT 2026',location:'Viña del Mar, Valparaíso',    flag:'🇨🇱',org:'FTECH'},
  {id:'tri-iquique-26',    name:'Triatlón Iquique Sprint',   type:'Sprint',  typeClass:'sprint',  date:'2026-09-20',dateLabel:'20 SEP 2026',location:'Iquique, Tarapacá',            flag:'🇨🇱',org:'FTECH'},
  {id:'tri-copiapo-27',    name:'Triatlón Copiapó',          type:'Olímpico',typeClass:'olimpico',date:'2027-04-04',dateLabel:'04 ABR 2027',location:'Copiapó, Atacama',             flag:'🇨🇱',org:'FTECH'},
  {id:'challenge-chile-27',name:'Challenge Chile',           type:'70.3',   typeClass:'half',   date:'2027-04-18',dateLabel:'18 ABR 2027',location:'Santiago, Chile',              flag:'🇨🇱',org:'Challenge'},
  // ── IRONMAN 70.3 — LATAM ────────────────────────────────────────────────
  {id:'im703-panama-26',   name:'Ironman 70.3 Panamá',       type:'70.3',   typeClass:'half',   date:'2026-08-16',dateLabel:'16 AGO 2026',location:'Panamá City, Panamá',          flag:'🇵🇦',org:'Ironman'},
  {id:'im703-lima-26',     name:'Ironman 70.3 Lima',         type:'70.3',   typeClass:'half',   date:'2026-09-27',dateLabel:'27 SEP 2026',location:'Lima, Perú',                    flag:'🇵🇪',org:'Ironman'},
  {id:'im703-medellin-26', name:'Ironman 70.3 Medellín',     type:'70.3',   typeClass:'half',   date:'2026-10-04',dateLabel:'04 OCT 2026',location:'Medellín, Colombia',            flag:'🇨🇴',org:'Ironman'},
  {id:'im703-bsas-26',     name:'Ironman 70.3 Buenos Aires', type:'70.3',   typeClass:'half',   date:'2026-10-18',dateLabel:'18 OCT 2026',location:'Buenos Aires, Argentina',       flag:'🇦🇷',org:'Ironman'},
  {id:'im703-cancun-26',   name:'Ironman 70.3 Cancún',       type:'70.3',   typeClass:'half',   date:'2026-11-01',dateLabel:'01 NOV 2026',location:'Cancún, Quintana Roo, México', flag:'🇲🇽',org:'Ironman'},
  {id:'im703-pucon-27',    name:'Ironman 70.3 Pucón',        type:'70.3',   typeClass:'half',   date:'2027-01-17',dateLabel:'17 ENE 2027',location:'Pucón, Araucanía, Chile',      flag:'🇨🇱',org:'Ironman'},
  {id:'im703-bariloche-27',name:'Ironman 70.3 Bariloche',    type:'70.3',   typeClass:'half',   date:'2027-02-07',dateLabel:'07 FEB 2027',location:'Bariloche, Argentina',          flag:'🇦🇷',org:'Ironman'},
  {id:'im703-cartagena-27',name:'Ironman 70.3 Cartagena',    type:'70.3',   typeClass:'half',   date:'2027-03-07',dateLabel:'07 MAR 2027',location:'Cartagena, Colombia',           flag:'🇨🇴',org:'Ironman'},
  {id:'im703-manta-27',    name:'Ironman 70.3 Manta',        type:'70.3',   typeClass:'half',   date:'2027-05-02',dateLabel:'02 MAY 2027',location:'Manta, Manabí, Ecuador',        flag:'🇪🇨',org:'Ironman'},
  {id:'im703-flori-27',    name:'Ironman 70.3 Florianópolis',type:'70.3',   typeClass:'half',   date:'2027-05-23',dateLabel:'23 MAY 2027',location:'Florianópolis, Brasil',         flag:'🇧🇷',org:'Ironman'},
  {id:'im703-smarta-27',   name:'Ironman 70.3 Santa Marta',  type:'70.3',   typeClass:'half',   date:'2027-06-06',dateLabel:'06 JUN 2027',location:'Santa Marta, Colombia',         flag:'🇨🇴',org:'Ironman'},
  {id:'im703-cozumel-26',  name:'Ironman 70.3 Cozumel',      type:'70.3',   typeClass:'half',   date:'2026-09-20',dateLabel:'20 SEP 2026',location:'Cozumel, Quintana Roo, México',flag:'🇲🇽',org:'Ironman'},
  {id:'im703-langkawi-26', name:'Ironman 70.3 Langkawi',     type:'70.3',   typeClass:'half',   date:'2026-11-07',dateLabel:'07 NOV 2026',location:'Langkawi, Malasia',             flag:'🇲🇾',org:'Ironman'},
  {id:'im703-phuket-26',   name:'Ironman 70.3 Thailand',     type:'70.3',   typeClass:'half',   date:'2026-11-22',dateLabel:'22 NOV 2026',location:'Phuket, Tailandia',             flag:'🇹🇭',org:'Ironman'},
  {id:'im703-ec-27',       name:'Ironman 70.3 European Champ',type:'70.3',  typeClass:'half',   date:'2027-06-27',dateLabel:'27 JUN 2027',location:'Kraichgau, Alemania',           flag:'🇩🇪',org:'Ironman'},
  {id:'challenge-lima-27', name:'Challenge Lima',            type:'70.3',   typeClass:'half',   date:'2027-04-11',dateLabel:'11 ABR 2027',location:'Lima, Perú',                    flag:'🇵🇪',org:'Challenge'},
  // ── IRONMAN 70.3 — WORLD CHAMPIONSHIP ──────────────────────────────────
  {id:'im703-worlds-26',   name:'70.3 World Championship',   type:'70.3',   typeClass:'half',   date:'2026-09-06',dateLabel:'06 SEP 2026',location:'Taupo, Nueva Zelanda',          flag:'🇳🇿',org:'Ironman'},
  {id:'im703-worlds-27',   name:'70.3 World Championship 27',type:'70.3',   typeClass:'half',   date:'2027-09-05',dateLabel:'05 SEP 2027',location:'Por confirmar',                 flag:'🌎',org:'Ironman'},
  // ── IRONMAN FULL ─────────────────────────────────────────────────────────
  {id:'im-kona-26',        name:'Ironman World Championship', type:'Ironman',typeClass:'full',   date:'2026-10-10',dateLabel:'10 OCT 2026',location:'Kailua-Kona, Hawái, USA',      flag:'🇺🇸',org:'Ironman'},
  {id:'im-bsas-26',        name:'Ironman Buenos Aires',       type:'Ironman',typeClass:'full',   date:'2026-10-25',dateLabel:'25 OCT 2026',location:'Buenos Aires, Argentina',       flag:'🇦🇷',org:'Ironman'},
  {id:'im-cozumel-26',     name:'Ironman Cozumel',            type:'Ironman',typeClass:'full',   date:'2026-11-29',dateLabel:'29 NOV 2026',location:'Cozumel, México',               flag:'🇲🇽',org:'Ironman'},
  {id:'im-brazil-27',      name:'Ironman Brasil',             type:'Ironman',typeClass:'full',   date:'2027-05-25',dateLabel:'25 MAY 2027',location:'Florianópolis, Brasil',         flag:'🇧🇷',org:'Ironman'},
  {id:'im-wa-27',          name:'Ironman Western Australia',  type:'Ironman',typeClass:'full',   date:'2026-11-29',dateLabel:'29 NOV 2026',location:'Busselton, Australia',           flag:'🇦🇺',org:'Ironman'},
  {id:'im-lanzarote-27',   name:'Ironman Lanzarote',          type:'Ironman',typeClass:'full',   date:'2027-05-22',dateLabel:'22 MAY 2027',location:'Lanzarote, España',              flag:'🇪🇸',org:'Ironman'},
  {id:'challenge-roth-27', name:'Challenge Roth',             type:'Ironman',typeClass:'full',   date:'2027-06-27',dateLabel:'27 JUN 2027',location:'Roth, Baviera, Alemania',        flag:'🇩🇪',org:'Challenge'},
  // ── PTO / WORLD TRIATHLON ─────────────────────────────────────────────
  {id:'pto-t100-cancun-26',name:'PTO T100 Cancún',            type:'Sprint', typeClass:'sprint', date:'2026-10-03',dateLabel:'03 OCT 2026',location:'Cancún, México',               flag:'🇲🇽',org:'PTO'},
  {id:'wt-contsam-26',     name:'WT Continental Champ. SAM',  type:'Olímpico',typeClass:'olimpico',date:'2026-09-12',dateLabel:'12 SEP 2026',location:'LATAM (por confirmar)',      flag:'🌎',org:'World Triathlon'}
];

var _mcPickerType = 'all';

function mcOpenPicker(){
  var ov=document.getElementById('mc-picker-overlay');
  var dr=document.getElementById('mc-picker-drawer');
  if(ov){ ov.classList.add('open'); }
  if(dr){ dr.classList.add('open'); }
  document.body.style.overflow='hidden';
  // reset search + filter
  var inp=document.getElementById('mc-pk-inp');
  if(inp) inp.value='';
  _mcPickerType='all';
  var pills=document.querySelectorAll('.mc-pk-pill');
  pills.forEach(function(p){ p.classList.remove('on'); if(p.dataset.type==='all') p.classList.add('on'); });
  _mcRenderPickerBody();
}

function mcClosePicker(){
  var ov=document.getElementById('mc-picker-overlay');
  var dr=document.getElementById('mc-picker-drawer');
  if(ov) ov.classList.remove('open');
  if(dr) dr.classList.remove('open');
  document.body.style.overflow='';
}

function mcSetType(btn, type){
  _mcPickerType=type;
  document.querySelectorAll('.mc-pk-pill').forEach(function(p){ p.classList.remove('on'); });
  if(btn) btn.classList.add('on');
  _mcRenderPickerBody();
}

function mcFilterRaces(){
  _mcRenderPickerBody();
}

function _mcRenderPickerBody(){
  var body = document.getElementById('mc-pk-body');
  if (!body) { console.warn('KL: mc-pk-body not found'); return; }

  var term = ((document.getElementById('mc-pk-inp') || {}).value || '').toLowerCase().trim();
  var addedIds = _mcRaces.map(function(r){ return r.id; });

  /* Clear existing content */
  while (body.firstChild) body.removeChild(body.firstChild);

  /* ── Selected section ── */
  if (_mcRaces.length > 0) {
    var selHdr = document.createElement('div');
    selHdr.className = 'mc-pk-sel-hdr';
    selHdr.textContent = 'Mis Carreras Seleccionadas (' + _mcRaces.length + ')';
    body.appendChild(selHdr);

    var selList = document.createElement('div');
    selList.className = 'mc-pk-sel-list';
    _mcRaces.forEach(function(r) {
      var item = document.createElement('div'); item.className = 'mc-pk-sel-item';
      var fl = document.createElement('span'); fl.className = 'mc-pk-sel-flag'; fl.textContent = r.flag || '🏁';
      var nm = document.createElement('span'); nm.className = 'mc-pk-sel-name'; nm.textContent = r.name;
      var dt = document.createElement('span'); dt.className = 'mc-pk-sel-date'; dt.textContent = r.dateLabel;
      var rm = document.createElement('button'); rm.className = 'mc-pk-sel-rm'; rm.textContent = '✕';
      rm.setAttribute('aria-label', 'Quitar ' + r.name);
      (function(rid){ rm.addEventListener('click', function(){ mcRemoveFromPicker(rid); }); })(r.id);
      item.appendChild(fl); item.appendChild(nm); item.appendChild(dt); item.appendChild(rm);
      selList.appendChild(item);
    });
    body.appendChild(selList);
  }

  /* ── Filter MC_RACES ── */
  var filtered = MC_RACES.filter(function(r) {
    if (_mcPickerType === 'ftech') { if ((r.org || '') !== 'FTECH') return false; }
    else if (_mcPickerType !== 'all') { if (r.typeClass !== _mcPickerType) return false; }
    if (!term) return true;
    return ((r.name || '') + ' ' + (r.location || '') + ' ' + (r.type || '') + ' ' + (r.org || '')).toLowerCase().indexOf(term) >= 0;
  });

  /* ── Header row ── */
  var allHdr = document.createElement('div'); allHdr.className = 'mc-pk-all-hdr';
  var allHdrLbl = document.createElement('span'); allHdrLbl.textContent = 'Carreras disponibles';
  var allHdrCnt = document.createElement('span'); allHdrCnt.className = 'mc-pk-count';
  allHdrCnt.textContent = filtered.length + ' carrera' + (filtered.length !== 1 ? 's' : '');
  allHdr.appendChild(allHdrLbl); allHdr.appendChild(allHdrCnt);
  body.appendChild(allHdr);

  /* ── Race cards grid ── */
  if (filtered.length === 0) {
    var noRes = document.createElement('div'); noRes.className = 'mc-pk-no-results';
    noRes.textContent = 'Sin resultados · prueba otro término o busca por país';
    body.appendChild(noRes);
    return;
  }

  var typeColors = {
    olimpico: { c:'var(--cyan)',  bg:'rgba(14,165,233,.12)', bd:'rgba(14,165,233,.28)' },
    sprint:   { c:'var(--green)', bg:'rgba(16,185,129,.12)', bd:'rgba(16,185,129,.28)' },
    half:     { c:'var(--orange)',bg:'rgba(255,101,53,.12)', bd:'rgba(255,101,53,.28)' },
    full:     { c:'var(--gold)',  bg:'rgba(240,165,0,.12)',  bd:'rgba(240,165,0,.28)'  }
  };

  var grid = document.createElement('div'); grid.className = 'mc-pk-grid';

  filtered.forEach(function(r) {
    var isAdded = addedIds.indexOf(r.id) >= 0;
    var card = document.createElement('div');
    card.className = 'mc-pk-card' + (isAdded ? ' mc-pk-added' : '');

    /* Top row: flag + type badge */
    var top = document.createElement('div'); top.className = 'mc-pk-c-top';
    var flag = document.createElement('span'); flag.className = 'mc-pk-c-flag'; flag.textContent = r.flag || '🏁';
    var badge = document.createElement('span'); badge.className = 'mc-pk-c-type'; badge.textContent = r.type || '';
    var tc = typeColors[r.typeClass] || typeColors.olimpico;
    badge.style.cssText = 'color:' + tc.c + ';background:' + tc.bg + ';border-color:' + tc.bd;
    top.appendChild(flag); top.appendChild(badge);

    /* Name, location, date */
    var name = document.createElement('div'); name.className = 'mc-pk-c-name'; name.textContent = r.name || '';
    var loc  = document.createElement('div'); loc.className  = 'mc-pk-c-loc';  loc.textContent  = r.location || '';
    var date = document.createElement('div'); date.className = 'mc-pk-c-date'; date.textContent = r.dateLabel || '';

    /* Footer: org + add button */
    var foot = document.createElement('div'); foot.className = 'mc-pk-c-foot';
    var org  = document.createElement('span'); org.className  = 'mc-pk-c-org';  org.textContent  = r.org || '';
    var btn  = document.createElement('button');
    btn.className = 'mc-pk-c-add' + (isAdded ? ' mc-pk-added' : '');
    btn.textContent = isAdded ? '✓ Agregada' : '+';
    if (!isAdded) {
      (function(rid){ btn.addEventListener('click', function(){ mcAddRace(rid); }); })(r.id);
    }
    foot.appendChild(org); foot.appendChild(btn);

    card.appendChild(top); card.appendChild(name); card.appendChild(loc);
    card.appendChild(date); card.appendChild(foot);
    grid.appendChild(card);
  });

  body.appendChild(grid);
}

function mcAddRace(id){
  var r=MC_RACES.filter(function(x){ return x.id===id; })[0];
  if(!r) return;
  if(_mcRaces.filter(function(x){ return x.id===id; }).length) return;
  _mcRaces.push(r);
  // Sort by date ascending
  _mcRaces.sort(function(a,b){ return new Date(a.date)-new Date(b.date); });
  _mcSave();
  mcRender();
  _mcTickStart();
  _mcRenderPickerBody();
}

function mcRemoveFromPicker(id){
  mcRemove(id);
  _mcRenderPickerBody();
}

var _mcRaces = [];
var _mcRaceDate = null;

function _mcSave(){
  var j = JSON.stringify(_mcRaces);
  localStorage.setItem('kl_my_races', j);
  try{ sessionStorage.setItem('kl_my_races', j); }catch(e){}
  if(_mcRaces.length) localStorage.setItem('kl_next_race', JSON.stringify(_mcRaces[0]));
}

function mcLoad(){
  try{
    var saved = sessionStorage.getItem('kl_my_races') || localStorage.getItem('kl_my_races');
    if(saved) { _mcRaces = JSON.parse(saved)||[]; }
    else {
      var leg = JSON.parse(localStorage.getItem('kl_next_race')||'null');
      if(leg){ _mcRaces=[leg]; _mcSave(); }
    }
  }catch(e){ _mcRaces=[]; }
  mcRender();
}

function mcRender(){
  var empty = document.getElementById('mc-empty');
  var grid  = document.getElementById('mc-races-grid');
  var pc    = document.getElementById('mc-primary-card');
  var sec   = document.getElementById('mc-secondary');
  if(!empty||!grid||!pc||!sec) return;

  if(_mcRaces.length === 0){
    empty.style.display='flex'; grid.style.display='none'; return;
  }
  empty.style.display='none'; grid.style.display='grid';

  /* Primary race */
  var p = _mcRaces[0];
  _mcRaceDate = new Date(p.date+'T07:00:00');
  var fl=document.getElementById('mc-flag'); if(fl) fl.textContent=p.flag||'🏁';
  var nm=document.getElementById('mc-name'); if(nm) nm.textContent=p.name;
  var dt=document.getElementById('mc-date'); if(dt) dt.textContent=p.dateLabel+' · '+p.location;
  var tb=document.getElementById('mc-type-badge');
  if(tb){
    tb.textContent=p.type;
    var cl={olimpico:{c:'var(--cyan)',bg:'rgba(14,165,233,.12)',bd:'rgba(14,165,233,.25)'},sprint:{c:'var(--green)',bg:'rgba(16,185,129,.12)',bd:'rgba(16,185,129,.25)'},half:{c:'var(--orange)',bg:'rgba(255,101,53,.12)',bd:'rgba(255,101,53,.25)'},full:{c:'var(--gold)',bg:'rgba(240,165,0,.12)',bd:'rgba(240,165,0,.25)'}};
    var cs=cl[p.typeClass]||cl.olimpico;
    tb.style.cssText='color:'+cs.c+';background:'+cs.bg+';border-color:'+cs.bd;
  }
  var cta=document.getElementById('mc-cta');
  if(cta) cta.href='race_predictor.html';

  /* Secondary races */
  var labels=['B','C','D','E','F'];
  if(_mcRaces.length<=1){ sec.innerHTML=''; return; }
  sec.innerHTML=_mcRaces.slice(1).map(function(r,i){
    var days=Math.ceil((new Date(r.date+'T07:00:00')-Date.now())/86400000);
    var dStr=days>0?days:'—';
    var dCol=days<30?'var(--orange)':days<90?'var(--gold)':'var(--text)';
    return '<div class="mc-sec-card">'+
      '<button class="mc-sec-rm" onclick="mcRemove(\''+r.id+'\')" aria-label="Quitar">✕</button>'+
      '<div class="mc-sec-badge">META '+(labels[i]||i+2)+'</div>'+
      '<div class="mc-sec-flag">'+r.flag+'</div>'+
      '<div class="mc-sec-name">'+r.name+'</div>'+
      '<div class="mc-sec-date">'+r.dateLabel+'</div>'+
      '<div class="mc-sec-days" style="color:'+dCol+'">'+dStr+'<span class="mc-sec-days-lbl"> días</span></div>'+
      '<a href="race_predictor.html" class="mc-sec-pred">→ Predictor</a>'+
    '</div>';
  }).join('');
}

function mcRemove(id){
  _mcRaces = _mcRaces.filter(function(r){return r.id!==id;});
  _mcSave(); mcRender(); _mcTickStart();
}

/* Countdown tick for primary race */
var _mcTickTimer = null;
function _mcTick(){
  if(!_mcRaceDate) return;
  var diff = _mcRaceDate - new Date();
  var g=function(id,v){var el=document.getElementById(id);if(el)el.textContent=v;};
  if(diff<=0){ g('mc-cd-d','00');g('mc-cd-h','00');g('mc-cd-m','00');g('mc-cd-s','00'); return; }
  g('mc-cd-d',String(Math.floor(diff/86400000)).padStart(2,'0'));
  g('mc-cd-h',String(Math.floor((diff%86400000)/3600000)).padStart(2,'0'));
  g('mc-cd-m',String(Math.floor((diff%3600000)/60000)).padStart(2,'0'));
  g('mc-cd-s',String(Math.floor((diff%60000)/1000)).padStart(2,'0'));
}
function _mcTickStart(){
  if(_mcTickTimer) clearInterval(_mcTickTimer);
  if(_mcRaceDate){ _mcTick(); _mcTickTimer=setInterval(_mcTick,1000); }
}

/* Race picker — navigates to dashboard's race drawer */

/* ── Custom race form ──────────────────────────────────────────── */
function mcToggleCustomForm(){
  var form=document.getElementById('mc-custom-form');
  var btn=document.getElementById('mc-custom-toggle');
  if(!form) return;
  var open=form.classList.toggle('open');
  if(btn) btn.style.borderStyle=open?'solid':'dashed';
  if(open){
    var d=document.getElementById('cf-date');
    if(d && !d.value){
      var t=new Date(); t.setDate(t.getDate()+60);
      d.value=t.toISOString().slice(0,10);
    }
  }
}

function mcAddCustomRace(){
  var name=(document.getElementById('cf-name')||{}).value||'';
  var dateV=(document.getElementById('cf-date')||{}).value||'';
  var typeV=((document.getElementById('cf-type')||{}).value||'olimpico|Olímpico').split('|');
  var loc=(document.getElementById('cf-loc')||{}).value||'';
  var org=(document.getElementById('cf-org')||{}).value||'Personalizada';

  name=name.trim();
  if(!name||!dateV){ alert('Completa al menos nombre y fecha.'); return; }

  var typeClass=typeV[0], typeName=typeV[1]||typeV[0];
  var dateObj=new Date(dateV+'T07:00:00');
  var months=['ENE','FEB','MAR','ABR','MAY','JUN','JUL','AGO','SEP','OCT','NOV','DIC'];
  var dateLabel=dateObj.getDate()+' '+months[dateObj.getMonth()]+' '+dateObj.getFullYear();

  /* Assign flag by location text */
  var flag='🏁';
  var locLow=(loc||'').toLowerCase();
  if(locLow.indexOf('chile')>=0||locLow.indexOf('concón')>=0||locLow.indexOf('concon')>=0||locLow.indexOf('santiago')>=0||locLow.indexOf('pucón')>=0||locLow.indexOf('pucon')>=0) flag='🇨🇱';
  else if(locLow.indexOf('argentina')>=0||locLow.indexOf('buenos aires')>=0||locLow.indexOf('bariloche')>=0) flag='🇦🇷';
  else if(locLow.indexOf('perú')>=0||locLow.indexOf('peru')>=0||locLow.indexOf('lima')>=0) flag='🇵🇪';
  else if(locLow.indexOf('brasil')>=0||locLow.indexOf('brazil')>=0||locLow.indexOf('florianópolis')>=0) flag='🇧🇷';
  else if(locLow.indexOf('colombia')>=0||locLow.indexOf('medellín')>=0||locLow.indexOf('cartagena')>=0) flag='🇨🇴';
  else if(locLow.indexOf('españa')>=0||locLow.indexOf('spain')>=0) flag='🇪🇸';
  else if(locLow.indexOf('mexico')>=0||locLow.indexOf('méxico')>=0||locLow.indexOf('cancun')>=0) flag='🇲🇽';

  /* Build unique id from name+date */
  var id='custom-'+(name.toLowerCase().replace(/[^a-z0-9]/g,'-').slice(0,18))+'-'+(dateV.slice(0,7));

  var r={id:id, name:name, type:typeName, typeClass:typeClass, date:dateV, dateLabel:dateLabel, location:loc||'—', flag:flag, org:org||'—', custom:true};

  /* Add and save */
  if(_mcRaces.filter(function(x){return x.id===id;}).length){
    alert('Esta carrera ya fue agregada.'); return;
  }
  _mcRaces.push(r);
  _mcRaces.sort(function(a,b){return new Date(a.date)-new Date(b.date);});
  _mcSave();
  mcRender();
  _mcTickStart();

  /* Reset form and close */
  document.getElementById('cf-name').value='';
  document.getElementById('cf-loc').value='';
  document.getElementById('cf-org').value='';
  var form=document.getElementById('mc-custom-form');
  if(form) form.classList.remove('open');
  var btn=document.getElementById('mc-custom-toggle');
  if(btn) btn.style.borderStyle='dashed';
  _mcRenderPickerBody();
}

/* Init on load */
mcLoad();
_mcTickStart();

/* Race Picker — wire overlay click and pre-render race list */
document.addEventListener('DOMContentLoaded', function(){
  var ov = document.getElementById('mc-picker-overlay');
  if (ov) ov.addEventListener('click', mcClosePicker);
  /* Pre-render picker body so races are ready on first open */
  _mcRenderPickerBody();
});

