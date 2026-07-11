
(function(){
'use strict';

// â”€â”€ Config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
var API = 'http://localhost:8000/api';
var _token = null;
var _me    = null;
var _cache = { athletes:[], groups:[], workouts:[], assigns:[] };
var _addMemberGroupId = null;

// â”€â”€ Auth â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function getToken(){ return _token || localStorage.getItem('lx_co_token'); }
function setToken(t){ _token=t; localStorage.setItem('lx_co_token',t); }

async function apiGet(path){
  var r = await fetch(API+path,{headers:{Authorization:'Bearer '+getToken()}});
  if(!r.ok) throw new Error(await r.text());
  return r.json();
}
async function apiPost(path,body){
  var r = await fetch(API+path,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+getToken()},body:JSON.stringify(body)});
  if(!r.ok){ var t=await r.text(); throw new Error(t); }
  return r.json();
}
async function apiDelete(path){
  var r = await fetch(API+path,{method:'DELETE',headers:{Authorization:'Bearer '+getToken()}});
  if(!r.ok) throw new Error(await r.text());
  return r.status===204 ? null : r.json();
}

// â”€â”€ Toast â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
var _toastTimer;
function toast(msg, type){
  type = type||'ok';
  var el = document.getElementById('co-toast');
  el.textContent=msg; el.className='show '+type;
  clearTimeout(_toastTimer);
  _toastTimer=setTimeout(function(){ el.className=''; },3500);
}

// â”€â”€ Sidebar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
window.sbToggle=function(){
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('sb-overlay').classList.toggle('show');
};
window.sbClose=function(){
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sb-overlay').classList.remove('show');
};

// â”€â”€ Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
window.openModal=function(id){ document.getElementById(id).classList.add('open'); };
window.closeModal=function(id){ document.getElementById(id).classList.remove('open'); };

// â”€â”€ Tabs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
window.switchTab=function(name){
  document.querySelectorAll('.coach-tab').forEach(function(b){ b.classList.toggle('on', b.dataset.tab===name); });
  document.querySelectorAll('.tab-panel').forEach(function(p){ p.classList.toggle('on', p.id==='tab-'+name); });
  if(name==='athletes'){ loadAthletes(); populateGroupsInAthleteModal(); }
  if(name==='groups')   loadGroups();
  if(name==='workouts') loadWorkouts();
  if(name==='assign')   loadAssignTab();
  if(name==='adherence') loadAdherenceFilters();
  if(name==='mi-atleta') initMiAtletaTab();
};

// â”€â”€ Login â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
window.coLogin=async function(){
  var email=document.getElementById('lw-email').value.trim();
  var pass =document.getElementById('lw-pass').value;
  var errEl=document.getElementById('lw-err');
  errEl.style.display='none';
  try{
    var data = await apiPost('/auth/login',{email:email,password:pass});
    setToken(data.access_token);
    _me = data;
    showApp();
  }catch(e){
    errEl.style.display='block';
  }
};

window.coLogout=function(){
  localStorage.removeItem('lx_co_token');
  localStorage.removeItem('lx_co_rol');
  localStorage.removeItem('lx_co_nombre');
  _token=null; _me=null;
  showLoginWall();
};

// â”€â”€ Init â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function init(){
  var t = getToken();
  if(!t){ showLoginWall(); return; }
  try{
    _me = await apiGet('/auth/me');
    if(_me.rol==='athlete'){ toast('Sin acceso coach','err'); showLoginWall(); return; }
    showApp();
  }catch(e){ showLoginWall(); }
}

function showLoginWall(){
  document.getElementById('login-wall').style.display='flex';
  document.getElementById('coach-app').style.display='none';
}
function showApp(){
  document.getElementById('login-wall').style.display='none';
  document.getElementById('coach-app').style.display='block';
  var initials = (_me.nombre||'C').charAt(0).toUpperCase();
  document.getElementById('co-avatar').textContent   = initials;
  document.getElementById('co-av-tb').textContent    = initials;
  document.getElementById('co-uname').textContent    = _me.nombre;
  document.getElementById('co-urole').textContent    = _me.rol==='admin'?'Admin':'Coach';
  document.getElementById('app-heading').textContent = 'Hola, '+_me.nombre;
  loadOverview();
}

