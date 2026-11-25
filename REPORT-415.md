# REPORT-415 — H3-H2-LIMITES (IP confiable + contador 2FA tras ambos factores)

Solo local: commit en `main`, sin push, sin deploy, sin migraciones.

## Qué cambió

- `api/audit.py` `ip_from_request`: ya NO lee `X-Forwarded-For`. Devuelve `CF-Connecting-IP` si está presente y es una IP válida; si no, la IP de la conexión directa (`request.client.host`).
- `api/routes/auth_routes.py` (solo el contador de `/auth/login`):
  - `_clear_attempts(ip)` se movió del punto posterior a la contraseña al final del flujo: solo se ejecuta tras pasar contraseña y, si hay 2FA, también TOTP o backup code. La respuesta `needs_2fa` (contraseña correcta, sin código) ya no limpia nada.
  - Nuevo límite por `user_id` (`_check_user_limit`, `_record_failed("user:<id>")`, `_clear_user_attempts`): cada fallo de segundo factor (TOTP o backup code) suma un intento al bucket del usuario; con 10 en la ventana de 1 h, `/auth/login` responde 429 aunque cambie la IP o el código sea correcto. El bucket se borra solo con login completo. Se mantiene el límite por IP.
  - Se reutiliza la tabla `login_attempts` con la clave `user:<id>` en la columna `ip`, así que no hay migración y funciona sobre la capa de BD, la única viva en producción (Redis caído, `labx_redis_up 0`). El límite por usuario no usa Redis.
- `sw.js` BUILD_VERSION 414 → 415 con línea de changelog. Espejos móviles regenerados (`scripts/build_www.py` + `node node_modules/@capacitor/cli/bin/capacitor sync`).
- Tests nuevos: `api/tests/test_h3_h2_limites.py` (11).

Umbrales numéricos: sin cambios (10 intentos / 3600 s; registro 5; reset 3).

## Suposición sobre Cloudflare / WAF (no verificable desde el repo)

- Se confía en `CF-Connecting-IP` porque Cloudflare lo fija con la IP real del cliente que llegó al borde y sobrescribe el valor que envíe el cliente. Esto presupone que el origen (uvicorn en la VM, puerto 8000) solo es alcanzable vía Cloudflare Tunnel (`cloudflared`).
- El código no puede distinguir un proxy de confianza de un cliente directo. Si el puerto 8000 de la VM fuera accesible directamente desde Internet (regla de firewall GCP), un atacante podría falsificar `CF-Connecting-IP` y esquivar el límite por IP. Las reglas de firewall de GCP y las reglas WAF de Cloudflare están fuera del repo y NO se verificaron. Acción recomendada para Rafael: confirmar que el puerto 8000 no está expuesto públicamente.
- No se aplicó la variante «último valor de XFF»: sin lista de proxies de confianza en el código es menos fiable que `CF-Connecting-IP`. Sin proxy y sin ese header, se usa la IP de la conexión directa. Si uvicorn corre con `--proxy-headers` y confía en el peer (por defecto solo 127.0.0.1), puede reescribir `request.client.host` desde XFF; eso depende de la unidad systemd (no está en el repo) y no se verificó.

## Alcance honesto / límites residuales

- El bucket por usuario cuenta solo fallos del segundo factor (con la contraseña ya correcta). Los fallos de contraseña NO se cuentan por usuario, a propósito: contarlos permitiría a cualquiera bloquear a una víctima conociendo solo su email. Un ataque de contraseña desde muchas IPs reales distintas sigue limitado solo por el tope por IP (ahora ya no falsificable por header).
- Un usuario con 2FA queda bloqueado 1 h tras 10 fallos de 2FA, incluso con el código correcto (comportamiento buscado).
- Los backup codes siguen siendo SHA-256 sin sal (fuera de alcance); quedan cubiertos por el mismo contador.
- Registro y forgot-password no se tocaron más allá de heredar la IP confiable.
- Los limitadores por IP de otros módulos que usen `ip_from_request` también heredan el cambio (auditoría, logout, GDPR).

## Evidencia de tests

- `api/tests/test_h3_h2_limites.py`: 11 passed (XFF ignorado; CF-Connecting-IP respetado y su valor inválido ignorado; XFF distinto por petición alcanza 429 al 11.º; TOTP erróneo no se borra con peticiones siguientes; límite por `user_id` con IP cambiante, incluso con TOTP correcto; backup code inválido cuenta; login completo limpia contadores; login sin 2FA, registro y forgot-password siguen funcionando).
- Suite completa (`pytest api -q -x`): 3771 passed, 1 skipped, 0 failed, 0 errors (28 min). Sin fallos preexistentes. Incluye los archivos sin versionar `test_zz_*` del árbol de trabajo.
