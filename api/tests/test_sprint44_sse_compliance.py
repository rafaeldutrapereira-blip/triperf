"""
Sprint 44 — SSE Broker (B-20) + Compliance Trending (B-22) tests.

Coverage targets:
  - api/sse_broker.py          : InMemoryBroker, RedisBroker, create_broker, publish_nowait
  - api/routes/compliance_routes.py : athlete_compliance_trend, coach_athlete_compliance_trend, squad
  - api/routes/events_routes.py     : _SubscribersView, publish_event, event_stream
  - SSE wiring in coach_routes / message_routes / garmin_pull_service
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _reg_login(client, email, password="Test1234!") -> str:
    client.post("/api/auth/register", json={
        "email": email, "password": password,
        "nombre": "Test User", "rol": "athlete",
    })
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _create_coach(db, email="coach44@test.com", nombre="Coach 44") -> "User":
    """Create a coach user directly via DB (registration API hardcodes rol=atleta)."""
    from api.models import User
    from api.auth import hash_password
    u = User(
        email=email,
        nombre=nombre,
        password_hash=hash_password("Test1234!"),
        rol="coach",
        plan_nivel="agegroup",
        activo=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _login_user(client, email, password="Test1234!") -> str:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


# ═══════════════════════════════════════════════════════════════════
# SSE BROKER — InMemoryBroker unit tests
# ═══════════════════════════════════════════════════════════════════

class TestInMemoryBroker:
    def test_publish_to_unsubscribed_user_is_noop(self):
        from api.sse_broker import InMemoryBroker
        broker = InMemoryBroker()
        asyncio.run(broker.publish("nobody", "evt", {}))  # should not raise

    def test_subscribe_yields_connected_event(self):
        from api.sse_broker import InMemoryBroker
        broker = InMemoryBroker()

        async def _run():
            gen = broker.subscribe("u1")
            first = await gen.__anext__()
            return first

        first = asyncio.run(_run())
        assert "connected" in first

    def test_publish_reaches_subscriber(self):
        from api.sse_broker import InMemoryBroker
        broker = InMemoryBroker()

        received = []

        async def _run():
            gen = broker.subscribe("u2")
            await gen.__anext__()  # connected
            await broker.publish("u2", "workout_assigned", {"name": "FTP Test"})
            msg = await gen.__anext__()
            received.append(msg)
            await gen.aclose()

        asyncio.run(_run())
        assert len(received) == 1
        data = json.loads(received[0].replace("data: ", "").strip())
        assert data["type"] == "workout_assigned"
        assert data["data"]["name"] == "FTP Test"

    def test_connection_count_tracks_subscribers(self):
        from api.sse_broker import InMemoryBroker
        broker = InMemoryBroker()
        assert broker.connection_count() == 0

        async def _run():
            gen = broker.subscribe("u3")
            await gen.__anext__()  # connected
            count = broker.connection_count()
            await gen.aclose()
            return count

        count = asyncio.run(_run())
        assert count == 1

    def test_connection_count_decrements_after_close(self):
        from api.sse_broker import InMemoryBroker
        broker = InMemoryBroker()

        async def _run():
            gen = broker.subscribe("u4")
            await gen.__anext__()
            await gen.aclose()
            return broker.connection_count()

        count = asyncio.run(_run())
        assert count == 0

    def test_multiple_subscribers_same_user(self):
        from api.sse_broker import InMemoryBroker
        broker = InMemoryBroker()

        async def _run():
            g1 = broker.subscribe("u5")
            g2 = broker.subscribe("u5")
            await g1.__anext__()
            await g2.__anext__()
            count = broker.connection_count()
            await g1.aclose()
            await g2.aclose()
            return count

        count = asyncio.run(_run())
        assert count == 2

    def test_publish_to_wrong_user_not_received(self):
        from api.sse_broker import InMemoryBroker
        broker = InMemoryBroker()

        received = []

        async def _run():
            gen = broker.subscribe("u6")
            await gen.__anext__()  # connected
            await broker.publish("u7", "evt", {})  # different user
            # queue for u6 should be empty
            received.append(broker.connection_count())
            await gen.aclose()

        asyncio.run(_run())
        assert len(broker._queues.get("u6", [])) == 0

    def test_subscribers_view_property(self):
        from api.sse_broker import InMemoryBroker
        broker = InMemoryBroker()
        assert isinstance(broker._subscribers, dict)

    def test_heartbeat_emitted_on_timeout(self):
        import api.sse_broker as _mod
        from api.sse_broker import InMemoryBroker

        async def _run():
            old = _mod._HEARTBEAT_INTERVAL
            _mod._HEARTBEAT_INTERVAL = 0.01
            try:
                broker = InMemoryBroker()
                gen = broker.subscribe("u8")
                await gen.__anext__()  # connected
                chunk = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
                await gen.aclose()
                return chunk
            finally:
                _mod._HEARTBEAT_INTERVAL = old

        chunk = asyncio.run(_run())
        assert "heartbeat" in chunk


# ═══════════════════════════════════════════════════════════════════
# SSE BROKER — create_broker factory
# ═══════════════════════════════════════════════════════════════════

class TestCreateBroker:
    def test_no_redis_url_returns_in_memory(self):
        from api.sse_broker import create_broker, InMemoryBroker
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("REDIS_URL", None)
            b = create_broker()
            assert isinstance(b, InMemoryBroker)

    def test_invalid_redis_url_falls_back_to_in_memory(self):
        from api.sse_broker import create_broker, InMemoryBroker
        with patch.dict(os.environ, {"REDIS_URL": "redis://bad-host:6379"}):
            b = create_broker()
            assert isinstance(b, InMemoryBroker)

    def test_valid_redis_creates_redis_broker(self):
        from api.sse_broker import create_broker, RedisBroker
        mock_redis_mod = MagicMock()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_mod.from_url.return_value = mock_client

        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"}):
            with patch.dict("sys.modules", {"redis": mock_redis_mod}):
                b = create_broker()
                assert isinstance(b, RedisBroker)

    def test_module_singleton_exists(self):
        from api.sse_broker import broker, SSEBroker
        assert isinstance(broker, SSEBroker)


# ═══════════════════════════════════════════════════════════════════
# SSE BROKER — publish_nowait
# ═══════════════════════════════════════════════════════════════════

class TestPublishNowait:
    def test_publish_nowait_does_not_raise(self):
        from api.sse_broker import publish_nowait
        publish_nowait("any-user", "test_event", {"k": "v"})  # should not raise

    def test_publish_nowait_with_running_loop(self):
        from api.sse_broker import publish_nowait, InMemoryBroker
        import api.sse_broker as _mod
        broker = InMemoryBroker()
        old_broker = _mod.broker
        _mod.broker = broker

        async def _run():
            gen = broker.subscribe("u9")
            await gen.__anext__()  # connected
            publish_nowait("u9", "test_event", {"value": 42})
            await asyncio.sleep(0.05)
            chunk = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
            await gen.aclose()
            return chunk

        try:
            chunk = asyncio.run(_run())
            data = json.loads(chunk.replace("data: ", "").strip())
            assert data["type"] == "test_event"
        finally:
            _mod.broker = old_broker

    def test_publish_nowait_from_thread(self):
        from api.sse_broker import publish_nowait
        errors = []
        def _work():
            try:
                publish_nowait("thread-user", "evt", {})
            except Exception as e:
                errors.append(e)

        t = threading.Thread(target=_work)
        t.start()
        t.join(timeout=2)
        assert not errors


# ═══════════════════════════════════════════════════════════════════
# SSE BROKER — RedisBroker unit tests
# ═══════════════════════════════════════════════════════════════════

class TestRedisBroker:
    @pytest.fixture
    def mock_redis(self):
        mock_mod = MagicMock()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_mod.from_url.return_value = mock_client
        with patch.dict("sys.modules", {"redis": mock_mod}):
            yield mock_mod, mock_client

    def test_channel_name_format(self, mock_redis):
        from api.sse_broker import RedisBroker
        b = RedisBroker("redis://localhost:6379")
        assert b._channel("u123") == "labx:sse:u123"

    def test_connection_count_delegates_to_local(self, mock_redis):
        from api.sse_broker import RedisBroker
        b = RedisBroker("redis://localhost:6379")
        assert b.connection_count() == 0

    def test_publish_calls_redis_publish(self, mock_redis):
        from api.sse_broker import RedisBroker
        _, mock_client = mock_redis
        b = RedisBroker("redis://localhost:6379")

        async def _run():
            await b.publish("u10", "evt", {"key": "val"})

        asyncio.run(_run())
        mock_client.publish.assert_called()

    def test_publish_fallback_on_redis_error(self, mock_redis):
        from api.sse_broker import RedisBroker
        _, mock_client = mock_redis
        mock_client.publish.side_effect = Exception("connection reset")
        b = RedisBroker("redis://localhost:6379")

        async def _run():
            await b.publish("u11", "evt", {})  # should not raise

        asyncio.run(_run())  # fallback to local broker


# ═══════════════════════════════════════════════════════════════════
# events_routes.py — _SubscribersView + publish_event
# ═══════════════════════════════════════════════════════════════════

class TestEventsRoutes:
    def test_subscribers_view_has_values_method(self):
        from api.routes.events_routes import _subscribers
        assert hasattr(_subscribers, "values")

    def test_subscribers_view_values_iterable(self):
        from api.routes.events_routes import _subscribers
        list(_subscribers.values())  # should not raise

    def test_publish_event_is_coroutine(self):
        from api.routes.events_routes import publish_event
        import inspect
        assert inspect.iscoroutinefunction(publish_event)

    def test_publish_event_delegates_to_broker(self):
        from api.routes.events_routes import publish_event
        import api.sse_broker as _broker_mod

        received = []

        class _FakeBroker:
            async def publish(self, user_id, event_type, data):
                received.append((user_id, event_type, data))
            def connection_count(self): return 0

        orig_broker = _broker_mod.broker
        _broker_mod.broker = _FakeBroker()
        # Also patch the name inside events_routes since it's imported directly
        import api.routes.events_routes as _evt_mod
        orig_evt_broker = _evt_mod.broker
        _evt_mod.broker = _FakeBroker()
        try:
            asyncio.run(publish_event("u99", "test", {"x": 1}))
        finally:
            _broker_mod.broker = orig_broker
            _evt_mod.broker = orig_evt_broker

        assert received == [("u99", "test", {"x": 1})]

    def test_event_stream_endpoint_registered(self, client, db):
        """Verify the /api/events SSE endpoint exists in the OpenAPI schema."""
        r = client.get("/openapi.json")
        assert r.status_code == 200
        paths = r.json().get("paths", {})
        assert "/api/events" in paths


# ═══════════════════════════════════════════════════════════════════
# COMPLIANCE TRENDING — athlete endpoints
# The endpoint at /api/athlete/compliance-trend returns a list of
# {week_start, week_end, total_rx, completed_rx, compliance_pct}
# (from template_service.compliance_trend)
# ═══════════════════════════════════════════════════════════════════

class TestAthleteComplianceTrend:
    def test_trend_default_8_weeks(self, client, db):
        tok = _reg_login(client, "ctrend1@test.com")
        r = client.get("/api/athlete/compliance-trend", headers=_auth(tok))
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 8

    def test_trend_custom_weeks(self, client, db):
        tok = _reg_login(client, "ctrend2@test.com")
        r = client.get("/api/athlete/compliance-trend?weeks=4", headers=_auth(tok))
        assert r.status_code == 200
        assert len(r.json()) == 4

    def test_trend_no_prescriptions_returns_null_pct(self, client, db):
        tok = _reg_login(client, "ctrend3@test.com")
        r = client.get("/api/athlete/compliance-trend?weeks=2", headers=_auth(tok))
        assert r.status_code == 200
        trend = r.json()
        for w in trend:
            assert w["compliance_pct"] is None
            assert w["total_rx"] == 0

    def test_trend_week_structure(self, client, db):
        tok = _reg_login(client, "ctrend4@test.com")
        r = client.get("/api/athlete/compliance-trend?weeks=1", headers=_auth(tok))
        assert r.status_code == 200
        w = r.json()[0]
        assert "week_start" in w
        assert "week_end" in w
        assert "total_rx" in w
        assert "completed_rx" in w
        assert "compliance_pct" in w

    def test_trend_requires_auth(self, client):
        r = client.get("/api/athlete/compliance-trend")
        assert r.status_code == 401

    def test_trend_weeks_max_52(self, client, db):
        tok = _reg_login(client, "ctrend6@test.com")
        r = client.get("/api/athlete/compliance-trend?weeks=52", headers=_auth(tok))
        assert r.status_code == 200
        assert len(r.json()) == 52

    def test_trend_weeks_too_large_rejected(self, client, db):
        tok = _reg_login(client, "ctrend7@test.com")
        r = client.get("/api/athlete/compliance-trend?weeks=100", headers=_auth(tok))
        assert r.status_code == 422

    def test_trend_week_dates_in_order(self, client, db):
        tok = _reg_login(client, "ctrend8@test.com")
        r = client.get("/api/athlete/compliance-trend?weeks=4", headers=_auth(tok))
        assert r.status_code == 200
        starts = [w["week_start"] for w in r.json()]
        assert starts == sorted(starts)


# ═══════════════════════════════════════════════════════════════════
# COMPLIANCE TRENDING — coach endpoints
# ═══════════════════════════════════════════════════════════════════

class TestCoachComplianceTrend:
    def _setup_coach_athlete(self, client, db, coach_email, athlete_email):
        """Create coach (direct DB) + athlete (registration), group, membership."""
        from api.models import User, Group, GroupMember

        coach   = _create_coach(db, coach_email)
        ath_tok = _reg_login(client, athlete_email)
        coach_tok = _login_user(client, coach_email)

        athlete = db.query(User).filter(User.email == athlete_email).first()

        g = Group(
            id=str(uuid.uuid4()),
            coach_id=coach.id,
            nombre="Test Group 44",
            descripcion="",
        )
        db.add(g)
        db.commit()

        gm = GroupMember(id=str(uuid.uuid4()), group_id=g.id, athlete_id=athlete.id)
        db.add(gm)
        db.commit()

        return coach_tok, ath_tok, coach, athlete, g

    def test_coach_athlete_trend_default_weeks(self, client, db):
        coach_tok, _, _, athlete, _ = self._setup_coach_athlete(
            client, db, "cc44a@test.com", "ca44a@test.com"
        )
        r = client.get(
            f"/api/coach/athletes/{athlete.id}/compliance-trend",
            headers=_auth(coach_tok),
        )
        assert r.status_code == 200
        # Returns a list of week entries
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 12  # default 12 weeks for coach view

    def test_coach_athlete_trend_custom_weeks(self, client, db):
        coach_tok, _, _, athlete, _ = self._setup_coach_athlete(
            client, db, "cc44b@test.com", "ca44b@test.com"
        )
        r = client.get(
            f"/api/coach/athletes/{athlete.id}/compliance-trend?weeks=4",
            headers=_auth(coach_tok),
        )
        assert r.status_code == 200
        assert len(r.json()) == 4

    def test_coach_cannot_access_unowned_athlete(self, client, db):
        coach_tok, _, _, _, _ = self._setup_coach_athlete(
            client, db, "cc44c@test.com", "ca44c@test.com"
        )
        other_tok = _reg_login(client, "ca44c_other@test.com")
        from api.models import User
        other = db.query(User).filter(User.email == "ca44c_other@test.com").first()
        r = client.get(
            f"/api/coach/athletes/{other.id}/compliance-trend",
            headers=_auth(coach_tok),
        )
        assert r.status_code in (403, 404)

    def test_squad_compliance_trend(self, client, db):
        coach_tok, _, _, athlete, _ = self._setup_coach_athlete(
            client, db, "cc44e@test.com", "ca44e@test.com"
        )
        r = client.get("/api/coach/squad/compliance-trend", headers=_auth(coach_tok))
        assert r.status_code == 200
        data = r.json()
        assert "athletes" in data
        assert "weeks" in data
        assert data["weeks"] == 4

    def test_squad_trend_contains_registered_athlete(self, client, db):
        coach_tok, _, _, athlete, _ = self._setup_coach_athlete(
            client, db, "cc44f@test.com", "ca44f@test.com"
        )
        r = client.get("/api/coach/squad/compliance-trend", headers=_auth(coach_tok))
        ids = [a["athlete_id"] for a in r.json()["athletes"]]
        assert athlete.id in ids

    def test_squad_trend_empty_coach(self, client, db):
        coach = _create_coach(db, "cc44g@test.com")
        coach_tok = _login_user(client, "cc44g@test.com")
        r = client.get("/api/coach/squad/compliance-trend", headers=_auth(coach_tok))
        assert r.status_code == 200
        assert r.json()["athletes"] == []

    def test_squad_trend_athlete_has_trend_key(self, client, db):
        coach_tok, _, _, athlete, _ = self._setup_coach_athlete(
            client, db, "cc44h@test.com", "ca44h@test.com"
        )
        r = client.get("/api/coach/squad/compliance-trend?weeks=2", headers=_auth(coach_tok))
        assert r.status_code == 200
        our = next(a for a in r.json()["athletes"] if a["athlete_id"] == athlete.id)
        assert "trend" in our
        assert "average_pct" in our
        assert len(our["trend"]) == 2


# ═══════════════════════════════════════════════════════════════════
# compliance_trend service unit tests
# ═══════════════════════════════════════════════════════════════════

class TestComplianceTrendService:
    def test_returns_list(self, db):
        from api.services.template_service import compliance_trend
        result = compliance_trend("nonexistent", 4, db)
        assert isinstance(result, list)
        assert len(result) == 4

    def test_null_pct_when_no_data(self, db):
        from api.services.template_service import compliance_trend
        result = compliance_trend("nonexistent", 2, db)
        for w in result:
            assert w["compliance_pct"] is None

    def test_chronological_order(self, db):
        from api.services.template_service import compliance_trend
        result = compliance_trend("nonexistent", 6, db)
        starts = [w["week_start"] for w in result]
        assert starts == sorted(starts)

    def test_entry_structure(self, db):
        from api.services.template_service import compliance_trend
        result = compliance_trend("nonexistent", 1, db)
        w = result[0]
        assert "week_start" in w
        assert "week_end" in w
        assert "total_rx" in w
        assert "completed_rx" in w
        assert "compliance_pct" in w

    def test_last_entry_is_recent(self, db):
        from api.services.template_service import compliance_trend
        result = compliance_trend("nonexistent", 3, db)
        last_end = date.fromisoformat(result[-1]["week_end"])
        today = date.today()
        # Last week end should be within 7 days of today
        assert abs((last_end - today).days) <= 7

    def test_week_ranges_contiguous(self, db):
        from api.services.template_service import compliance_trend
        result = compliance_trend("nonexistent", 4, db)
        for i in range(1, len(result)):
            prev_end = date.fromisoformat(result[i - 1]["week_end"])
            curr_start = date.fromisoformat(result[i]["week_start"])
            diff = (curr_start - prev_end).days
            assert diff == 1  # contiguous weeks