// â”€â”€ Overview â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function loadOverview(){
  try{
    var [ath,grps,wkts] = await Promise.all([
      apiGet('/coach/athletes'),
      apiGet('/coach/groups'),
      apiGet('/coach/workouts'),
    ]);
    _cache.athletes=ath; _cache.groups=grps; _cache.workouts=wkts;
    document.getElementById('kpi-athletes').textContent = ath.length;
    document.getElementById('kpi-groups').textContent   = grps.length;
    document.getElementById('kpi-workouts').textContent = wkts.length;

    // Groups list
    var gl = document.getElementById('ov-groups-list');
    if(!grps.length){ gl.innerHTML='<div class="empty"><p>Sin grupos aÃºn</p></div>'; }
    else{
      gl.innerHTML = grps.slice(0,5).map(function(g){
        return '<div style="display:flex;justify-content:space-between;align-items:center;padding:.45rem 0;border-bottom:1px solid var(--border2)">'
          +'<div><div style="font-size:.85rem;font-weight:500">'+esc(g.nombre)+'</div>'
          +(g.competencia?'<div style="font-size:.72rem;color:var(--dim)">'+esc(g.competencia)+'</div>':'')+'</div>'
          +'<span class="badge badge-cyan">'+g.member_count+' atl.</span></div>';
      }).join('');
    }

    // Upcoming assignments (next 7 days)
    var today = todayISO();
    var next7 = addDays(today,7);
    var asn = await apiGet('/coach/assignments?start='+today+'&end='+next7);
    _cache.assigns=asn;
    var upc=document.getElementById('ov-upcoming');
    if(!asn.length){ upc.innerHTML='<div class="empty"><p>Sin sesiones prÃ³ximas</p></div>'; }
    else{
      upc.innerHTML=asn.slice(0,8).map(function(a){
        var ath=_cache.athletes.find(function(x){return x.id===a.athlete_id;});
        return '<div style="display:flex;gap:.6rem;align-items:center;padding:.4rem 0;border-bottom:1px solid var(--border2)">'
          +'<span class="sport-chip '+sportCls(a.template.sport)+'">'+sportIcon(a.template.sport)+'</span>'
          +'<div style="flex:1"><div style="font-size:.82rem;font-weight:500">'+esc(a.template.nombre)+'</div>'
          +(ath?'<div style="font-size:.7rem;color:var(--dim)">'+esc(ath.nombre)+'</div>':'')+'</div>'
          +'<span style="font-size:.72rem;color:var(--muted)">'+a.date_iso+'</span></div>';
      }).join('');
    }

    // Adherence KPI (last 30 days)
    var from30 = addDays(today,-30);
    try{
      var adh = await apiGet('/coach/adherence?start='+from30+'&end='+today);
      if(adh.length){
        var avg = adh.reduce(function(s,a){return s+a.pct;},0)/adh.length;
        document.getElementById('kpi-adh').textContent = Math.round(avg)+'%';
        document.getElementById('kpi-adh-sub').textContent = adh.length+' atletas';
      }else{ document.getElementById('kpi-adh').textContent='â€”'; }
    }catch(e){ document.getElementById('kpi-adh').textContent='â€”'; }

  }catch(e){ toast('Error cargando resumen','err'); }
}

// â”€â”€ Athletes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function loadAthletes(){
  var tb=document.getElementById('athletes-tbody');
  tb.innerHTML='<tr><td colspan="6" style="text-align:center;color:var(--dim)">Cargando...</td></tr>';
  try{
    var ath = await apiGet('/coach/athletes');
    _cache.athletes=ath;
    if(!ath.length){ tb.innerHTML='<tr><td colspan="6" style="text-align:center;color:var(--dim)">Sin atletas. Crea uno con "+ Nuevo Atleta".</td></tr>'; return; }
    tb.innerHTML = ath.map(function(u){
      var grpNames = _cache.groups.filter(function(g){
        return g.members&&g.members.some&&g.members.some(function(m){return m.user_id===u.id;});
      }).map(function(g){return g.nombre;});
      var garminDot = u.has_garmin
        ? '<span title="Garmin conectado" style="color:var(--green);font-size:1rem">â—</span> <span style="font-size:.72rem;color:var(--green)">Conectado</span>'
        : '<span title="Sin Garmin" style="color:var(--border);font-size:1rem">â—</span> <span style="font-size:.72rem;color:var(--dim)">Sin Garmin</span>';
      return '<tr>'
        +'<td><strong>'+esc(u.nombre)+'</strong></td>'
        +'<td style="color:var(--muted)">'+esc(u.email)+'</td>'
        +'<td>'+planBadge(u.plan_nivel)+'</td>'
        +'<td>'+garminDot+'</td>'
        +'<td style="color:var(--dim);font-size:.78rem">'+grpNames.join(', ')+'</td>'
        +'<td style="display:flex;gap:.35rem;align-items:center;flex-wrap:wrap">'
        +'<button class="btn btn-ghost btn-sm" onclick="openAthletePlan(\''+u.id+'\',\''+esc(u.nombre)+'\')">Ver Plan</button>'
        +'<button class="btn btn-ghost btn-sm" onclick="openEditAthlete(\''+u.id+'\')">Editar</button>'
        +'<button class="btn btn-ghost btn-sm" onclick="openAddMemberFor(\''+u.id+'\')">+Grupo</button>'
        +'<button class="btn btn-danger btn-sm btn-icon" title="Eliminar atleta" onclick="deleteAthlete(\''+u.id+'\',\''+esc(u.nombre)+'\')">'
        +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg></button>'
        +'</td>'
        +'</tr>';
    }).join('');
  }catch(e){ tb.innerHTML='<tr><td colspan="6" style="color:var(--red)">Error: '+esc(e.message)+'</td></tr>'; }
}

