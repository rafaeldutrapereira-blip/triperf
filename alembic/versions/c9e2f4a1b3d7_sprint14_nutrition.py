"""Sprint 14: Nutrition Intelligence tables

Revision ID: c9e2f4a1b3d7
Revises: b7f1e9d3a2c8
Create Date: 2026-06-29

Covers:
  food_diary_entries, nutrition_plans, hydration_logs, weight_logs,
  supplement_logs, custom_foods, favorite_foods, nutrition_insights
"""
from alembic import op

revision = 'c9e2f4a1b3d7'
down_revision = 'b7f1e9d3a2c8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS food_diary_entries (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            date_iso    TEXT NOT NULL,
            meal_slot   TEXT NOT NULL DEFAULT 'other',
            food_name   TEXT NOT NULL,
            off_id      TEXT,
            quantity_g  REAL NOT NULL DEFAULT 100,
            kcal        REAL,
            carbs_g     REAL,
            protein_g   REAL,
            fat_g       REAL,
            fiber_g     REAL,
            sodium_mg   REAL,
            sugar_g     REAL,
            notes       TEXT,
            logged_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_food_diary_user_date ON food_diary_entries(user_id, date_iso)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS nutrition_plans (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            race_name   TEXT,
            race_date   TEXT,
            race_dist   TEXT,
            total_kcal  INTEGER,
            cho_g       INTEGER,
            fluid_ml    INTEGER,
            sodium_mg   INTEGER,
            params_json TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_nutrition_plans_user ON nutrition_plans(user_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS hydration_logs (
            id           TEXT PRIMARY KEY,
            user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            date_iso     TEXT NOT NULL,
            amount_ml    INTEGER NOT NULL,
            liquid_type  TEXT DEFAULT 'water',
            logged_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_hyd_user_date ON hydration_logs(user_id, date_iso)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS weight_logs (
            id           TEXT PRIMARY KEY,
            user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            date_iso     TEXT NOT NULL,
            weight_kg    REAL NOT NULL,
            body_fat_pct REAL,
            logged_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date_iso)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_weight_user_date ON weight_logs(user_id, date_iso)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS supplement_logs (
            id           TEXT PRIMARY KEY,
            user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            date_iso     TEXT NOT NULL,
            supplement   TEXT NOT NULL,
            dose_mg      REAL,
            timing       TEXT,
            logged_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_supp_user_date ON supplement_logs(user_id, date_iso)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS custom_foods (
            id           TEXT PRIMARY KEY,
            user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name         TEXT NOT NULL,
            brand        TEXT,
            serving_g    REAL DEFAULT 100,
            kcal_100g    REAL,
            carbs_100g   REAL,
            protein_100g REAL,
            fat_100g     REAL,
            fiber_100g   REAL,
            sodium_100g  REAL,
            is_public    BOOLEAN DEFAULT 0,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_custom_food_user ON custom_foods(user_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS favorite_foods (
            id           TEXT PRIMARY KEY,
            user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            food_ref     TEXT NOT NULL,
            food_name    TEXT,
            default_g    REAL DEFAULT 100,
            use_count    INTEGER DEFAULT 1,
            last_used    DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, food_ref)
        )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_fav_food ON favorite_foods(user_id, food_ref)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS nutrition_insights (
            id               TEXT PRIMARY KEY,
            user_id          TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            date_iso         TEXT NOT NULL,
            insights         TEXT,
            meal_suggestions TEXT,
            created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date_iso)
        )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_insight_user_date ON nutrition_insights(user_id, date_iso)")


def downgrade() -> None:
    for table in [
        "nutrition_insights", "favorite_foods", "custom_foods",
        "supplement_logs", "weight_logs", "hydration_logs",
        "nutrition_plans", "food_diary_entries",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table}")
