# REPORT-417 - A2-COMUNIDAD (privacidad de comunidad y mensajes)

Solo local: commit en main, sin push, sin deploy, sin migraciones.

## Cambios
- `api/routes/community_routes.py`
  - Busqueda: ya NO busca por email (solo `nombre`), solo usuarios activos, sin fallback al prefijo del email. Un email existente e inexistente devuelven lo mismo (lista vacia, mismo codigo). CTL solo si el usuario comparte (`share_details`). Se devuelve uuid, nombre, avatar, pais, is_following.
  - Perfil: `season_stats` (km/horas/TSS/actividades) solo si es el propio usuario, el usuario comparte (`community_share_prefs.share_details`) o el consultante es su coach. Si no, `season_stats: null` y `stats_shared: false`. El frontend no consume `season_stats`.
  - `get_post`: helper `_can_view_post` (public; followers solo seguidores; coach_only solo coach; private solo dueno). `list_comments` usa el mismo helper (404 si el post no existe, 403 sin acceso).
  - Grupos privados: `get_group`, `list_members`, `list_challenges`, `challenge_leaderboard` exigen ser miembro (403, mismo criterio que `group_feed`).
- `api/routes/message_routes.py`: `POST /messages` exige relacion: CoachAthlete activo (cualquier direccion), atleta en grupo del coach, hilo previo, o remitente admin. Sin relacion responde el mismo 404 que "destinatario no existe" (sin oraculo de uuid).
- `sw.js` BUILD 416 -> 417 + changelog. Espejos regenerados con `build_www.py` + `node .../capacitor sync`.
- Tests: `api/tests/test_a2_comunidad.py` (14 tests).

## Relaciones legitimas de mensajeria
Verificadas en codigo: coach-atleta activo, grupos de coach (`Group`/`GroupMember`), admin. Ningun HTML consume `/messages`. Casos que ahora se bloquean: atleta -> admin sin hilo previo (admin debe escribir primero); coach con relacion `pending` (invitacion no aceptada); usuarios sin relacion. Se considera intencional.

## Tests
- Nuevos: 14/14 en verde.
- Suite completa: ver `labx-overnight/a2-full.txt`; unicos fallos: `test_calendario_vivo_375.py::test_c_evento_borrado_en_origen_desaparece` y `::test_c2_pasado_se_conserva_y_fallo_no_borra`. PREEXISTENTES: fallan igual con mis cambios en stash (no relacionados con comunidad).

## Alcance honesto
- No se tocaron inbox/thread/read/delete, `group_feed`, `invite_code`, ni el resto de `community_routes.py`.
- El avatar se sigue devolviendo en la busqueda (no existe preferencia de avatar); es necesario para encontrar companeros.
- Busqueda por nombre sigue permitiendo enumerar nombres; no hay rate limit nuevo. Diferencia de tiempo email existente/inexistente: ya no hay consulta distinta, al no consultar el email.
- `get_athletes_for_coach` incluye a todos los atletas para admin: el admin ve stats de cualquiera (intencional, como antes).
- Perfil: `follower_count`, `following_count`, `recent_posts` publicos se mantienen.
