# Sprint 39 — Alembic Consolidation (completado 2026-07-03)

## R-03: Consolidar migrations en Alembic

### Problema
El proyecto tenía **tres sistemas de migración paralelos**:
1. `Base.metadata.create_all()` — crea todas las tablas de los modelos SQLAlchemy
2. `migrate_db()` en `start_coach_api.py` — ~260 líneas de ALTER TABLE + CREATE TABLE condicionales
3. Bloque hot-migration en `api/coach_main.py` (líneas 168-709) — ~540 líneas de SQL ejecutadas en cada arranque

### Solución

#### 1. Nueva revisión Alembic: `h4c5d6e7f8g9_sprint13_to_38_catchall`
Cubre todas las tablas y columnas que existían solo en los sistemas legados:

**Tablas nuevas (CREATE TABLE IF NOT EXISTS):**
- `login_attempts`, `drip_logs`, `push_subscriptions`
- `injury_risk_snapshots`, `race_events`
- `training_plans`, `plan_sessions`
- `follows`, `community_posts`, `kudos`, `comments`
- `community_groups`, `community_group_members`
- `challenges`, `challenge_entries`, `community_notifications`
- `blood_lab_alerts`

**Columnas nuevas (ALTER TABLE try/except):**
- `users`: strava_*, totp_backup_hash, last_device_hash, stripe_customer_id, gdpr_consent_*, notif_*, ftp, height_cm, fcmax
- `garmin_activities`: swolf, avg_cadence_spm, pool_length_m, photo_path
- `plan_sessions`: rpe, perceived_effort, mood, feedback_at
- `blood_lab_exams`: notes, ai_interpretation, ai_interpreted_at
- `assigned_workouts`: coach_comment

#### 2. `api/coach_main.py`
- **Eliminado**: bloque hot-migration completo (~540 líneas, líneas 168-709)
- **Mantenido**: `Base.metadata.create_all(bind=engine)` como safety net para SQLite dev

#### 3. `start_coach_api.py`
- **Eliminado**: función `migrate_db()` (~220 líneas)
- **Añadido**: `run_alembic_upgrade()` — llama `alembic upgrade head` via Python API
- **Safety**: si Alembic falla, continúa (create_all ya aplicó el schema)

#### 4. `.github/workflows/ci.yml`
- **Añadido**: `alembic upgrade head` antes de iniciar el servidor en el smoke test job

### Cadena Alembic completa

```
ca391f8bf2e6 (initial_schema)
  └─ a1b2c3d4e5f6 (sprint1_health_ai)
       └─ b7f1e9d3a2c8 (sprint15_to_20)
            └─ c9e2f4a1b3d7 (sprint14_nutrition)
                 └─ d0e1f2a3b4c5 (sprint27_prescriptions)
                      └─ e1f2a3b4c5d6 (sprint31_training_phases)
                           └─ f2a3b4c5d6e7 (sprint32_benchmarks)
                                └─ g3b4c5d6e7f8 (sprint33_plan_templates)
                                     └─ h4c5d6e7f8g9 (sprint13_to_38_catchall) ← NEW
```

### Métricas
- Líneas eliminadas de `coach_main.py`: ~545 (bloque hot-migration)
- Líneas eliminadas de `start_coach_api.py`: ~220 (migrate_db)
- Tests: 1641 passed, 0 failures

### Para producción (PostgreSQL)
```bash
# Antes de deploy:
alembic upgrade head

# O en start_coach_api.py (automático):
python start_coach_api.py  # llama run_alembic_upgrade() internamente
```
