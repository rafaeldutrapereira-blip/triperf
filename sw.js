/**
 * LabX Service Worker â€” offline cache + background sync + GPS tracker
 * IMPORTANTE: Incrementar BUILD_VERSION en cada deploy para forzar
 * que los usuarios reciban la versiÃ³n actualizada (invalida cache viejo).
 */
var BUILD_VERSION = '346';  // TEMA-CLARO-FIX contraste del tema claro en las bandas 2 y 3 del Dashboard (semaforos ACWR/VO2/readiness/mental/semana por variables --ok/--warn/--bad/--cyan/--orange/--faint, color-mix en vez de sufijo hex; sparklines por style; tema oscuro identico). Anterior 345: MIPLAN-INTEGRA la franja semanal S3 (bienestar por dia + metricas Carga/Fitness/Forma/Fatiga/Ramp) se integra al resumen de entrada de Mi Plan y sale de Ver mas (que queda solo con herramientas). Anterior 344: DASHBOARD-EJECUTIVO dashboard en tres preguntas (Como estoy hoy / Como esta mi carga / Para donde voy) con tarjetas uniformes, sin eliminar indicadores; sistema de tema global OSCURO por defecto + selector CLARO en el menu (variables en theme-vars.css, labx_theme en localStorage, aplicado antes del primer pintado; nav.css?v=8, nav.js?v=10); regla de siglas: nombre + (sigla). Anterior 343: MIPLAN-RESUMEN Mi Plan resumen primero estilo intervals (cabecera de semana + linea ejecutiva N sesiones / Xh planificadas / M hechas, dias en mini-tarjetas, semanas siguientes colapsadas; Cumplimiento semanal retirado y metas fijas TARGETS eliminadas). Anterior 342: INSIGHT-SIMPLE Insight del dia simple por defecto (severidad en palabra, titular grande, una linea de accion = ultimo bullet; drivers, bullets completos y lista tecnica tras 'Ver por que'). Anterior 341: CARRERAS-DASHBOARD franja ejecutiva de carreras del ano en el Dashboard (proxima en grande, resto del ano compacto; fuente unica GET /athlete/races, sin kl_next_race). Anterior 340: CARRERAS-PERFIL Mis carreras del ano en el perfil (lista editable sobre RaceEvent, principal unica y prioridad A/B/C; GET/POST/PATCH/DELETE /athlete/races). Anterior 339: TARJETA-VERDAD la tarjeta Garmin solo cree en has_credentials, no en la fila de sync (la escribe tambien intervals.icu). Anterior 338: SHELL-1 cascara unica, menu cargado una sola vez. Anterior 337: 2026-11-07: MENUBAR-3 geometria unica del shell (232px solo en nav.css; coach.html sin copia local del menu, 220px fuera de detalle/indoor/style), sin slideUp en Mi Plan, menu sin barra de scroll y con scroll conservado entre paginas (nav.css?v=6, nav.js?v=8). Anterior 336: 2026-11-07: SYNC-HONESTO sync_state/data_until en garmin sync-status; tarjeta, banner S-C y franja de reloj dicen la verdad (conexion caida + "Datos hasta"). Anterior 335: MENUBAR-2 menu ejecutivo estilo intervals (232px, filas 36px sin mayusculas, activo pastilla, marca estatica tambien en movil) y fuentes locales sin swap (fonts.css + vendor/fonts, font-display optional). Anterior 334: 2026-11-06: RETIRO-1 conexion Garmin por contrasena cerrada (410 salvo GARMIN_LEGACY_CONNECT_ENABLED=1; sin formulario en perfil ni onboarding) e interruptor GARMIN_LEGACY_SYNC_ENABLED. Anterior 333: 2026-11-06: MENUBAR sidebar fijo y estable (marca estatica, sin transform/transition all, alturas fijas, .sb-user reserva espacio; nav.css?v=4, nav.js?v=7). Anterior 332: 2026-11-06: Mi Plan no duplica la copia Garmin de una sesion del plan propio (dedupe W17 en /athlete/planned-workouts, solo vista). Anterior 331: 2026-11-06: M4 planes compartibles por link de solo lectura (share_token en training_plans; POST/DELETE /coach/plans/{id}/share, GET /public/plans/{token}, POST /plans/shared/{token}/copy; pagina shared_plan.html). Anterior 330: 2026-11-06: M3 Rendimiento: resumen compara el periodo con el anterior equivalente (GET /analytics/summary?compare=true; deltas absoluto y % calculados en backend; 'sin datos previos' si no hay). Anterior 329: 2026-11-06: M2 check-in subjetivo (energia, animo, dolor muscular, estres 1-5) en el Dashboard; GET/POST /athlete/health/checkin; syncs no tocan esas columnas. Anterior 328: 2026-11-06: M1 FTP Indoor (rodillo) separado en el constructor Indoor (users.ftp_indoor; vacio = FTP principal). Anterior 327: 2026-11-06: A4 checklist 'Primeros pasos' en el Dashboard (GET /onboarding/status con 4 pasos calculados de datos reales; descarte local). Anterior 326: 2026-11-06: A3 preview 'Impacto proyectado' (CTL/ATL/TSB) al aplicar semana tipo / macrociclo en Coach (POST preview-impact, solo lectura; Chart.js vendorizado en coach.html). Anterior 325: 2026-11-06: S-D Conexiones: 'Ver detalles' por tarjeta (Garmin, Polar, Wahoo, Strava: recibe/envia, ultima sync real, Sincronizar ahora/Reconectar; status Polar/Wahoo expone last_sync_at). Anterior 324: 2026-11-06: S-C Conexiones: banner de migracion a Garmin oficial (solo legacy sin oficial; descarte en localStorage). Anterior 323: 2026-11-06: S-B Conexiones: paso 'Trae tu historial' (intervals.icu backfill + Strava 90d; descarte/hecho en localStorage). Anterior 322: 2026-11-06: Sprint 3 franja semanal en Mi Plan (wellness + hecho + plan + PMC). Anterior 321: 2026-11-06: S-A Conexiones: una sola tarjeta Garmin (oficial por OAuth; credenciales solo admin; 'Cambiar a la conexion oficial' si hay legacy). Anterior 320: 2026-11-06: lectura intervals.icu (scopes, sync actividades/wellness tras flag INTERVALS_READ_ENABLED; sello Indoor honesto 'Enviado a intervals.icu'; fecha larga en Mis Workouts). Anterior 319: 2026-11-05: Sprint 56 paso 3 tarjetas Polar/Wahoo en Conexiones (perfil web + app), gateadas por /providers/enabled; sync inicial 90d tras el OAuth. Anterior 318: 2026-11-04: CQ15 ruta vendor de Leaflet normalizada (vendor/leaflet/leaflet.css|js + images/, sin carpeta doble). Anterior 317:CQ10b/D3 Leaflet 1.9.4 y Chart.js 4.4.4 vendorizados (vendor/, sin CDN en la app; precacheados). Anterior 315: CQ13 importacion del plan local por usuario (marca kl_own_plan_migrated:<id>; solo si el plan local es de esa cuenta); lx-ownplan.js?v=2. Anterior 314: 2026-11-04: CQ11 sellos unicos workout-blocks.js?v=4 y estado-checkin.js?v=1 en web y app (precache alineado). Anterior 312: CQ8 la pelota de Hoy igual a la web (arco proporcional al semaforo, rotulo MENTAL/RECUPERACION + secundario, etiqueta/frase/chip de carrera en el idioma activo; tarjeta Insight del Dashboard con la pelota; helper lx-estado-ball.js). Anterior 310: 2026-11-04: CQ7 Mi Plan propio vive en el servidor (GET/POST/PUT/DELETE /athlete/own-plan, helper lx-ownplan.js, migracion unica desde localStorage, Indoor + Mi Plan escribe en servidor). Anterior 309: CQ6 limpieza menor (docstring/mojibake plan_builder, recovery_score 0 valido, CTL objetivo sugerido). Anterior 308: CQ5 VO2max rotula lecturas estimadas vs Garmin (leyenda y marcadores en Rendimiento) y PMC con la misma cifra de hoy en Rendimiento, Dashboard y Detalle. Antes: 2026-11-04: CQ4 Readiness una sola superficie visible (sin chip en dash-header ni fila en auditoria; Garmin Training Readiness y Recovery Score rotulados como metricas distintas; sin /readiness/history ni /today-plan). Antes: 2026-11-04: CQ3 TSS unico y real (helper lx-tss.js compartido por dashboard, Mi Plan y Detalle; null sin FTP/FCmax/FC, fuerza sin RPE sin TSS, sin 240/180/50 por hora). Antes: 2026-11-04: CQ2 cero botones y cifras falsas (sin Enviar a Garmin falso en Mi Plan, mockup landing ilustrativo con TSB -14, grafico semanal de Nutricion sin semillas, nav.js sin syncGarmin muerto ?v=6, Race Day sin readiness_score). Antes: 2026-11-04: CQ1 readiness calculo honesto (DRS null sin datos, bandas unicas del backend). Antes: GARMIN integracion oficial OAuth2+webhook (backend). Antes:DASHFIX el dashboard muestra la etiqueta del objetivo (70.3 / Half (113 km)) y no el codigo crudo + km. Antes: 2026-11-04: RECORDS se elimina la seccion Mis records del Perfil web (Rendimiento unica fuente). Antes:2026-11-04: SEXO campo sexo en el Perfil de la app (valores f/m como la web). Antes: 2026-11-04: D2 i18n final de la app podada (Recovery Score y etiqueta Recovery por i18n, subtitulo de Progreso sin "tu año"). Antes: 2026-11-04: D1 poda: se borran Asistente IA, Huella, _wlData, _NGROK_BYPASS y menuGo de la app. Antes:2026-11-04: C3 Race Day en 1 vista (cuenta regresiva + objetivos + Ver plan completo en la web); se retiran Plan por tramos y Nutricion de la app. Antes: 2026-11-04: C2 Mas de 5 filas (tarjeta proxima carrera, sin Equipo) y Perfil ordenado (sin Salir duplicado, enlace a la web). Antes:2026-11-04: C1 Progreso en 3 chips (Forma, Records, Potencia/VO2); se retiran Proyeccion, Distribucion y Zonas de la app y el wpMob se recorta. Antes: 2026-11-04: B4 Plan = sesion + tira de 7 dias con el plan real (include_garmin) y el realizado con Adicionales; sin anillos; Progreso Semanal (wpMob) se muda a Progreso. Antes: P2 Recovery = detalle de 1 vista desde Hoy (sin pestanas ni fila en Mas, enlace a la web). Antes:B3 check-in en hoja unica de 9 campos (estado-checkin.js) en Hoy, sin check-ins viejos de Recovery/Mental. Antes:B2 Hoy nuevo (semaforo unico de estado-hoy, sesion del plan real, chip de carrera; sin tiras de metricas, sparklines, detalle por indicador ni recomendacion duplicada); previo: 2026-11-04: P0 puente app->web (handoff de un solo uso, abrirEnWeb, banner en Mas, contador por destino); previo: 2026-11-03: W21 Mi Plan muestra el realizado completo (actividades Adicionales, GET /athlete/plan/realizado); previo:2026-11-03: W20 Blood Labs sube examenes PDF/foto con lectura IA, borrador editable y confirmacion; previo: 2026-11-03: W19 Entrenador suma natacion (bloques reps x distancia, push a intervals.icu como Swim); previo: 2026-11-03: W17 el plan del dia suma el plan de Garmin (GET /athlete/plan?include_garmin=1, dedupe y done con evidencia); previo: 2026-11-03: W16 sube el sello de routes.config.js a ?v=11 (W4 cambio su contenido sin subir el sello; el archivo es immutable 1 ano); previo: 2026-11-03: CC4 la web monta community.js en community.html (casca fina; sin Desafios/Descubrir/panel de perfil propios); previo: 2026-11-03: CC3 la app monta community.js en screen-community (Feed, Ranking, Clubes; sin Descubrir ni Mi Perfil, modo lectura Free); previo: 2026-11-03: CC2 modulo unico community.js (Feed, Ranking, Clubes; aun sin montar, precacheado con ?v=1); previo: 2026-11-03: A2 Estado y Dashboard consumen el veredicto unico GET /athlete/estado-hoy (sin fusion local); previo: 2026-11-02: W14 nicho (Blood Labs llano con descargo y registro en 2 pasos, Adaptativos vista unica Esta semana para el atleta, Comunidad con 2 selectores y feed primero, Gear Bicicletas con invitacion a subir de plan); previo: 2026-11-02: W13 portada en tres piezas (Dashboard: frase de hoy, carrera en dias, Que toca hoy con Mi Plan; Estado: 2 grupos de 4 y check-in que se pliega; Perfil: 3 pestanas); previo: 2026-11-02: W12 retiro de GPS Tracker y codigo muerto (cuerpos de atleta de mental/recovery, drawer de carreras del dashboard); previo:2026-11-02: W10 Integridad: sin cifras/IA/rol/defaults falsos (landing, login, registro, dashboard eTSS, onboarding con error de guardado, comunidad en tuteo y plan Basico); previo: 2026-11-02: W9 Detalle: KPIs en capas (3 cifras + Ver mas datos), 2 graficos por defecto + Mas graficos, sin badge duplicado; previo: 2026-11-02: W8 Nutricion directa (3 KPIs, Gasto semanal al final, Intensidad en 2 capas); previo: 2026-11-02: W7 Rendimiento: tarjeta Carga nativa (sin iframe), pestanas 6 a 4 (Mas analisis agrupa Records, Distribucion y Zonas), selector de rango dentro de sus pestanas, sin fila de 3 cifras duplicada; previo: 2026-11-02: W6 Race Day en una sola pantalla (2 pestanas, plan en un boton, Ajustes avanzados plegados, sin pestana Nutricion); previo: 2026-11-02: W5 Detalle: heroe en lenguaje llano (titular + una cifra, siglas en capa 2), PMC sin Progreso Semanal ni Otras metricas, Comparar Ciclos plegado, periodos 7 a 4; previo:2026-11-02: W11 campo sexo (Blood Labs sin rangos masculinos por defecto, aviso y Beta) + medidor de perfil completo; previo: 2026-11-02: W4 Mi Huella oculta para todos los roles (canAccess respeta disabled antes del bypass); previo: 2026-11-02: W3 Race Day: Registrar Resultado envia race_id, errores HTTP visibles y TSB 0 valido; previo: 2026-11-02: W2 sin semillas ni metas genericas (nutricion, detalle, race_day); previo: 2026-11-02: S28 Estado de hoy: check-in unico de 9 campos para Recuperacion y Mental; previo: 2026-11-02: S27 barrido i18n de los textos dinamicos de Nutricion (ES/PT/EN); previo: 2026-11-02: S25 restaura la página completa de Nutrición desde el historial (simulador, gráficos y detalle por hora) sobre la shell actual; previo: 2026-11-02: S23-F Rendimiento abre con resumen ejecutivo que respeta el rango elegido; previo: S23-B analytics/summary acepta days_back (solo backend); previo: S22 Detalle: Progreso solo en metricas de carga, hero con valor actual + promedio del periodo, periodo por defecto 90 dias; previo: 2026-11-02: S21 Rendimiento: selector de rango coherente (Zonas lo respeta; Records y Carga avisan), init sobrio y pestañas con deep-link por hash; previo: 2026-11-02: S20 Rendimiento: identidad unica (titulo Rendimiento/Performance/Desempenho) e idioma P11 completo en analytics (W/kg, CP, W' con info; textos JS traducidos; _t definida); previo: 2026-11-02: S19 Nutricion: estados explicitos (cargando, sin datos, error con Reintentar) en la tarjeta de Race Day; previo: 2026-11-01: S18 Mi Plan: saca el título "Mi Plan" del encabezado de la página; previo: 2026-11-01: S17 Mi Plan: saca el resumen de semana, las cifras y los botones Agregar Sesión / Garmin Sync del encabezado; previo: 2026-11-01: S16 unifica el sello de routes.config.js; previo: S13  // 2026-11-01: S13 corte a Estado de hoy (menu unico; recovery/mental redirigen, excepto recovery ?view=coach); previo: 2026-11-01: S12 pagina unica Estado de hoy (estado.html fusiona Recuperacion y Mental); previo: 2026-11-01: S11 Indoor simple: plantillas, editor visual, sincronizacion automatica al guardar y menu Exportar; previo: 2026-11-01: S14 Ajustes Adaptativos como aviso ocasional; sale la seccion incrustada de Mi Plan; previo: 2026-11-01: S10 Mi Plan liviana (sesiones primero) + Progreso Semanal se muda a Rendimiento; previo: 2026-11-01: S6 envio de workouts al reloj via intervals.icu; previo: 2026-11-01: S5 Indoor multideporte v1 (running con bloques por ritmo y FC); previo: 2026-11-01: S4 workouts de Indoor persistidos en backend (CRUD + migracion desde localStorage); previo: 2026-11-01: S3 registro de sesion en un gesto (Hecha) en Mi Plan; previo: 2026-11-01: S2 Mi Plan con encabezado propio y resumen de la semana; previo: 2026-11-01: S1 AI Coach fuera del frente para atletas; previo: 2026-11-01: coach y pantallas de entrenamiento con nombres completos en primera mencion (P11-F2)
var CACHE_NAME = 'lxapp-v' + BUILD_VERSION;

