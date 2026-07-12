"""S10 — Tests para Stripe plans, features y feature gating."""
import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET",   "test-secret-key-labx-tests")
os.environ.setdefault("APP_ENV",      "test")

from api.routes.stripe_routes import has_feature, _PLAN_FEATURES
from api.models import User
from .conftest import auth_headers, login


class TestFeatureFlags:
    def test_basico_has_dashboard(self):
        u = User(rol="athlete", plan_nivel="basico")
        assert has_feature(u, "dashboard") is True

    def test_basico_no_nutrition(self):
        # Garmin sync es basico (todos los planes) — el corte real de plan
        # empieza en Agegroup, con módulos como nutrición/analytics/recovery.
        u = User(rol="athlete", plan_nivel="basico")
        assert has_feature(u, "nutrition") is False

    def test_agegroup_has_nutrition(self):
        u = User(rol="athlete", plan_nivel="agegroup")
        assert has_feature(u, "nutrition") is True

    def test_coach_has_all(self):
        u = User(rol="coach", plan_nivel="basico")
        # Coaches siempre tienen acceso completo independiente del plan
        assert has_feature(u, "coach_platform") is True
        assert has_feature(u, "advanced_analytics") is True

    def test_admin_has_all(self):
        u = User(rol="admin", plan_nivel="basico")
        assert has_feature(u, "advanced_analytics") is True

    def test_unknown_plan_defaults_basico(self):
        u = User(rol="athlete", plan_nivel="unknown_plan")
        basico_features = _PLAN_FEATURES["basico"]
        for feat in basico_features:
            assert has_feature(u, feat) is True
        assert has_feature(u, "garmin_sync") is False


class TestPlansEndpoint:
    def test_list_plans_public(self, client):
        r = client.get("/api/stripe/plans")
        assert r.status_code == 200
        data = r.json()
        assert "plans" in data
        ids = [p["id"] for p in data["plans"]]
        assert "basico" in ids
        assert "agegroup" in ids
        assert "elite" in ids
        assert "coach" in ids

    def test_my_features_requires_auth(self, client):
        r = client.get("/api/stripe/my-features")
        assert r.status_code == 401

    def test_my_features_basico(self, client, athlete_user):
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.get("/api/stripe/my-features", headers=auth_headers(token))
        assert r.status_code == 200
        data = r.json()
        assert data["plan"] == "basico"
        assert "dashboard" in data["features"]
        assert "garmin_sync" not in data["features"]

    def test_checkout_requires_auth(self, client):
        r = client.post("/api/stripe/checkout", json={"plan": "agegroup"})
        assert r.status_code == 401

    def test_checkout_no_stripe_key(self, client, athlete_user):
        """Sin STRIPE_SECRET_KEY configurada, debe retornar 503."""
        token = login(client, "athlete@test.com", "AthlPass123")
        r = client.post("/api/stripe/checkout",
                        json={"plan": "agegroup"},
                        headers=auth_headers(token))
        assert r.status_code == 503
