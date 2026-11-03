/**
 * LabX Service Worker â€” offline cache + background sync + GPS tracker
 * IMPORTANTE: Incrementar BUILD_VERSION en cada deploy para forzar
 * que los usuarios reciban la versiÃ³n actualizada (invalida cache viejo).
 */
var BUILD_VERSION = '277';  // 2026-11-02: W14 nicho (Blood Labs llano con descargo y registro en 2 pasos, Adaptativos vista unica Esta semana para el atleta, Comunidad con 2 selectores y feed primero, Gear Bicicletas con invitacion a subir de plan); previo: 2026-11-02: W13 portada en tres piezas (Dashboard: frase de hoy, carrera en dias, Que toca hoy con Mi Plan; Estado: 2 grupos de 4 y check-in que se pliega; Perfil: 3 pestanas); previo: 2026-11-02: W12 retiro de GPS Tracker y codigo muerto (cuerpos de atleta de mental/recovery, drawer de carreras del dashboard); previo:2026-11-02: W10 Integridad: sin cifras/IA/rol/defaults falsos (landing, login, registro, dashboard eTSS, onboarding con error de guardado, comunidad en tuteo y plan Basico); previo: 2026-11-02: W9 Detalle: KPIs en capas (3 cifras + Ver mas datos), 2 graficos por defecto + Mas graficos, sin badge duplicado; previo: 2026-11-02: W8 Nutricion directa (3 KPIs, Gasto semanal al final, Intensidad en 2 capas); previo: 2026-11-02: W7 Rendimiento: tarjeta Carga nativa (sin iframe), pestanas 6 a 4 (Mas analisis agrupa Records, Distribucion y Zonas), selector de rango dentro de sus pestanas, sin fila de 3 cifras duplicada; previo: 2026-11-02: W6 Race Day en una sola pantalla (2 pestanas, plan en un boton, Ajustes avanzados plegados, sin pestana Nutricion); previo: 2026-11-02: W5 Detalle: heroe en lenguaje llano (titular + una cifra, siglas en capa 2), PMC sin Progreso Semanal ni Otras metricas, Comparar Ciclos plegado, periodos 7 a 4; previo:2026-11-02: W11 campo sexo (Blood Labs sin rangos masculinos por defecto, aviso y Beta) + medidor de perfil completo; previo: 2026-11-02: W4 Mi Huella oculta para todos los roles (canAccess respeta disabled antes del bypass); previo: 2026-11-02: W3 Race Day: Registrar Resultado envia race_id, errores HTTP visibles y TSB 0 valido; previo: 2026-11-02: W2 sin semillas ni metas genericas (nutricion, detalle, race_day); previo: 2026-11-02: S28 Estado de hoy: check-in unico de 9 campos para Recuperacion y Mental; previo: 2026-11-02: S27 barrido i18n de los textos dinamicos de Nutricion (ES/PT/EN); previo: 2026-11-02: S25 restaura la página completa de Nutrición desde el historial (simulador, gráficos y detalle por hora) sobre la shell actual; previo: 2026-11-02: S23-F Rendimiento abre con resumen ejecutivo que respeta el rango elegido; previo: S23-B analytics/summary acepta days_back (solo backend); previo: S22 Detalle: Progreso solo en metricas de carga, hero con valor actual + promedio del periodo, periodo por defecto 90 dias; previo: 2026-11-02: S21 Rendimiento: selector de rango coherente (Zonas lo respeta; Records y Carga avisan), init sobrio y pestañas con deep-link por hash; previo: 2026-11-02: S20 Rendimiento: identidad unica (titulo Rendimiento/Performance/Desempenho) e idioma P11 completo en analytics (W/kg, CP, W' con info; textos JS traducidos; _t definida); previo: 2026-11-02: S19 Nutricion: estados explicitos (cargando, sin datos, error con Reintentar) en la tarjeta de Race Day; previo: 2026-11-01: S18 Mi Plan: saca el título "Mi Plan" del encabezado de la página; previo: 2026-11-01: S17 Mi Plan: saca el resumen de semana, las cifras y los botones Agregar Sesión / Garmin Sync del encabezado; previo: 2026-11-01: S16 unifica routes.config.js?v=10; previo: S13  // 2026-11-01: S13 corte a Estado de hoy (menu unico; recovery/mental redirigen, excepto recovery ?view=coach); previo: 2026-11-01: S12 pagina unica Estado de hoy (estado.html fusiona Recuperacion y Mental); previo: 2026-11-01: S11 Indoor simple: plantillas, editor visual, sincronizacion automatica al guardar y menu Exportar; previo: 2026-11-01: S14 Ajustes Adaptativos como aviso ocasional; sale la seccion incrustada de Mi Plan; previo: 2026-11-01: S10 Mi Plan liviana (sesiones primero) + Progreso Semanal se muda a Rendimiento; previo: 2026-11-01: S6 envio de workouts al reloj via intervals.icu; previo: 2026-11-01: S5 Indoor multideporte v1 (running con bloques por ritmo y FC); previo: 2026-11-01: S4 workouts de Indoor persistidos en backend (CRUD + migracion desde localStorage); previo: 2026-11-01: S3 registro de sesion en un gesto (Hecha) en Mi Plan; previo: 2026-11-01: S2 Mi Plan con encabezado propio y resumen de la semana; previo: 2026-11-01: S1 AI Coach fuera del frente para atletas; previo: 2026-11-01: coach y pantallas de entrenamiento con nombres completos en primera mencion (P11-F2)
var CACHE_NAME = 'lxapp-v' + BUILD_VERSION;

