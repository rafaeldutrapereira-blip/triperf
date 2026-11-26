# REPORT-416 — H5-H4-INVITACION-OAUTH (BUILD 416)

## Qué cambió
**H5 — reclamo de invitación con verificación por correo** (`api/routes/auth_routes.py`, `api/schemas.py`, `registro.html`)
- `POST /auth/register` sobre un email con `pending_invite` ya NO fija contraseña, activa la cuenta ni pasa vínculos a `active` por sí solo. Sin `claim_token` válido: envía un enlace de un solo uso al correo invitado (24 h) y responde `202 {code: invite_verification_sent}` sin token de sesión.
- Con `claim_token` válido (del usuario invitado, sin usar, no expirado) se reclama como antes y el token se quema.
- Anti-spam: no se reenvía si hay un token emitido hace <1 min. El 409 «email ya registrado» sigue solo para cuentas ya reclamadas/reales.
- `registro.html` precarga el email desde `?claim=…&email=…`, reenvía `claim_token` y muestra el mensaje ante el 202.

**H4 — state OAuth aleatorio de un solo uso** (`api/routes/intervals_routes.py`, `api/routes/strava_routes.py`)
- Se reutilizan `provider_oauth.create_state/consume_state` (aleatorio + firma HMAC, hash en BD, TTL 10 min, borrado al consumir). Providers: `intervals`, `intervals_profile` (conserva el destino `ret=profile`; el `ret` ya no viaja en el state), `strava`.
- El callback rechaza (400) state desconocido, reutilizado, expirado, de otro proveedor o el viejo `base64({"uid":…})`.
- Rama «denied/error» de intervals: consume el state solo para recuperar el destino de retorno; sin state válido usa el destino histórico.

## Migración
**Ninguna.** El token de reclamo reutiliza la tabla existente `password_reset_tokens` (`PasswordResetToken`; hash SHA-256, expiración, `used_at`) y el state reutiliza `provider_oauth_states` (`ProviderOAuthState`, `provider` es String(20): «intervals_profile» cabe). No se creó archivo Alembic.

## Evidencia
- `api/tests/test_h5_h4_invitacion_oauth.py` (nuevo, 11 tests): reclamo sin verificar rechazado (cuenta intacta), token inventado/expirado/de otro usuario rechazado, con enlace activa vínculos y es de un solo uso, 409 solo para email registrado, sin reenvío <1 min; state forjado, reutilizado, expirado y de otro proveedor rechazados en intervals; Strava forjado/feliz/reutilizado.
- `test_fuente_unica_376.py` adaptado al nuevo state (los flujos felices de intervals siguen verdes).
- Nuevos + fuente_unica: 36 passed.
- Suite completa: 3779 passed, 2 failed (preexistentes, abajo), 1 skipped (29 min).
- Fallos preexistentes (también fallan sin mis cambios, verificado con `git stash`): `test_calendario_vivo_375.py::test_c_evento_borrado_en_origen_desaparece` y `::test_c2_pasado_se_conserva_y_fallo_no_borra`.

## Alcance y honestidad
- No se tocó Garmin/Polar/Wahoo, community/search, el resto del flujo de invitaciones ni el mailer (el HTML del correo nuevo usa `quote()` en la URL; el escape general de correos es la pila ENDURECIMIENTO).
- El token de reclamo vive en la misma tabla que el de reset: un token de reset válido de ese usuario también serviría para reclamar (igualmente prueba control del correo). `forgot-password` sigue sin atender cuentas inactivas.
- Una invitación pendiente sigue siendo detectable por la respuesta 202 vs 201/409 (ya lo era antes).
- Sesiones OAuth abiertas antes del deploy (state base64 viejo) fallarán con 400: el usuario reintenta «Conectar». Sin push ni deploy.
- Espejos móviles regenerados con `build_www.py` + `capacitor sync` (gitignorados).
