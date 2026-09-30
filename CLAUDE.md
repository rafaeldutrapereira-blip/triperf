# LabX — Contexto del proyecto

LabX es una plataforma de coaching y análisis de rendimiento para triatletas/corredores/ciclistas (Garmin/Strava), con panel de atleta, panel de coach, y app móvil (Capacitor). Este archivo es la fuente de verdad que debe leer **cualquier sesión de Claude Code que abra este repo** (celular, PC, nube) — reemplaza la necesidad de compartir memoria personal entre dispositivos. Se actualiza cada vez que cambia algo estructural importante.

## Regla de oro: un solo proyecto, sin duplicidad

- **GitHub (`rafaeldutrapereira-blip/triperf`, rama `main`) es la única fuente de verdad del código.** Antes de empezar a trabajar desde cualquier dispositivo: `git pull`. Al terminar: commitear y `git push`. Nunca dejar trabajo sin subir de un dispositivo antes de trabajar desde otro — eso es lo que causa forks silenciosos (ya pasó una vez: 439 commits locales sin subir mientras GitHub quedó 5 meses atrás, corregido 2026-09-30).
- **Este archivo (`CLAUDE.md`) es la memoria compartida entre dispositivos.** La memoria personal de Claude (`~/.claude/.../memory/`) vive solo en la PC de Rafael y no es accesible desde sesiones cloud/celular — por eso cualquier decisión o gotcha importante debe terminar reflejado acá, no solo en esa memoria.
- **Toda sesión que termine un cambio debe:** (1) commitear con mensaje descriptivo, (2) hacer push, (3) si el cambio es arquitectónico o revela un patrón de bug nuevo, actualizar este archivo en el mismo commit.

## Stack y arquitectura

- **Backend:** FastAPI + SQLAlchemy + Alembic + SQLite (`api/coach_main.py` es el entrypoint real). JWT en cookies HttpOnly (`lx_co_token` es la cookie real — páginas que leen `lx_token` o `kl_s.token` están usando claves que NO existen y van a fallar con 401 silencioso).
- **Frontend:** HTML/JS estático servido por el mismo backend, sin build step para la web. Sidebar de navegación estándar vía `nav.js` + `routes.config.js` (cache-busting importante — bump de versión en el query string cuando se toca).
- **App móvil:** Capacitor. Build real con `scripts/build_www.py` (nunca copiar archivos a mano al directorio `www/`). El entry point real es `index.html`, no `athlete-app.html`. Dominio real: **labxperformanceapp.com** (no existe `beta.labx.app`).
- **PWA / Service Worker:** `sw.js`, cache-first para estáticos. Cada deploy que toque un archivo precacheado **debe** incrementar `BUILD_VERSION` en `sw.js`, si no los usuarios quedan con versión vieja indefinidamente (hay que cerrar la PWA por completo, no minimizar, para forzar la actualización del Service Worker).
- **Backend envelope de error:** `{ok:false, errors:[{message}]}`, NO el `{detail}` default de FastAPI — el frontend espera ese formato.

## Infraestructura (desde 2026-09-27)

El backend corre en un servidor cloud, **no en la PC de Rafael** — ver [[project-labx-server-migration]] en memoria para el detalle completo.

- VM: `labx-server`, GCP, zona `us-west1-b`, IP `34.145.118.232`, e2-micro (Always Free — gratis mientras se mantenga ese tipo de máquina, esa región, y disco "Standard").
- `labx.service` (systemd, `Restart=always`, arranca solo en boot) corre uvicorn en el puerto 8000.
- `cloudflared.service` (systemd) expone el mismo túnel de Cloudflare que ya apuntaba a `labxperformanceapp.com` — no hubo que tocar DNS.
- **Rollback si el VM falla:** en la PC de Rafael siguen instalados (no borrados) `scripts/run_backend_forever.ps1` y `scripts/run_cloudflared_forever.ps1` — relanzarlos vuelve a servir desde ahí, Cloudflare Tunnel soporta réplicas simultáneas del mismo túnel.
- Acceso SSH: `deploy/keys/gcp_labx` (gitignored, nunca commitear), usuario `labx-deploy`.

## Patrones de bug recurrentes (evitar repetir)

- **Campos de modelo inexistentes:** varias veces se escribió código asumiendo campos que no existen en `GarminActivity`/`TrainingLoad`/`RaceEvent` — verificar el modelo real en `api/models.py` antes de asumir un nombre de campo.
- **Topes hardcodeados silenciosos:** ACWR y otros cálculos han tenido límites de ventana hardcodeados (ej. 120 días) que se olvidan y limitan el análisis sin avisar — buscar constantes mágicas antes de confiar en un cálculo "raro".
- **Mojibake:** nunca tipear caracteres corruptos a mano para arreglarlos; usar `chr(codepoint)` y verificar con Read el resultado real.
- **TSS con FC fija:** hubo un bug de meses calculando TSS con FC máxima fija (190) en vez de la real del atleta — si un TSS se ve raro, revisar qué fórmula/constante está usando.
- **RepeatGroupDTO:** el TSS planificado ignoraba series repetidas anidadas (bug real, corregido, pero el patrón de "estructuras anidadas no recorridas completas" puede repetirse en otros DTOs similares).
- **Device fingerprint:** nunca usar IP para identidad de dispositivo — cambia constantemente en redes móviles.

## Decisiones de producto pendientes (no ejecutar sin confirmar con Rafael)

- Marcar/ocultar Coach view, Blood Labs, Race Day como "beta" cuando están vacíos — decisión de producto, no fix de código.
- Postura sobre Garmin OAuth vs. credenciales de usuario — Garmin no ofrece OAuth de consumidor para devs independientes; migrar es negociación comercial, no un sprint.
- Plan multi-marca (Wahoo/Polar/Coros/Apple Health) — auditoría hecha, sprints 48-55 diseñados, no iniciados.

## Detalle histórico completo

El detalle sprint-por-sprint (más de 90 entradas) vive en la memoria personal de Claude en la PC de Rafael, no en este archivo — este archivo es un resumen vivo, no un changelog. Para historia completa de una feature específica, preguntar en la sesión de la PC.
