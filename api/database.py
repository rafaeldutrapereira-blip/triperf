"""
SQLAlchemy setup — SQLite para desarrollo, swap a PostgreSQL en producción
cambiando solo DATABASE_URL en .env.
"""
import os
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR     = Path(__file__).resolve().parent.parent
_raw_db_url  = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'labx_coach.db'}")
# Railway provee "postgres://" (sin ql) — SQLAlchemy 2.x requiere "postgresql://"
DATABASE_URL = _raw_db_url.replace("postgres://", "postgresql://", 1) if _raw_db_url.startswith("postgres://") else _raw_db_url

_is_sqlite = DATABASE_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

# PostgreSQL pool tuning: conservative sizing suitable for PGBouncer in front.
# With PGBouncer (transaction mode) each app connection maps to 1 PG connection;
# keep pool small so PGBouncer can multiplex efficiently.
_pool_kwargs: dict = {} if _is_sqlite else {
    "pool_size":    int(os.getenv("DB_POOL_SIZE",    "5")),
    "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
    "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
    "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
}

engine = create_engine(
    DATABASE_URL,
    connect_args = _connect_args,
    pool_pre_ping = True,   # detecta conexiones muertas (útil en PostgreSQL)
    echo = False,
    **_pool_kwargs,
)

# SQLite: activar WAL mode para mejor concurrencia de lectura
if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yield DB session, siempre cierra al final."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