var PRECACHE = [
  '/athlete-app.html',
  '/lx-info.js',
  '/estado-checkin.js',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png',
  '/nav.js',
  '/login.html',
  '/dashboard.html',
  '/analytics.html',
  '/training_plan.html',
  '/auth.js',
  '/i18n.js',
  '/community.html',
  '/recovery.html',
  '/nutrition.html',
  '/adaptive.html',
  '/mental.html',
  '/estado.html',
  '/ai_coach.html',
  '/gear.html',
];

/* â”€â”€ Install: pre-cache archivos estÃ¡ticos â”€â”€ */
self.addEventListener('install', function(e){
  e.waitUntil(
    caches.open(CACHE_NAME).then(function(cache){
      return cache.addAll(PRECACHE);
    }).then(function(){ return self.skipWaiting(); })
  );
});

/* â”€â”€ Activate: limpiar caches viejos â”€â”€ */
self.addEventListener('activate', function(e){
  e.waitUntil(
    caches.keys().then(function(keys){
      return Promise.all(
        keys.filter(function(k){ return k !== CACHE_NAME; })
            .map(function(k){ return caches.delete(k); })
      );
    }).then(function(){ return self.clients.claim(); })
  );
});

/*
 * Mientras el backend se sirve por un tunel ngrok gratuito (fase de
 * pruebas, no produccion): ngrok le muestra a cualquier request con cara
 * de navegador (sin este header) una pagina HTML de advertencia en vez
 * de proxyear al servidor real, con status 200 -- fetch() no lo detecta
 * como error, solo devuelve HTML donde se esperaba JSON. Un telefono
 * real nunca manda este header por su cuenta, asi que el Service Worker
 * se lo agrega a todo lo que reenvia a la red. Bug real encontrado en
 * vivo: "Sin conexion -- plan no disponible" apareciendo siempre, desde
 * que ngrok empezo a mostrar esta interstitial. Inofensivo contra un
 * dominio real (el header se ignora), no hace falta sacarlo despues.
 */
function _withNgrokBypass(req){
  var headers = new Headers(req.headers);
  headers.set('ngrok-skip-browser-warning', 'true');
  return new Request(req, {headers: headers});
}

/* â”€â”€ Fetch: cache-first para estÃ¡ticos, network-first para API â”€â”€ */
self.addEventListener('fetch', function(e){
  // Defensivo: new URL() puede tirar SyntaxError en Safari/WebKit ("The
  // string did not match the expected pattern") si e.request.url viniera
  // malformada por cualquier motivo -- sin este try/catch, ESE error
  // rompía el fetch completo (login incluido) sin ningún log ni forma
  // de diagnosticarlo desde el servidor, porque nunca llegaba a la red.
  var url;
  try{ url = new URL(e.request.url); }
  catch(err){ return; } // deja pasar el request sin intervenir (comportamiento default del browser)

  // API calls: siempre red, sin cache
  if(url.pathname.startsWith('/api')){
    e.respondWith(
      fetch(_withNgrokBypass(e.request)).catch(function(){
        return new Response(JSON.stringify({error:'offline'}),
          {status:503, headers:{'Content-Type':'application/json'}});
      })
    );
    return;
  }

  // Archivos estÃ¡ticos: cache-first
  e.respondWith(
    caches.match(e.request).then(function(cached){
      if(cached) return cached;
      return fetch(_withNgrokBypass(e.request)).then(function(response){
        if(!response || response.status !== 200 || response.type !== 'basic') return response;
        var clone = response.clone();
        caches.open(CACHE_NAME).then(function(cache){ cache.put(e.request, clone); });
        return response;
      }).catch(function(){
        // Fallback offline: devuelve athlete-app.html para cualquier navegaciÃ³n
        if(e.request.mode === 'navigate'){
          return caches.match('/athlete-app.html');
        }
      });
    })
  );
});