// â”€â”€ Groups â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function loadGroups(){
  var grid=document.getElementById('groups-grid');
  grid.innerHTML='<p style="color:var(--dim)">Cargando...</p>';
  try{
    var grps = await apiGet('/coach/groups');
    _cache.groups=grps;
    if(!grps.length){ grid.innerHTML='<div class="empty"><p>Sin grupos. Crea el primero.</p></div>'; return; }
    grid.innerHTML=grps.map(function(g){
      return '<div class="card">'
        +'<div class="card-hd"><h3>'+esc(g.nombre)+'</h3>'
        +'<button class="btn btn-danger btn-sm btn-icon" title="Eliminar grupo" onclick="deleteGroup(\''+g.id+'\')">'
        +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg></button></div>'
        +(g.competencia?'<p style="font-size:.78rem;color:var(--dim);margin-bottom:.75rem">'+esc(g.competencia)+'</p>':'')
        +'<div style="font-size:.8rem;color:var(--muted);margin-bottom:.75rem">'+g.member_count+' atleta'+(g.member_count!==1?'s':'')+'</div>'
        +'<button class="btn btn-ghost btn-sm" onclick="openAddMemberGroup(\''+g.id+'\',\''+esc(g.nombre)+'\')">+ Agregar atleta</button>'
        +'</div>';
    }).join('');
  }catch(e){ grid.innerHTML='<p style="color:var(--red)">Error: '+esc(e.message)+'</p>'; }
}

window.createGroup=async function(){
  var nombre=document.getElementById('mg-nombre').value.trim();
  var comp  =document.getElementById('mg-comp').value.trim();
  if(!nombre){ toast('Nombre requerido','err'); return; }
  try{
    await apiPost('/coach/groups',{nombre:nombre,competencia:comp||null});
    closeModal('modal-group');
    document.getElementById('mg-nombre').value='';
    document.getElementById('mg-comp').value='';
    toast('Grupo creado');
    loadGroups();
  }catch(e){ toast('Error: '+e.message,'err'); }
};

window.deleteGroup=async function(id){
  if(!confirm('Eliminar este grupo y todas sus asignaciones?')) return;
  try{
    await apiDelete('/coach/groups/'+id);
    toast('Grupo eliminado');
    loadGroups();
    loadOverview();
  }catch(e){ toast('Error: '+e.message,'err'); }
};

window.openAddMemberGroup=function(gid,gname){
  _addMemberGroupId=gid;
  document.getElementById('mam-group-name').textContent=gname;
  var sel=document.getElementById('mam-athlete');
  sel.innerHTML='<option value="">Seleccionar...</option>';
  _cache.athletes.forEach(function(u){
    sel.innerHTML+='<option value="'+u.id+'">'+esc(u.nombre)+' ('+esc(u.email)+')</option>';
  });
  openModal('modal-add-member');
};

window.openAddMemberFor=function(uid){
  var sel=document.getElementById('mam-athlete');
  sel.innerHTML='<option value="">Seleccionar...</option>';
  _cache.athletes.forEach(function(u){
    sel.innerHTML+='<option value="'+u.id+(u.id===uid?' selected':'')+'">'+(u.id===uid?'* ':'')+esc(u.nombre)+' ('+esc(u.email)+')</option>';
  });
  _addMemberGroupId=null;
  // ask which group
  if(!_cache.groups.length){ toast('Sin grupos creados','err'); return; }
  _addMemberGroupId=_cache.groups[0].id;
  document.getElementById('mam-group-name').textContent=_cache.groups[0].nombre;
  document.getElementById('mam-athlete').value=uid;
  openModal('modal-add-member');
};

window.addMember=async function(){
  if(!_addMemberGroupId){ toast('Selecciona un grupo','err'); return; }
  var uid=document.getElementById('mam-athlete').value;
  if(!uid){ toast('Selecciona un atleta','err'); return; }
  try{
    await apiPost('/coach/groups/'+_addMemberGroupId+'/members',{user_id:uid});
    closeModal('modal-add-member');
    toast('Atleta agregado al grupo');
    loadGroups();
    loadOverview();
  }catch(e){ toast('Error: '+e.message,'err'); }
};

// â”€â”€ Crear atleta â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
window.createAthlete=async function(){
  var nombre     = document.getElementById('na-nombre').value.trim();
  var email      = document.getElementById('na-email').value.trim();
  var pass       = document.getElementById('na-pass').value.trim();
  var plan       = document.getElementById('na-plan').value;
  var gEmail     = document.getElementById('na-garmin-email').value.trim();
  var gPass      = document.getElementById('na-garmin-pass').value.trim();
  var groupId    = document.getElementById('na-group').value;

  if(!nombre||!email||!pass){ toast('Nombre, email y contraseÃ±a requeridos','err'); return; }

  try{
    // 1. Crear usuario atleta
    var newUser = await apiPost('/coach/athletes',{
      email: email, nombre: nombre, password: pass,
      rol: 'athlete', plan_nivel: plan
    });
    toast('Atleta '+nombre+' creado');

    // 2. Guardar credenciales Garmin si se ingresaron
    if(gEmail && gPass){
      toast('Verificando credenciales Garmin...','ok');
      try{
        // Llamamos al endpoint del atleta â€” necesitamos hacer login como el atleta
        // para guardar sus credenciales. Hacemos POST directo al admin endpoint.
        await fetch(API+'/admin/users/'+newUser.id+'/garmin',{
          method:'POST',
          headers:{'Content-Type':'application/json',Authorization:'Bearer '+getToken()},
          body: JSON.stringify({garmin_email:gEmail,garmin_password:gPass})
        }).then(function(r){
          if(!r.ok) return r.json().then(function(d){ throw new Error(d.detail||'Error'); });
          return r.json();
        });
        toast('Garmin conectado para '+nombre,'ok');
      }catch(e2){
        toast('Atleta creado, Garmin fallÃ³: '+e2.message,'err');
      }
    }

    // 3. Agregar al grupo si se seleccionÃ³
    if(groupId){
      try{
        await apiPost('/coach/groups/'+groupId+'/members',{user_id:newUser.id});
      }catch(e3){ /* grupo ya puede estar lleno o error */ }
    }

    // Limpiar modal
    ['na-nombre','na-email','na-pass','na-garmin-email','na-garmin-pass'].forEach(function(id){
      document.getElementById(id).value='';
    });
    closeModal('modal-new-athlete');
    loadAthletes();
    loadOverview();
  }catch(e){ toast('Error: '+e.message,'err'); }
};

