"""
Fixtures compartidos para todos los tests de LabX.
Usa base de datos SQLite en memoria para tests aislados y rápidos.
"""
import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET",   "test-secret-key-labx-tests")
os.environ.setdefault("APP_ENV",      "test")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.database import Base, get_db
from api.coach_main import app
from api.models import User
from api.auth import hash_password

TEST_DB_URL = "sqlite:///:memory:"

# StaticPool forces all connections to share the same underlying connection,
# which is required for in-memory SQLite: otherwise each new connection gets
# an empty DB and tables created by create_all() are invisible to test requests.
engine_test = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine_test)
    app.dependency_overrides[get_db] = override_get_db
    yield TestingSessionLocal()
    Base.metadata.drop_all(bind=engine_test)
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def client(db):
    Base.metadata.create_all(bind=engine_test)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    Base.metadata.drop_all(bind=engine_test)
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db) -> User:
    u = User(
        email="admin@test.com",
        nombre="Admin Test",
        password_hash=hash_password("AdminPass123"),
        rol="admin",
        plan_nivel="elite",
        activo=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def coach_user(db) -> User:
    u = User(
        email="coach@test.com",
        nombre="Coach Test",
        password_hash=hash_password("CoachPass123"),
        rol="coach",
        plan_nivel="pro",
        activo=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def athlete_user(db) -> User:
    u = User(
        email="athlete@test.com",
        nombre="Athlete Test",
        password_hash=hash_password("AthlPass123"),
        rol="athlete",
        plan_nivel="basico",
        activo=True,
        ftp=220,
        fcmax=182,
        weight_kg=72.0,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def login(client, email: str, password: str) -> str:
    """Helper: hace login y retorna el access_token."""
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login falló: {r.text}"
    return r.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
