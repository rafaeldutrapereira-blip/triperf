/**
 * LabX Service Worker â€” offline cache + background sync + GPS tracker
 * IMPORTANTE: Incrementar BUILD_VERSION en cada deploy para forzar
 * que los usuarios reciban la versiÃ³n actualizada (invalida cache viejo).
 */
var BUILD_VERSION = '88';  // 2026-08-14: guía Hoy alineada al estándar de dashboard.html — orden, sparklines e "i" info en las 3 KPI cards
var CACHE_NAME = 'lxapp-v' + BUILD_VERSION;

var PRECACHE = [
  '/athlete-app.html',
  '/lx-info.js',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png',
  '/gps_tracker.html',
  '/nav.js',
  '/login.html',
  '/dashboard.html',
  '/year_in_review.html',
  '/analytics.html',
  '/training_plan.html',
  '/auth.js',
  '/i18n.js',
  '/community.html',
  '/recovery.html',
  '/nutrition.html',
  '/adaptive.html',
  '/mental.html',
  '/ai_coach.html',
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
  var url = new URL(e.request.url);

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
