# REPORT-418 — ENDURECIMIENTO (H6 + A4 + A5 + A6), BUILD 418

Solo local: commit en main, sin push, sin deploy, sin migraciones.

## ACCIÓN REQUERIDA ANTES DEL DEPLOY (Rafael)

Poner en el `.env` del servidor:

- **`GARMIN_NOTIFY_SECRET`** — obligatoria. Sin ella `/api/integrations/garmin/notify` responde 404 (fail-closed) y **el push real de Garmin deja de entrar**.
  - Registrar en el portal de Garmin la URL con el secreto en la ruta: `https://labxperformanceapp.com/api/integrations/garmin/notify/<GARMIN_NOTIFY_SECRET>` (Garmin no permite cabeceras propias). También se acepta la cabecera `X-Garmin-Notify-Secret`.
  - Orden seguro: poner la variable → reiniciar → cambiar la URL en Garmin. Entre el deploy y el cambio de URL, los push llegan sin secreto y se rechazan (401); Garmin reintenta.
- Opcionales: `GARMIN_NOTIFY_ALLOWED_IPS` (IP/CIDR de Garmin separadas por coma; vacía = no se filtra por IP), `GARMIN_PUSH_MAX_ROWS` (def. 50000), `GARMIN_PUSH_MAX_ORPHAN_ROWS` (def. 2000).
- `METRICS_SECRET` (ya existía para `/metrics`) ahora también protege `/api/metrics`.

## Cambios

- **H6** (`api/routes/garmin_official_routes.py`, `api/garmin_ingest.py`): secreto por ruta o cabecera (comparación en tiempo constante, leído solo del entorno); lista de IP opcional usando `ip_from_request` (CF-Connecting-IP, nunca XFF); tope del cuerpo real (413, antes solo se miraba Content-Length); tope de filas total y de filas sin usuario (excedido = se descarta con log y 200 a Garmin); `purge_unattributed` borra filas sin usuario de más de 7 días al final de cada `process_pending`. El ingest no se tocó más allá de eso.
- **A4** (`api/account_deletion.py`, `api/routes/public_routes.py`): `request_deletion` pone `share_token=NULL` en `training_plans` (coach_id) y `garmin_activities` (user_id); `/public/activities` y `/public/plans` dan 404 si el dueño está inactivo.
- **A5** (`api/coach_main.py`, `deploy/smoke_test.sh`): `/api/metrics` exige loopback o `Bearer METRICS_SECRET` (404 sin secreto configurado, 401 con uno malo), igual que `/metrics`; `/health` ya no devuelve `version` ni `env`. Monitoreo: el deploy (`deploy.yml`) y el CI usan solo `/health` y leen `status` (sigue presente); `smoke_test.sh` esperaba 200 en `/api/metrics`, ahora espera 401/404. Nada en el repo consume `/api/metrics` con auth. Los tests que exigían `version` en `/health` (`test_training_load.py`, `e2e/test_04`) se invirtieron.
- **A6** (`api/mailer.py`): `html.escape` de nombre, IP, dispositivo, ubicación y etiqueta de equipo en bienvenida, drips, alerta de login y alerta de gear; `_geolocate_ip` valida con `ipaddress` antes de armar la URL (IP no válida = sin consulta). La validación de nombre al guardar es `clean_display_name` (H1-XSS); no se duplicó, el escape del correo es defensa en profundidad. Asuntos de correo (texto plano) no se escapan.
- `sw.js` BUILD 418 + changelog; espejos móviles regenerados (`build_www.py` + `node node_modules/@capacitor/cli/bin/capacitor sync`).

## Evidencia de tests

- Nuevos: `api/tests/test_endurecimiento.py` — 14 pasan (sin secreto/mal secreto/cabecera/ruta, lista de IP y XFF ignorado, tope total y de huérfanas, 413, retención, borrado→404 en plan y actividad, dueño inactivo, `/api/metrics` 404/401/200, `/health` recortado, escape en 5 correos, validación de IP).
- Ajustes a tests existentes: `test_garmin_official.py` (fixture autouse que manda el secreto), `test_garmin_ingest.py::test_user_none_writes_nothing` (fila con fecha reciente: la fecha fija T0 ya tiene >7 días y la retención la borraría), `test_training_load.py` (health).
- Suite completa `pytest api`: 3806 passed, 1 skipped, 3 failed en la corrida completa. Uno era mío (`test_user_none_writes_nothing`, corregido arriba y ahora pasa); **2 preexistentes**, confirmados con `git stash` sobre HEAD limpio: `test_calendario_vivo_375.py::test_c_evento_borrado_en_origen_desaparece` y `::test_c2_pasado_se_conserva_y_fallo_no_borra` (eventos de intervals no se borran). No se tocaron. Tras el último ajuste no se repitió la suite completa; se re-corrieron los archivos afectados (`test_garmin_ingest`, `test_endurecimiento`, `test_garmin_official`).

## Honestidad del alcance

- **Push real de Garmin no verificado contra Garmin ni producción**: solo con tests contra el endpoint. Hay que registrar la URL con secreto en el portal de Garmin y comprobar la primera entrega tras el deploy (el sistema no puede probarlo desde aquí).
- **No inventé rangos de IP de Garmin**: no hay lista oficial en el repo; `GARMIN_NOTIFY_ALLOWED_IPS` queda vacía por defecto (solo secreto). Si Rafael obtiene los rangos de Garmin, se activa sin cambio de código. El filtro asume que el origen solo es alcanzable vía Cloudflare Tunnel.
- El secreto en la ruta puede quedar en logs de acceso de Cloudflare/proxy.
- A4: se anulan los tokens de planes (como coach) y actividades; los enlaces de informe (`/public/reports`) no se tocaron (ya dan 404 al cerrarse la relación coach-atleta). Los planes cuyo coach se borró ya no se pueden recuperar por token: es intencional.
- El tope de filas descarta datos legítimos de Garmin si se alcanza (log de aviso); 50000 filas es holgado para la base actual.
- `/health` sigue siendo público (necesario para deploy/CI) pero sin versión ni entorno.