// â”€â”€ Editar atleta â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
window.openEditAthlete = function(uid){
  var u = (_cache.athletes||[]).find(function(a){ return a.id===uid; });
  if(!u){ toast('Atleta no encontrado en cachÃ©','err'); return; }
  document.getElementById('ea-id').value          = u.id;
  document.getElementById('ea-nombre').value      = u.nombre||'';
  document.getElementById('ea-email').value       = u.email||'';
  document.getElementById('ea-plan').value        = u.plan_nivel||'basico';
  document.getElementById('ea-activo').value      = u.activo ? 'true' : 'false';
  document.getElementById('ea-pass').value        = '';
  document.getElementById('ea-garmin-email').value= u.garmin_email||'';
  document.getElementById('ea-garmin-pass').value = '';
  var gs = document.getElementById('ea-garmin-status');
  if(u.has_garmin){
    gs.innerHTML='<span style="color:var(--green)">â— Garmin conectado:</span> '+esc(u.garmin_email);
  }else{
    gs.innerHTML='<span style="color:var(--dim)">Sin Garmin configurado</span>';
  }
  openModal('modal-edit-athlete');
};

window.saveEditAthlete = async function(){
  var uid    = document.getElementById('ea-id').value;
  var nombre = document.getElementById('ea-nombre').value.trim();
  var email  = document.getElementById('ea-email').value.trim();
  var plan   = document.getElementById('ea-plan').value;
  var activo = document.getElementById('ea-activo').value === 'true';
  var pass   = document.getElementById('ea-pass').value.trim();
  var gEmail = document.getElementById('ea-garmin-email').value.trim();
  var gPass  = document.getElementById('ea-garmin-pass').value.trim();

  if(!nombre||!email){ toast('Nombre y email requeridos','err'); return; }

  try{
    // 1. Actualizar datos del usuario (email incluido)
    var patchBody = { nombre: nombre, email: email, plan_nivel: plan, activo: activo };
    if(pass) patchBody.password = pass;

    var r1 = await fetch(API+'/admin/users/'+uid,{
      method:'PATCH',
      headers:{'Content-Type':'application/json', Authorization:'Bearer '+getToken()},
      body: JSON.stringify(patchBody)
    });
    if(!r1.ok){ var d1=await r1.json(); throw new Error(d1.detail||'Error al guardar'); }

    // 2. Actualizar credenciales Garmin solo si se ingresÃ³ nueva contraseÃ±a
    if(gEmail && gPass){
      var r2 = await fetch(API+'/admin/users/'+uid+'/garmin',{
        method:'POST',
        headers:{'Content-Type':'application/json', Authorization:'Bearer '+getToken()},
        body: JSON.stringify({garmin_email:gEmail, garmin_password:gPass})
      });
      if(!r2.ok){ var d2=await r2.json(); throw new Error(d2.detail||'Error Garmin'); }
    }

    toast('Atleta actualizado correctamente','ok');
    closeModal('modal-edit-athlete');
    loadAthletes();
  }catch(e){ toast('Error: '+e.message,'err'); }
};

window.deleteAthlete = async function(uid, nombre){
  if(!confirm('Â¿Eliminar a "'+nombre+'"?\nSus asignaciones histÃ³ricas quedarÃ¡n en la BD pero el atleta no podrÃ¡ iniciar sesiÃ³n.')) return;
  try{
    var r = await fetch(API+'/admin/users/'+uid,{
      method:'DELETE',
      headers:{Authorization:'Bearer '+getToken()}
    });
    if(!r.ok && r.status!==204){ var d=await r.json(); throw new Error(d.detail||'Error'); }
    toast('Atleta "'+nombre+'" eliminado','ok');
    loadAthletes();
  }catch(e){ toast('Error: '+e.message,'err'); }
};

window.deleteAthleteFromModal = function(){
  var uid    = document.getElementById('ea-id').value;
  var nombre = document.getElementById('ea-nombre').value.trim();
  closeModal('modal-edit-athlete');
  deleteAthlete(uid, nombre);
};

// Poblar grupos en el modal de nuevo atleta
function populateGroupsInAthleteModal(){
  var sel = document.getElementById('na-group');
  if(!sel) return;
  sel.innerHTML='<option value="">Sin grupo por ahora</option>';
  _cache.groups.forEach(function(g){
    sel.innerHTML+='<option value="'+g.id+'">'+esc(g.nombre)+'</option>';
  });
}