var PRECACHE = [
  '/athlete-app.html',
  '/lx-info.js',
  '/lx-tss.js?v=1',
  '/lx-ownplan.js?v=2',
  '/lx-estado-ball.js?v=1',
  '/estado-checkin.js?v=1',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png',
  '/nav.js',
  '/fonts.css',
  '/vendor/fonts/inter-400.woff2',
  '/vendor/fonts/inter-500.woff2',
  '/vendor/fonts/inter-600.woff2',
  '/vendor/fonts/oswald-500.woff2',
  '/vendor/fonts/oswald-600.woff2',
  '/vendor/fonts/barlow-condensed-700.woff2',
  '/vendor/fonts/barlow-condensed-800.woff2',
  '/login.html',
  '/dashboard.html',
  '/shell.html',
  '/analytics.html',
  '/training_plan.html',
  '/auth.js',
  '/i18n.js',
  '/community.js?v=1',
  '/community.html',
  '/recovery.html',
  '/nutrition.html',
  '/adaptive.html',
  '/mental.html',
  '/estado.html',
  '/ai_coach.html',
  '/gear.html',
  '/web-handoff.html',
  '/vendor/leaflet/leaflet.css',
  '/vendor/leaflet/leaflet.js',
  '/vendor/leaflet/images/layers.png',
  '/vendor/leaflet/images/layers-2x.png',
  '/vendor/leaflet/images/marker-icon.png',
  '/vendor/leaflet/images/marker-icon-2x.png',
  '/vendor/leaflet/images/marker-shadow.png',
  '/vendor/chart.umd.min.js',
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
