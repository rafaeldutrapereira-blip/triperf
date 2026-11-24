# Fix A1 (h4) — relación coach-atleta activa obligatoria

Base: main, BUILD 412, commit 0da3280. Commit local, sin push ni deploy.

## Qué se cambió
- `api/routes/coach_routes.py` `add_member` (~l.190-208): exige `CoachAthlete.status=='active'` (coach actual + user_id) y `rol` de atleta (`atleta`/`athlete`, ambos valores existen en el código/tests) → si no, **403**. Usuario inexistente sigue en 404.
- `api/permissions.py` `assert_coach_owns_athlete` (~l.34-50): se quitó la consulta de `GroupMember`; solo vale la relación activa (admin sigue con bypass).
- `api/routes/athlete_routes.py` `_verify_coach_access` (~l.99-110): ahora consulta `CoachAthlete` activo en vez de membresía de grupo (admin sigue con bypass).
- Tests: `api/tests/test_coach.py` (fixture `group_with_athlete` y `test_add_member` crean relación activa; nuevos `test_add_member_sin_relacion_activa_403` y `test_membresia_de_grupo_sola_no_da_acceso`) y `api/tests/test_sprint44_sse_compliance.py` (setup crea relación activa). Esos tests asumían que la membresía sola bastaba.

## Verificación
- `pytest api/tests -k "coach or permission or group or member or blood or wellness or nutrition"`: 684 passed, 12 failed antes de ajustar fixtures; los 12 eran tests que dependían de la membresía sola (test_coach.py y test_sprint44_sse_compliance.py).
- Tras ajustar: `pytest api/tests/test_coach.py api/tests/test_sprint44_sse_compliance.py` → 74 passed.
- No se corrió la suite completa. Los otros archivos del filtro no fallaron.

## Pendiente / notas
- Datos existentes: membresías ya creadas sin relación activa dejan de dar acceso (comportamiento buscado). Revisar en producción si hay `group_members` huérfanos de relación, y limpiarlos.
- `coach_athlete_ids` (permissions.py:94) sigue uniendo `CoachAthlete.activo` y miembros de grupo; afecta a `_bulk_add` y tableros (lectura agregada). No se tocó (fuera de alcance); con A1 cerrado solo contiene miembros legítimos hacia adelante, pero conviene alinearlo a `status=='active'`.
- Otras rutas con su propia lógica de membresía no se auditaron aquí.
- A3, H1, H7 y demás hallazgos: no tocados.
- Árbol: tracked limpio al inicio (`git diff`/`--cached` vacíos); había archivos untracked previos (reportes, scripts, prompts) que no se tocaron ni se commitearon.