// â”€â”€ Workouts â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function loadWorkouts(){
  var tb=document.getElementById('workouts-tbody');
  tb.innerHTML='<tr><td colspan="6" style="text-align:center;color:var(--dim)">Cargando...</td></tr>';
  try{
    var wkts = await apiGet('/coach/workouts');
    _cache.workouts=wkts;
    if(!wkts.length){ tb.innerHTML='<tr><td colspan="6" style="text-align:center;color:var(--dim)">Sin templates</td></tr>'; return; }
    tb.innerHTML=wkts.map(function(w){
      return '<tr>'
        +'<td><strong>'+esc(w.nombre)+'</strong>'+(w.notas?'<div style="font-size:.72rem;color:var(--dim)">'+esc(w.notas.slice(0,50))+'</div>':'')+'</td>'
        +'<td><span class="sport-chip '+sportCls(w.sport)+'">'+sportLabel(w.sport)+'</span></td>'
        +'<td>'+(w.dur_min?w.dur_min+' min':'â€”')+'</td>'
        +'<td>'+(w.dist_km?w.dist_km+' km':'â€”')+'</td>'
        +'<td>'+(w.tss?w.tss:'â€”')+'</td>'
        +'<td><button class="btn btn-danger btn-sm btn-icon" onclick="deleteWorkout(\''+w.id+'\')" title="Eliminar">'
        +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/></svg></button></td>'
        +'</tr>';
    }).join('');
  }catch(e){ tb.innerHTML='<tr><td colspan="6" style="color:var(--red)">Error</td></tr>'; }
}

window.createWorkout=async function(){
  var nombre=document.getElementById('mw-nombre').value.trim();
  var sport =document.getElementById('mw-sport').value;
  var dur   =parseInt(document.getElementById('mw-dur').value)||null;
  var dist  =parseFloat(document.getElementById('mw-dist').value)||null;
  var tss   =parseInt(document.getElementById('mw-tss').value)||null;
  var notas =document.getElementById('mw-notas').value.trim()||null;
  if(!nombre){ toast('Nombre requerido','err'); return; }
  try{
    await apiPost('/coach/workouts',{sport:sport,nombre:nombre,dur_min:dur,dist_km:dist,tss:tss,notas:notas});
    closeModal('modal-workout');
    ['mw-nombre','mw-dur','mw-dist','mw-tss','mw-notas'].forEach(function(id){ document.getElementById(id).value=''; });
    toast('Template creado');
    loadWorkouts();
    loadOverview();
  }catch(e){ toast('Error: '+e.message,'err'); }
};

window.deleteWorkout=async function(id){
  if(!confirm('Eliminar este template?')) return;
  try{
    await apiDelete('/coach/workouts/'+id);
    toast('Template eliminado');
    loadWorkouts();
    loadOverview();
  }catch(e){ toast('Error: '+e.message,'err'); }
};

// â”€â”€ Assign â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function loadAssignTab(){
  var tSel=document.getElementById('asgn-template');
  tSel.innerHTML='<option value="">Seleccionar template...</option>';
  _cache.workouts.forEach(function(w){
    tSel.innerHTML+='<option value="'+w.id+'">'+esc(sportLabel(w.sport)+' â€” '+w.nombre)+'</option>';
  });

  var aSel=document.getElementById('asgn-athlete');
  aSel.innerHTML='<option value="">Seleccionar atleta...</option>';
  _cache.athletes.forEach(function(u){
    aSel.innerHTML+='<option value="'+u.id+'">'+esc(u.nombre)+'</option>';
  });

  var gSel=document.getElementById('asgn-group');
  gSel.innerHTML='<option value="">Seleccionar grupo...</option>';
  _cache.groups.forEach(function(g){
    gSel.innerHTML+='<option value="'+g.id+'">'+esc(g.nombre)+'</option>';
  });

  // default date = today
  if(!document.getElementById('asgn-date').value){
    document.getElementById('asgn-date').value=todayISO();
  }

  loadRecentAssigns();
}

async function loadRecentAssigns(){
  var el=document.getElementById('recent-assigns');
  try{
    var today=todayISO();
    var from =addDays(today,-7);
    var asn = await apiGet('/coach/assignments?start='+from+'&end='+addDays(today,30));
    _cache.assigns=asn;
    if(!asn.length){ el.innerHTML='<div class="empty"><p>Sin asignaciones</p></div>'; return; }
    el.innerHTML=asn.slice(0,15).map(function(a){
      var ath=_cache.athletes.find(function(x){return x.id===a.athlete_id;});
      var hasGarmin = ath && ath.has_garmin;
      var garminBtn = hasGarmin
        ? '<button class="btn btn-ghost btn-sm" style="font-size:.68rem;padding:.2rem .5rem;color:var(--green);border-color:rgba(16,185,129,.3)" title="Enviar a Garmin de '+esc(ath?ath.nombre:'atleta')+'" onclick="syncToGarmin(\''+a.id+'\',\''+esc(a.template.nombre)+'\',\''+esc(ath?ath.nombre:'')+'\')">Garmin</button>'
        : '<span style="font-size:.68rem;color:var(--dim)" title="Atleta sin Garmin configurado">sin Garmin</span>';
      var delBtn='<button class="btn btn-danger btn-sm btn-icon" title="Eliminar asignaciÃ³n" onclick="deleteAssign(\''+a.id+'\')" style="padding:.2rem .35rem">'
        +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:13px;height:13px"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/></svg></button>';
      return '<div style="display:flex;gap:.5rem;align-items:center;padding:.45rem 0;border-bottom:1px solid var(--border2)">'
        +'<span class="sport-chip '+sportCls(a.template.sport)+'">'+sportIcon(a.template.sport)+'</span>'
        +'<div style="flex:1;font-size:.8rem"><strong>'+esc(a.template.nombre)+'</strong>'
        +(ath?'<div style="color:var(--dim);font-size:.7rem">'+esc(ath.nombre)+' Â· '+a.date_iso+'</div>':'<div style="color:var(--dim);font-size:.7rem">'+a.date_iso+'</div>')+'</div>'
        +garminBtn+' '+delBtn
        +'</div>';
    }).join('');
  }catch(e){ el.innerHTML='<div class="empty"><p>Sin asignaciones</p></div>'; }
}

