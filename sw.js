/**
 * LabX Service Worker — offline cache + background sync
 */
var CACHE_NAME = 'lxapp-v1';

var PRECACHE = [
  '/athlete-app.html',
  '/lx-info.js',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png',
];

/* ── Install: pre-cache archivos estáticos ── */
self.addEventListener('install', function(e){
  e.waitUntil(
    caches.open(CACHE_NAME).then(function(cache){
      return cache.addAll(PRECACHE.filter(function(url){
        return !url.endsWith('.png'); // íconos opcionales
      }));
    }).then(function(){ return self.skipWaiting(); })
  );
});

/* ── Activate: limpiar caches viejos ── */
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

/* ── Fetch: cache-first para estáticos, network-first para API ── */
self.addEventListener('fetch', function(e){
  var url = new URL(e.request.url);

  // API calls: siempre red, sin cache
  if(url.pathname.startsWith('/api')){
    e.respondWith(
      fetch(e.request).catch(function(){
        return new Response(JSON.stringify({error:'offline'}),
          {status:503, headers:{'Content-Type':'application/json'}});
      })
    );
    return;
  }

  // Archivos estáticos: cache-first
  e.respondWith(
    caches.match(e.request).then(function(cached){
      if(cached) return cached;
      return fetch(e.request).then(function(response){
        if(!response || response.status !== 200 || response.type !== 'basic') return response;
        var clone = response.clone();
        caches.open(CACHE_NAME).then(function(cache){ cache.put(e.request, clone); });
        return response;
      }).catch(function(){
        // Fallback offline: devuelve athlete-app.html para cualquier navegación
        if(e.request.mode === 'navigate'){
          return caches.match('/athlete-app.html');
        }
      });
    })
  );
});

/* ── Push notifications (cuando el coach asigna entreno) ── */
self.addEventListener('push', function(e){
  var data = e.data ? e.data.json() : {};
  var title = data.title || 'LabX';
  var body  = data.body  || 'Tienes una notificación nueva';
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
  if(e.action === 'view' || !e.action){
    e.waitUntil(clients.openWindow('/athlete-app.html'));
  }
});