/* â”€â”€ Push notifications (cuando el coach asigna entreno) â”€â”€ */
self.addEventListener('push', function(e){
  var data = e.data ? e.data.json() : {};
  var title = data.title || 'LabX';
  var body  = data.body  || 'Tienes una notificaciÃ³n nueva';
  var icon  = '/icon-192.png';
  e.waitUntil(
    self.registration.showNotification(title, {
      body: body,
      icon: icon,
      badge: icon,
      tag: 'lxapp',
      data: data,
      actions: [
        { action: 'view', title: 'Ver entrenamiento' },
        { action: 'dismiss', title: 'Cerrar' }
      ]
    })
  );
});

self.addEventListener('notificationclick', function(e){
  e.notification.close();
  var data = e.notification.data || {};
  var url = data.url || (data.type === 'community' ? '/community.html' : '/athlete-app.html');
  if(e.action === 'view' || !e.action){
    e.waitUntil(
      clients.matchAll({type:'window', includeUncontrolled:true}).then(function(cls){
        for(var i=0;i<cls.length;i++){
          if(cls[i].url.includes(self.location.origin)){
            cls[i].focus(); cls[i].navigate(url); return;
          }
        }
        return clients.openWindow(url);
      })
    );
  }
});

/* â”€â”€ Background Sync â€” D-05: encolar workouts GPS cuando offline â”€â”€ */
self.addEventListener('sync', function(e){
  if(e.tag === 'sync-workouts'){
    e.waitUntil(syncPendingWorkouts());
  }
});

/*
 * BP-10 FIX: El Service Worker NO puede leer HttpOnly cookies (por diseÃ±o de seguridad).
 * SoluciÃ³n: usar credentials:'include' â€” el browser adjunta la cookie automÃ¡ticamente.
 * Ya no se necesita getAuthToken() con IndexedDB; la cookie lx_access_token se envía sola.
 */
function syncPendingWorkouts(){
  return openIDB().then(function(db){
    return getAllPending(db).then(function(items){
      if(!items.length) return;
      return Promise.allSettled(items.map(function(item){
        return fetch('/api/athlete/workout-log',{
          method:'POST',
          credentials: 'include',  /* BP-10: cookie HttpOnly se adjunta automÃ¡ticamente */
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({
            sport:    item.data.sport,
            dur_min:  item.data.dur_min,
            dist_km:  item.data.dist_km,
            date_iso: (item.data.recorded_at||new Date().toISOString()).slice(0,10),
            notas:    'GPS Tracker (offline sync) â€” '+item.data.dist_km+' km',
            tss:      Math.round((item.data.dur_min||0)*0.8),
          })
        }).then(function(r){
          if(r.ok) return deleteItem(db, item.key);
          /* Si 401 â†’ sesiÃ³n expirada; no reintentar; item permanece en queue */
          if(r.status === 401) return;
          /* Otros errores â†’ reintentar en prÃ³ximo sync */
        }).catch(function(){});
      }));
    });
  }).catch(function(){});
}

function openIDB(){
  return new Promise(function(resolve,reject){
    var req = indexedDB.open('labx-offline',1);
    req.onupgradeneeded = function(e){
      var db = e.target.result;
      if(!db.objectStoreNames.contains('pending_workouts'))
        db.createObjectStore('pending_workouts',{autoIncrement:true});
      if(!db.objectStoreNames.contains('auth'))
        db.createObjectStore('auth',{keyPath:'id'});
    };
    req.onsuccess = function(e){ resolve(e.target.result); };
    req.onerror   = function(e){ reject(e); };
  });
}

function getAllPending(db){
  return new Promise(function(resolve){
    var items=[], tx=db.transaction('pending_workouts','readonly');
    var cur=tx.objectStore('pending_workouts').openCursor();
    cur.onsuccess=function(e){
      var c=e.target.result;
      if(c){ items.push({key:c.key,data:c.value}); c.continue(); }
      else resolve(items);
    };
    cur.onerror=function(){ resolve([]); };
  });
}

function deleteItem(db,key){
  return new Promise(function(resolve){
    var tx=db.transaction('pending_workouts','readwrite');
    tx.objectStore('pending_workouts').delete(key);
    tx.oncomplete=resolve;
  });
}

function getAuthToken(db){
  return new Promise(function(resolve){
    try{
      var req=db.transaction('auth','readonly').objectStore('auth').get('session');
      req.onsuccess=function(e){ resolve(e.target.result?e.target.result.token:null); };
      req.onerror=function(){ resolve(null); };
    }catch(e){ resolve(null); }
  });
}