window.toggleAsgnTarget=function(){
  var v=document.getElementById('asgn-target-type').value;
  document.getElementById('asgn-athlete-field').style.display = v==='athlete'?'':'none';
  document.getElementById('asgn-group-field').style.display   = v==='group'?'':'none';
};

window.submitAssign=async function(){
  var tpl      = document.getElementById('asgn-template').value;
  var date     = document.getElementById('asgn-date').value;
  var type     = document.getElementById('asgn-target-type').value;
  var notes    = document.getElementById('asgn-notes').value.trim()||null;
  var syncGarmin = document.getElementById('asgn-sync-garmin').checked;
  if(!tpl||!date){ toast('Template y fecha requeridos','err'); return; }
  var body={template_id:tpl,date_iso:date,notas:notes};
  if(type==='athlete'){
    var uid=document.getElementById('asgn-athlete').value;
    if(!uid){ toast('Selecciona un atleta','err'); return; }
    body.athlete_id=uid;
  }else{
    var gid=document.getElementById('asgn-group').value;
    if(!gid){ toast('Selecciona un grupo','err'); return; }
    body.group_id=gid;
  }
  try{
    var assigned = await apiPost('/coach/assign',body);
    toast('Entrenamiento asignado');
    document.getElementById('asgn-notes').value='';

    // Si pidiÃ³ sync Garmin, disparar inmediatamente
    if(syncGarmin && assigned && assigned.id){
      toast('Enviando a Garmin...','ok');
      try{
        var syncRes = await apiPost('/coach/assign/'+assigned.id+'/sync-garmin',{});
        if(syncRes.ok){
          toast('Asignado y enviado a Garmin Connect','ok');
        } else {
          toast('Asignado. Garmin: '+(syncRes.error||'sin respuesta'),'err');
        }
      }catch(e2){ toast('Asignado. Garmin fallÃ³: '+e2.message,'err'); }
    }

    loadRecentAssigns();
  }catch(e){ toast('Error: '+e.message,'err'); }
};

// Sync manual de una asignaciÃ³n existente al Garmin del atleta
window.syncToGarmin=async function(assignId, workoutName, athleteName){
  toast('Enviando "'+workoutName+'" a Garmin de '+athleteName+'...','ok');
  try{
    var res = await apiPost('/coach/assign/'+assignId+'/sync-garmin',{});
    var body = document.getElementById('garmin-result-body');
    if(res.ok){
      body.innerHTML = '<div style="color:var(--green);font-size:1.1rem;margin-bottom:.75rem">Enviado correctamente</div>'
        +'<div style="color:var(--muted)"><strong>Atleta:</strong> '+esc(athleteName)+'</div>'
        +'<div style="color:var(--muted)"><strong>Workout:</strong> '+esc(workoutName)+'</div>'
        +'<div style="color:var(--muted)"><strong>Fecha:</strong> '+esc(res.date||'')+'</div>'
        +'<div style="color:var(--dim);font-size:.78rem;margin-top:.5rem">Workout ID Garmin: '+esc(res.workout_id||'')+'</div>';
    }else{
      body.innerHTML = '<div style="color:var(--red);margin-bottom:.5rem">Error al sincronizar</div>'
        +'<div style="color:var(--dim);font-size:.8rem">'+esc(res.error||'Error desconocido')+'</div>';
    }
    openModal('modal-garmin-result');
  }catch(e){ toast('Error Garmin: '+e.message,'err'); }
};

// â”€â”€ Adherence â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function loadAdherenceFilters(){
  var gSel=document.getElementById('adh-group-filter');
  gSel.innerHTML='<option value="">Todos</option>';
  _cache.groups.forEach(function(g){
    gSel.innerHTML+='<option value="'+g.id+'">'+esc(g.nombre)+'</option>';
  });
  // default last 30 days
  var t=todayISO();
  if(!document.getElementById('adh-start').value) document.getElementById('adh-start').value=addDays(t,-30);
  if(!document.getElementById('adh-end').value)   document.getElementById('adh-end').value=t;
}

