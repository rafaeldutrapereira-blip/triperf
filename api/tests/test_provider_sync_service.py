"""Sprint 56 paso 2: sync de actividades Polar/Wahoo. Sin red: el provider se dobla via
registry.get_provider; los crudos salen de los fixtures oficiales de los Sprints 52/53
(solo se cambia la fecha en la COPIA en memoria para caer dentro/fuera de la ventana)."""
import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from api import provider_oauth as po
from api.models import GarminActivity, ProviderConnection
from api.provider_sync_service import sync_provider_user
from api.providers import registry
from api.providers.polar import normalize_polar_exercise
from api.providers.wahoo import WahooProvider, normalize_wahoo_workout
from api.tests.conftest import auth_headers, login

FIX = Path(__file__).parent / "fixtures"
WAHOO_RAW = json.loads((FIX / "wahoo" / "doc_sample_get_workout.json").read_text(encoding="utf-8"))
POLAR_RAW = json.loads((FIX / "polar" / "doc_sample_exercise.json").read_text(encoding="utf-8"))


def _days_ago(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _wahoo(id_, days_ago):
    r = copy.deepcopy(WAHOO_RAW)
    r["id"] = id_
    r["starts"] = _days_ago(days_ago)
    return r


def _polar(id_, days_ago):
    r = copy.deepcopy(POLAR_RAW)
    r["id"] = id_
    r["start_time"] = _days_ago(days_ago)[:19]
    return r


class FakeProvider:
    def __init__(self, name, pages=None, raws=None, exc=None):
        self.name, self.pages, self.raws, self.exc = name, pages or [], raws or [], exc
        self.tokens, self.calls, self.gps = [], [], []

    async def list_activities(self, client, since, page=1, per_page=30):
        self.tokens.append(client)
        self.calls.append(page)
        if self.exc:
            raise self.exc
        if self.name == "polar":
            return self.raws
        return self.pages[page - 1] if page <= len(self.pages) else []

    def get_activity_detail(self, raw, **kw):
        if self.name == "polar":
            return normalize_polar_exercise(raw, **kw)
        return normalize_wahoo_workout(raw, **kw)

    async def download_gps(self, client, activity_id):
        self.gps.append(activity_id)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for p in ("POLAR", "WAHOO"):
        monkeypatch.setenv(f"{p}_ENABLED", "true")
        monkeypatch.setenv(f"{p}_CLIENT_ID", "cid-test")
        monkeypatch.setenv(f"{p}_CLIENT_SECRET", "fake-secret-value-for-tests")


def _use(monkeypatch, fake):
    monkeypatch.setattr(registry, "get_provider", lambda name, db: fake)
    return fake


def _connect(db, user, provider, expires_in=7200):
    po.save_connection(db, user.id, provider,
                       {"access_token": "AT-OLD", "refresh_token": "RT", "expires_in": expires_in})


def _run(db, user, provider, days=30):
    return asyncio.run(sync_provider_user(db, user.id, provider, days=days))


def _acts(db, user):
    return db.query(GarminActivity).filter(GarminActivity.user_id == user.id).all()


def test_wahoo_saves_prefixed_activities(db, athlete_user, monkeypatch):
    _connect(db, athlete_user, "wahoo")
    _use(monkeypatch, FakeProvider("wahoo", pages=[[_wahoo(101, 2), _wahoo(102, 5)]]))
    res = _run(db, athlete_user, "wahoo")
    assert res["ok"] is True and res["fetched"] == 2 and res["saved"] == 2 and res["skipped_dup"] == 0
    ids = sorted(a.activity_id for a in _acts(db, athlete_user))
    assert ids == ["wahoo_101", "wahoo_102"]
    conn = po.get_connection(db, athlete_user.id, "wahoo")
    assert conn.last_sync_status == "ok" and conn.last_sync_saved == 2 and conn.last_sync_at


def test_second_run_is_idempotent(db, athlete_user, monkeypatch):
    _connect(db, athlete_user, "wahoo")
    _use(monkeypatch, FakeProvider("wahoo", pages=[[_wahoo(101, 2), _wahoo(102, 5)]]))
    _run(db, athlete_user, "wahoo")
    res = _run(db, athlete_user, "wahoo")
    assert res["ok"] and res["saved"] == 0 and res["skipped_dup"] == 2
    assert len(_acts(db, athlete_user)) == 2


def test_wahoo_cutoff_drops_old_and_stops_paging(db, athlete_user, monkeypatch):
    _connect(db, athlete_user, "wahoo")
    fake = _use(monkeypatch, FakeProvider("wahoo", pages=[
        [_wahoo(1, 3), _wahoo(2, 200)],       # una vieja se filtra
        [_wahoo(3, 300), _wahoo(4, 400)],     # toda vieja: corta
        [_wahoo(5, 1)],                       # no debe pedirse
    ]))
    res = _run(db, athlete_user, "wahoo", days=30)
    assert res["saved"] == 1 and res["filtered_old"] == 3 and res["fetched"] == 4
    assert [a.activity_id for a in _acts(db, athlete_user)] == ["wahoo_1"]
    assert fake.calls == [1, 2]


def test_wahoo_max_five_pages(db, athlete_user, monkeypatch):
    _connect(db, athlete_user, "wahoo")
    fake = _use(monkeypatch, FakeProvider("wahoo", pages=[[_wahoo(10 + i, 1)] for i in range(8)]))
    res = _run(db, athlete_user, "wahoo")
    assert fake.calls == [1, 2, 3, 4, 5] and res["fetched"] == 5


def test_polar_saves_with_prefix_and_gps_for_new_only(db, athlete_user, monkeypatch):
    _connect(db, athlete_user, "polar", expires_in=31536000)
    fake = _use(monkeypatch, FakeProvider("polar", raws=[_polar("AB1", 400)]))  # vieja: Polar no filtra
    res = _run(db, athlete_user, "polar")
    assert res["ok"] and res["saved"] == 1
    assert [a.activity_id for a in _acts(db, athlete_user)] == ["polar_AB1"]
    assert fake.gps == ["AB1"]
    res2 = _run(db, athlete_user, "polar")
    assert res2["saved"] == 0 and res2["skipped_dup"] == 1 and fake.gps == ["AB1"]


def test_polar_gps_failure_does_not_break_sync(db, athlete_user, monkeypatch):
    _connect(db, athlete_user, "polar")
    fake = _use(monkeypatch, FakeProvider("polar", raws=[_polar("AB2", 1)]))

    async def boom(client, activity_id):
        raise RuntimeError("gpx")
    fake.download_gps = boom
    assert _run(db, athlete_user, "polar")["ok"] is True


def test_cross_origin_duplicate_is_skipped(db, athlete_user, monkeypatch):
    _connect(db, athlete_user, "wahoo")
    raw = _wahoo(7, 2)
    d = normalize_wahoo_workout(raw)
    db.add(GarminActivity(activity_id="12345", user_id=athlete_user.id, sport=d["sport"],
                          date_iso=d["date_iso"], dur_min=d["dur_min"], dist_km=d["dist_km"]))
    db.commit()
    _use(monkeypatch, FakeProvider("wahoo", pages=[[raw]]))
    res = _run(db, athlete_user, "wahoo")
    assert res["saved"] == 0 and res["skipped_dup"] == 1 and len(_acts(db, athlete_user)) == 1


def test_not_connected_touches_nothing(db, athlete_user, monkeypatch):
    called = []
    monkeypatch.setattr(registry, "get_provider", lambda n, d: called.append(n))
    res = _run(db, athlete_user, "wahoo")
    assert res["ok"] is False and res["error"] == "not_connected" and not called
    assert _acts(db, athlete_user) == [] and db.query(ProviderConnection).count() == 0


def test_provider_exception_records_error_state(db, athlete_user, monkeypatch):
    _connect(db, athlete_user, "wahoo")
    _use(monkeypatch, FakeProvider("wahoo", exc=RuntimeError("secret-detail")))
    res = _run(db, athlete_user, "wahoo")
    assert res["ok"] is False and res["error"] == "RuntimeError" and res["saved"] == 0
    conn = po.get_connection(db, athlete_user.id, "wahoo")
    assert conn.last_sync_status == "error" and conn.last_sync_error == "RuntimeError"
    assert "secret-detail" not in (conn.last_sync_error or "")


def test_http_401_maps_to_token_rejected(db, athlete_user, monkeypatch):
    class Resp:
        status_code = 401

    class Err(Exception):
        response = Resp()
    _connect(db, athlete_user, "polar")
    _use(monkeypatch, FakeProvider("polar", exc=Err()))
    assert _run(db, athlete_user, "polar")["error"] == "token_rejected"


def test_missing_refresh_gives_token_invalid(db, athlete_user, monkeypatch):
    po.save_connection(db, athlete_user.id, "wahoo", {"access_token": "AT", "expires_in": 1})
    fake = _use(monkeypatch, FakeProvider("wahoo"))
    res = _run(db, athlete_user, "wahoo")
    assert res["error"] == "token_invalid" and fake.calls == []
    assert po.get_connection(db, athlete_user.id, "wahoo").last_sync_status == "error"


def test_expired_wahoo_token_is_refreshed_before_listing(db, athlete_user, monkeypatch):
    _connect(db, athlete_user, "wahoo", expires_in=1)  # dentro del margen de 60s -> refresca

    async def auth(self, user_id, **creds):
        assert creds["refresh_token"] == "RT"
        self.last_token_response = {"access_token": "AT-NEW", "refresh_token": "RT2", "expires_in": 7200}
        return "AT-NEW"
    monkeypatch.setattr(WahooProvider, "authenticate", auth)
    fake = _use(monkeypatch, FakeProvider("wahoo", pages=[[_wahoo(1, 1)]]))
    res = _run(db, athlete_user, "wahoo")
    assert res["ok"] and set(fake.tokens) == {"AT-NEW"}
    assert po.get_connection(db, athlete_user.id, "wahoo").last_sync_status == "ok"


@pytest.mark.parametrize("provider", ["polar", "wahoo"])
def test_endpoint_sync_without_connection_is_404(client, athlete_user, provider):
    t = login(client, "athlete@test.com", "AthlPass123")
    client.cookies.clear()
    r = client.post(f"/api/integrations/{provider}/sync", headers=auth_headers(t))
    assert r.status_code == 404


def test_endpoint_sync_flag_off_is_404(client, athlete_user, monkeypatch):
    monkeypatch.setenv("WAHOO_ENABLED", "false")
    t = login(client, "athlete@test.com", "AthlPass123")
    client.cookies.clear()
    assert client.post("/api/integrations/wahoo/sync", headers=auth_headers(t)).status_code == 404


def test_endpoint_sync_clamps_days_and_returns_dict(client, db, athlete_user, monkeypatch):
    _connect(db, athlete_user, "wahoo")
    seen = {}

    async def fake_sync(db_, user_id, provider, days=30):
        seen["days"] = days
        return {"ok": True, "provider": provider, "fetched": 0, "saved": 0, "skipped_dup": 0}
    monkeypatch.setattr("api.provider_sync_service.sync_provider_user", fake_sync)
    t = login(client, "athlete@test.com", "AthlPass123")
    client.cookies.clear()
    r = client.post("/api/integrations/wahoo/sync?days=9999", headers=auth_headers(t))
    assert r.status_code == 200 and r.json()["ok"] is True and seen["days"] == 365
    client.post("/api/integrations/wahoo/sync?days=0", headers=auth_headers(t))
    assert seen["days"] == 1
