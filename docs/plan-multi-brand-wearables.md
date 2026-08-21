# Plan Multi-Marca (Garmin → Garmin + Strava + Wahoo + Polar + Coros + Apple Health)

Fecha auditoría: 2026-08-20
Backup pre-refactor: tag git `backup-pre-multibrand-20260820_201451` + bundle `~/labx_backups/labx_full_history_20260820_201451.bundle` + zip `~/labx_backups/labx_fullcode_backup_20260820_201533.zip`

## 1. Qué encontró la auditoría

El acoplamiento a Garmin no es superficial: es el *schema de datos*, no solo el conector.

- **90 archivos** (`api/`, `models/`, `scripts/`) referencian "garmin" directamente (rutas, servicios, tests, tareas Celery).
- Las tablas centrales del negocio se llaman literalmente `garmin_activities`, `garmin_training_load`, `garmin_sync_status`, `garmin_health_daily`, `garmin_sleep_session` ([api/models.py:740](api/models.py#L740), [api/models.py:822](api/models.py#L822), [api/models.py:853](api/models.py#L853), [api/models.py:994](api/models.py#L994), [api/models.py:1055](api/models.py#L1055)). No existe columna `provider`/`source`.
- Strava **ya está integrado**, pero como un parche: escribe directo en `GarminActivity` prefijando `activity_id` con `"strava_"` para poder distinguirlo ([api/routes/strava_routes.py:321-432](api/routes/strava_routes.py#L321)). Es el precedente de que *sí se puede* meter una segunda marca sin romper todo — pero el patrón actual no escala a una tercera.
- Toda la lógica de sync/parseo/MFA/login vive en una sola clase monolítica, `GarminPullService` (~1250 líneas, [api/garmin_pull_service.py:922-2178](api/garmin_pull_service.py#L922)), con `_parse_garmin_activity` como único punto de normalización Garmin→interno ([api/garmin_pull_service.py:629](api/garmin_pull_service.py#L629)).
- `api/garmin_converter.py` es otra cosa (conversión de workouts estructurados para *push* a reloj Garmin, no ingesta) — no confundir los dos módulos en el refactor.

**Conclusión:** no es un problema de "agregar un if por marca". Es una migración de esquema + introducir una capa de adaptador. Es viable, pero debe hacerse en sprints incrementales con feature flags, no de una vez.

## 2. Reglas no negociables para todos los sprints

Dado que **no tienes hardware de otras marcas para probar**, y dado el historial ya registrado en este proyecto de bugs de datos falsos visibles al usuario (curva PMC con puntos inventados, "Insight del día" mostrando demo cuando fallaba el fetch real), cada sprint de este plan debe respetar:

1. **Cero datos sintéticos visibles al usuario.** Si un provider nuevo falla, no responde, o no tiene datos: la UI debe mostrar un estado vacío explícito ("Aún no hay datos de Wahoo") — nunca un número inventado, nunca un fallback a valores "de ejemplo".
2. **Ningún provider nuevo se activa en producción sin al menos 1 usuario real con ese dispositivo confirmando que sincroniza bien.** Feature flag apagado por defecto (`WAHOO_ENABLED=false`, etc.) hasta esa validación.
3. **Nada de JSON de prueba inventado a mano.** Los fixtures de test deben salir de la documentación pública oficial de cada API (todas Wahoo/Polar/Coros/Strava tienen developer portal gratuito con ejemplos de respuesta reales, sin necesidad de comprar el reloj) o de datos reales anonimizados que el propio Garmin/Strava ya te devuelven hoy.
4. **Cada sprint termina con un tag git de respaldo** antes de arrancar el siguiente (`git tag pre-sprintNN-<fecha>`).
5. **El sprint de Garmin actual no se toca en su comportamiento visible** hasta que el refactor estructural (Sprint 48-49) esté 100% verde en tests — es tu única fuente de datos reales, no puede quebrarse.

## 3. Sprints propuestos

Cada sprint incluye un **prompt listo para pegar** en una futura sesión de Claude Code.

### Sprint 48 — Interfaz `WearableProvider` (sin cambiar comportamiento)

Objetivo: extraer una interfaz común de la lógica que hoy solo sabe hablar con Garmin, sin tocar el comportamiento real. Es el sprint más importante y el que más riesgo tiene si se apura — no avanzar al siguiente sin que el sync real de un usuario piloto Garmin dé exactamente los mismos resultados antes/después.

> **Prompt:**
> "Audita `api/garmin_pull_service.py` (clase `GarminPullService`) y `api/routes/strava_routes.py` (función `_upsert_strava_activity`). Diseña e implementa una interfaz abstracta `WearableProvider` (ABC) en `api/providers/base.py` con los métodos que ambos flujos ya implementan de hecho: `authenticate`, `list_activities(since)`, `get_activity_detail(id)`, `download_gps(id)`, `download_splits(id)`, `get_health_daily(date)`, `get_sleep(date)`. Refactoriza `GarminPullService` para que implemente esa interfaz como `GarminProvider`, y `strava_routes.py` para que use una clase `StravaProvider` con la misma interfaz — sin cambiar ninguna lógica de negocio ni de parseo, solo moviendo código a la nueva forma. Agrega una migración Alembic que añade la columna `provider` (string, default `'garmin'`) a `garmin_activities`, `garmin_training_load`, `garmin_sync_status`, `garmin_health_daily`, `garmin_sleep_session`, y backfillea `provider='strava'` donde `activity_id LIKE 'strava_%'`. Corre toda la suite de tests existente y no continúes hasta que quede 100% verde. Reporta cualquier diferencia de comportamiento encontrada, no la corrijas silenciosamente."

### Sprint 49 — Renombrado simbólico gradual

Objetivo: dejar de crecer deuda nueva con nombres `Garmin*`, sin arriesgar una migración de tabla masiva todavía.

> **Prompt:**
> "En `api/models.py`, agrega alias explícitos (`Activity = GarminActivity`, `HealthDaily = GarminHealthDaily`, `SleepSession = GarminSleepSession`, `TrainingLoad = GarminTrainingLoad`) sin renombrar las tablas físicas todavía (evitamos migración de datos riesgosa por ahora). Actualiza el CLAUDE.md o convención de contribución del repo: todo código nuevo debe importar y usar los alias genéricos, nunca crear un campo o variable nueva con prefijo `garmin_` salvo que sea literalmente específico de la API de Garmin (ej. tokens de auth). Audita los 90 archivos que hoy importan `GarminActivity`/`GarminTrainingLoad` directamente y decide cuáles vale la pena migrar al alias ahora vs. dejar para después — repórtalo, no lo hagas todo de una vez."

**Estado Sprint 49 (2026-08-20):** alias creados en `api/models.py` (`Activity`, `TrainingLoad`, `ProviderSyncStatus`, `HealthDaily`, `SleepSession`). Auditados 44 archivos que importan las clases `Garmin*` directamente (no 90 — ese número original incluía cualquier mención de "garmin" en comentarios/strings, no solo imports reales). **Decisión: no migrarlos ahora.** Cambiar 44 call-sites en rutas/servicios que están corriendo en producción es una rename puramente cosmética (mismo objeto Python — `Activity is GarminActivity`) sin ningún beneficio funcional hoy, y sí con riesgo real de introducir un typo en un archivo que toca a usuarios reales. La convención rige desde ahora solo para código nuevo: cualquier archivo creado o reescrito a partir de este punto debe importar los alias genéricos, nunca `Garmin*` (salvo que sea literalmente específico de la API de Garmin, ej. tokens/MFA). Los 44 archivos existentes se migran de forma oportunista, cuando ya se estén tocando por otro motivo — no en un sprint dedicado.

### Sprint 50 — Registry de providers + flags + UI de Conexiones

> **Prompt:**
> "Crea un `ProviderRegistry` en `api/providers/registry.py` que mapee un string `provider` (`garmin`, `strava`, `wahoo`, `polar`, `coros`, `apple_health`) a su clase `WearableProvider`. Lee de variables de entorno cuáles providers están habilitados (`WAHOO_ENABLED`, etc., todas `false` por defecto salvo `garmin`/`strava` que ya están en producción). En la página de 'Conexiones' del frontend (ya existente para Garmin/Strava), oculta cualquier botón de marca cuyo flag esté apagado — no debe aparecer una opción que no funciona. Ningún fixture inventado en este sprint: solo estructura y flags."

### Sprint 51 — Contract tests con fixtures reales (la base de tu 'testing sin hardware')

> **Prompt:**
> "Crea `api/tests/fixtures/garmin/*.json` capturando 5-10 respuestas reales (anonimizadas: reemplaza nombre/email por valores ficticios, deja las métricas reales) del sync que ya corre hoy contra la cuenta Garmin real del usuario. Escribe un test contractual parametrizado `test_provider_contract.py` que cualquier `WearableProvider` debe pasar: dado un fixture crudo, el resultado normalizado debe tener `sport`, `date_iso`, `dur_min` válidos, y `tss` no nulo si hay HR o potencia. Corre este contrato contra `GarminProvider` con los fixtures reales para confirmar que pasa. Este test es el gate obligatorio antes de aceptar cualquier provider nuevo (Wahoo/Polar/Coros) más adelante, aunque no tengamos el dispositivo físico para probarlo en vivo."

### Sprint 52 — Wahoo (primera marca nueva candidata)

Por qué Wahoo primero: developer portal público con ejemplos de respuesta reales documentados, sin requerir compra de hardware para acceder a la doc, y es una marca común en triatlón (overlap alto con tu público).

> **Prompt:**
> "Implementa `WahooProvider` en `api/providers/wahoo.py` contra la API pública real de Wahoo Cloud (OAuth2 + endpoints documentados en developers.wahoofitness.com). Usa como fixtures de test únicamente los ejemplos de respuesta que aparecen en su documentación oficial — no inventes JSON. Debe pasar el contract test del Sprint 51. Actívalo solo bajo el flag `WAHOO_ENABLED`, apagado por defecto. No lo actives en producción hasta conseguir al menos un usuario real con reloj Wahoo que confirme que el sync trae datos correctos — coordina eso conmigo antes de marcar el sprint como cerrado."

### Sprint 53 / 54 — Polar / Coros

Mismo patrón que Sprint 52, un prompt por marca, reemplazando "Wahoo" por la marca correspondiente y su developer portal (Polar Accesslink, Coros Developer API).

### Sprint 55 — Apple Health / Health Connect

Distinto a los anteriores: no es una API cloud con OAuth, es integración nativa en la app móvil (lectura local de HealthKit/Health Connect). Requiere trabajo en el proyecto de la app (ver memoria de paridad app↔web), no solo backend. Planificar aparte cuando llegue el momento.

## 4. Cómo validar sin comprar el hardware

- **Wahoo/Polar/Coros/Strava**: todas tienen developer portal gratuito. Puedes crear una cuenta de desarrollador y obtener ejemplos de payload reales de su documentación sin poseer el reloj — úsalos como fixtures, nunca datos inventados a mano.
- **Beta con usuarios reales**: para el sync end-to-end (no solo el parseo), necesitas 1 persona real con cada dispositivo. Vale la pena pedir en foros de triatlón/Strava clubs 1-2 voluntarios dispuestos a probar la integración a cambio de acceso anticipado — es la única forma de validar el flujo OAuth completo y los datos reales de ese dispositivo.
- **Shadow-mode**: si en el futuro un usuario tiene dos dispositivos (ej. Garmin + Wahoo en la misma sesión), compara el TSS/CTL calculado por ambos paths y alerta si divergen — es una red de seguridad barata para detectar bugs de parseo sin depender de que tú mismo tengas el hardware.

## 5. Progreso

- [x] Sprint 48 — Interfaz WearableProvider (commit `ecc1fe4`) — nota: `get_health_daily`/`get_sleep` y el list/detail de Strava quedaron con `NotImplementedError` explícito, no decoupled todavía (ver decisión en el commit)
- [x] Sprint 49 — Renombrado simbólico (commit `49cd046`) — alias creados, 44 call-sites existentes quedaron sin migrar a propósito (ver nota arriba)
- [x] Sprint 50 — Registry + flags + endpoint `/providers/enabled` (commit `f8b87de`) — UI de Conexiones NO adaptada todavía a propósito: hoy no hay ninguna card de marca nueva que ocultar, se hace data-driven recién cuando Sprint 52 agregue la primera card real (Wahoo)
- [x] Sprint 51 — Contract tests (commit `e008e7f`) — 8 fixtures reales anonimizadas de `data/cache/`, gate `test_provider_contract.py` listo para exigirse a Wahoo/Polar/Coros
- [ ] Sprint 52 — Wahoo
- [ ] Sprint 53 — Polar
- [ ] Sprint 54 — Coros
- [ ] Sprint 55 — Apple Health (app móvil)