window.loadAdherence=async function(){
  var start =document.getElementById('adh-start').value;
  var end   =document.getElementById('adh-end').value;
  var gid   =document.getElementById('adh-group-filter').value;
  if(!start||!end){ toast('Selecciona perÃ­odo','err'); return; }
  var tb=document.getElementById('adh-tbody');
  tb.innerHTML='<tr><td colspan="5" style="text-align:center;color:var(--dim)">Cargando...</td></tr>';
  try{
    var url='/coach/adherence?start='+start+'&end='+end+(gid?'&group_id='+gid:'');
    var data = await apiGet(url);
    if(!data.length){ tb.innerHTML='<tr><td colspan="5" style="text-align:center;color:var(--dim)">Sin datos para el perÃ­odo</td></tr>'; return; }
    tb.innerHTML=data.map(function(a){
      var pct=a.pct;
      var cls=pct>=90?'badge-green':pct>=60?'badge-gold':'badge-red';
      var fc=pct>=90?'var(--green)':pct>=60?'var(--gold)':'var(--red)';
      var sports=Object.entries(a.by_sport).map(function(kv){
        var s=kv[0]; var v=kv[1];
        return '<span title="'+sportLabel(s)+': '+v.pct+'%" class="sport-chip '+sportCls(s)+'" style="margin-right:.2rem">'+sportIcon(s)+' '+Math.round(v.pct)+'%</span>';
      }).join('');
      return '<tr>'
        +'<td><strong>'+esc(a.nombre)+'</strong><div style="font-size:.7rem;color:var(--dim)">'+esc(a.email)+'</div></td>'
        +'<td>'+a.total+'</td>'
        +'<td>'+a.completado+'</td>'
        +'<td><span class="badge '+cls+'">'+Math.round(pct)+'%</span>'
        +'<div class="adh-bar-wrap" style="margin-top:.3rem"><div class="adh-bar-bg"><div class="adh-bar-fill" style="width:'+Math.min(pct,100)+'%;background:'+fc+'"></div></div></div></td>'
        +'<td>'+sports+'</td>'
        +'</tr>';
    }).join('');
  }catch(e){ tb.innerHTML='<tr><td colspan="5" style="color:var(--red)">Error: '+esc(e.message)+'</td></tr>'; }
};

// â”€â”€ Mi Plan (cuenta atleta vinculada) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function initMiAtletaTab(){
  var email = localStorage.getItem('lx_ath_email');
  if(email){
    document.getElementById('ath-linked-email').textContent = email;
    document.getElementById('ath-linked-info').style.display = '';
    document.getElementById('ath-link-form').style.display   = 'none';
    loadMyPlan();
  }else{
    document.getElementById('ath-linked-info').style.display = 'none';
    document.getElementById('ath-link-form').style.display   = '';
    document.getElementById('my-plan-list').innerHTML = '<div class="empty"><p>Vincula tu cuenta de atleta para ver tu plan</p></div>';
  }
}

window.linkAthleteAccount = async function(){
  var email = document.getElementById('ath-email').value.trim();
  var pass  = document.getElementById('ath-pass').value.trim();
  if(!email||!pass){ toast('Email y contraseÃ±a requeridos','err'); return; }
  try{
    var r = await fetch(API+'/auth/login',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({email:email,password:pass})
    });
    if(!r.ok){ toast('Credenciales invÃ¡lidas','err'); return; }
    var data = await r.json();
    localStorage.setItem('lx_ath_token', data.access_token);
    localStorage.setItem('lx_ath_email', email);
    localStorage.setItem('lx_ath_nombre', data.nombre);
    toast('Cuenta de atleta "'+data.nombre+'" vinculada','ok');
    initMiAtletaTab();
  }catch(e){ toast('Error al vincular: '+e.message,'err'); }
};

window.unlinkAthleteAccount = function(){
  localStorage.removeItem('lx_ath_token');
  localStorage.removeItem('lx_ath_email');
  localStorage.removeItem('lx_ath_nombre');
  initMiAtletaTab();
  toast('Cuenta de atleta desvinculada');
};

window.loadMyPlan = async function(){
  var athToken = localStorage.getItem('lx_ath_token');
  if(!athToken){ initMiAtletaTab(); return; }
  var el = document.getElementById('my-plan-list');
  el.innerHTML = '<div style="text-align:center;color:var(--dim);padding:1rem">Cargando...</div>';
  try{
    var today = todayISO();
    var end   = addDays(today, 30);
    var r = await fetch(API+'/athlete/plan?start='+today+'&end='+end,{
      headers:{Authorization:'Bearer '+athToken}
    });
    if(r.status===401){
      localStorage.removeItem('lx_ath_token');
      localStorage.removeItem('lx_ath_email');
      localStorage.removeItem('lx_ath_nombre');
      el.innerHTML = '<div class="empty"><p>SesiÃ³n expirada. Vuelve a vincular tu cuenta.</p></div>';
      initMiAtletaTab(); return;
    }
    var plan = await r.json();
    if(!plan||!plan.length){
      el.innerHTML = '<div class="empty"><p>Sin entrenamientos asignados para los prÃ³ximos 30 dÃ­as</p></div>'; return;
    }
    el.innerHTML = plan.map(function(a){
      var t = a.template;
      return '<div style="display:flex;align-items:center;gap:.75rem;padding:.65rem 0;border-bottom:1px solid var(--border)">'
        +'<div style="font-weight:600;min-width:90px;font-size:.85rem">'+a.date_iso+'</div>'
        +'<span class="sport-chip '+sportCls(t.sport)+'">'+sportIcon(t.sport)+' '+sportLabel(t.sport)+'</span>'
        +'<div style="flex:1"><strong>'+esc(t.nombre)+'</strong>'
        +(t.dist_km?'<span style="color:var(--muted);font-size:.78rem;margin-left:.5rem">'+t.dist_km+' km</span>':'')
        +(t.dur_min?'<span style="color:var(--muted);font-size:.78rem;margin-left:.5rem">'+t.dur_min+' min</span>':'')
        +(a.notas?'<div style="font-size:.75rem;color:var(--dim)">'+esc(a.notas)+'</div>':'')+'</div>'
        +'</div>';
    }).join('');
  }catch(e){ el.innerHTML = '<div class="empty"><p style="color:var(--red)">Error: '+esc(e.message)+'</p></div>'; }
};

// â”€â”€ Ver plan de atleta â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
var _apAthleteId = null;

window.openAthletePlan = function(uid, nombre){
  _apAthleteId = uid;
  document.getElementById('ap-title').textContent = 'Plan de '+nombre;
  var today = todayISO();
  document.getElementById('ap-start').value = addDays(today,-14);
  document.getElementById('ap-end').value   = addDays(today, 60);
  openModal('modal-athlete-plan');
  loadAthletePlan();
};

window.loadAthletePlan = async function(){
  if(!_apAthleteId) return;
  var start = document.getElementById('ap-start').value;
  var end   = document.getElementById('ap-end').value;
  var el    = document.getElementById('ap-list');
  el.innerHTML = '<div style="text-align:center;color:var(--dim);padding:1rem">Cargando...</div>';
  try{
    var url = '/coach/assignments/athlete/'+_apAthleteId+(start||end?'?':'')+(start?'start='+start:'')+(start&&end?'&':'')+(end?'end='+end:'');
    var plan = await apiGet(url);
    if(!plan||!plan.length){
      el.innerHTML='<div class="empty"><p>Sin asignaciones en este perÃ­odo</p></div>'; return;
    }
    el.innerHTML = plan.map(function(a){
      var past = a.date_iso < todayISO();
      var rowStyle = past ? 'opacity:.65;' : '';
      return '<div style="display:flex;gap:.6rem;align-items:center;padding:.5rem 0;border-bottom:1px solid var(--border2);'+rowStyle+'">'
        +'<div style="min-width:88px;font-size:.78rem;font-weight:600;color:'+(past?'var(--dim)':'var(--text)')+'">'+a.date_iso+'</div>'
        +'<span class="sport-chip '+sportCls(a.template.sport)+'">'+sportIcon(a.template.sport)+' '+sportLabel(a.template.sport)+'</span>'
        +'<div style="flex:1;font-size:.82rem">'
        +'<strong>'+esc(a.template.nombre)+'</strong>'
        +(a.template.dist_km?'<span style="color:var(--muted);font-size:.72rem;margin-left:.4rem">'+a.template.dist_km+' km</span>':'')
        +(a.template.dur_min?'<span style="color:var(--muted);font-size:.72rem;margin-left:.4rem">'+a.template.dur_min+' min</span>':'')
        +(a.notas?'<div style="font-size:.7rem;color:var(--dim)">'+esc(a.notas)+'</div>':'')
        +'</div>'
        +'<button class="btn btn-danger btn-sm btn-icon" title="Eliminar" onclick="deleteAssignFromPlan(\''+a.id+'\')" style="padding:.2rem .35rem">'
        +'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:13px;height:13px"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/></svg></button>'
        +'</div>';
    }).join('');
  }catch(e){ el.innerHTML='<div class="empty"><p style="color:var(--red)">Error: '+esc(e.message)+'</p></div>'; }
};

window.deleteAssignFromPlan = async function(assignId){
  if(!confirm('Â¿Eliminar esta asignaciÃ³n?')) return;
  try{
    var r = await fetch(API+'/coach/assignments/'+assignId,{
      method:'DELETE', headers:{Authorization:'Bearer '+getToken()}
    });
    if(!r.ok && r.status!==204){ var d=await r.json(); throw new Error(d.detail||'Error'); }
    toast('AsignaciÃ³n eliminada','ok');
    loadAthletePlan();
    loadRecentAssigns();
  }catch(e){ toast('Error: '+e.message,'err'); }
};

window.deleteAssign = async function(assignId){
  if(!confirm('Â¿Eliminar esta asignaciÃ³n?')) return;
  try{
    var r = await fetch(API+'/coach/assignments/'+assignId,{
      method:'DELETE', headers:{Authorization:'Bearer '+getToken()}
    });
    if(!r.ok && r.status!==204){ var d=await r.json(); throw new Error(d.detail||'Error'); }
    toast('AsignaciÃ³n eliminada','ok');
    loadRecentAssigns();
  }catch(e){ toast('Error: '+e.message,'err'); }
};

// â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function esc(s){ if(s==null)return''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function todayISO(){ return new Date().toISOString().slice(0,10); }
function addDays(iso,n){ var d=new Date(iso+'T00:00:00'); d.setDate(d.getDate()+n); return d.toISOString().slice(0,10); }
function sportCls(s){ return {swim:'sp-swim',bike:'sp-bike',run:'sp-run',str:'sp-str'}[s]||''; }
function sportIcon(s){ return {swim:'ðŸŠ',bike:'ðŸš´',run:'ðŸƒ',str:'ðŸ’ª'}[s]||'ðŸ‹'; }
function sportLabel(s){ return {swim:'Nado',bike:'Bici',run:'Carrera',str:'Fuerza'}[s]||s; }
function planBadge(p){ var m={basico:'badge-dim',pro:'badge-cyan',elite:'badge-gold'}; return '<span class="badge '+(m[p]||'badge-dim')+'">'+p+'</span>'; }

// â”€â”€ Boot â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
window.addEventListener('load', init);

})();

