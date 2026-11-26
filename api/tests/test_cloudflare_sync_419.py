"""CLOUDFLARE-SYNC (BUILD 419): pull paralelo de las 7 ventanas de 24 h. Red mockeada con latencia."""
import threading
import time
from unittest.mock import patch

from api import garmin_official as go
from api.tests.test_sync_conexiones_379 import BASE, TOKENS, _act, _h, configured  # noqa: F401


def _by_window(delay=0.0, fail=None, calls=None):
    """Mock de _get_activities_window: una actividad distinta por ventana (id = start)."""
    def fake(token, a, b):
        if calls is not None:
            calls.append((a, b))
        time.sleep(delay)
        if fail and fail(a, b):
            raise go.GarminOfficialError("Garmin no respondio (ReadTimeout)")
        return [_act(a, 1763100000)]
    return fake


def test_paralelo_trae_lo_mismo_y_en_el_mismo_orden_que_el_secuencial():
    calls = []
    with patch.object(go, "_get_activities_window", side_effect=_by_window(0.02, calls=calls)):
        par = go.fetch_recent_activities("tok")
    ids = [x["activityId"] for x in par]
    # una actividad por ventana, las 7 ventanas contiguas de 24 h, mas reciente primero (como el secuencial)
    assert len(ids) == 7 and ids == sorted(ids, reverse=True)
    assert sorted(ids) == sorted(a for a, _ in calls)
    assert all(b - a == go.PULL_WINDOW_S for a, b in calls)


def test_pool_acotado_y_paralelo_real():
    active, peak, lock = 0, 0, threading.Lock()

    def fake(token, a, b):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return []
    with patch.object(go, "_get_activities_window", side_effect=fake):
        go.fetch_recent_activities("tok")
    assert 1 < peak <= go.PULL_WORKERS


def test_cada_ventana_conserva_el_timeout_de_20s():
    seen = {}

    class R:
        status_code = 200
        def json(self): return []
    def fake_get(url, **kw):
        seen["timeout"] = kw["timeout"]
        return R()
    with patch.object(go.httpx, "get", side_effect=fake_get):
        go._get_activities_window("t", 1, 2)
    assert seen["timeout"] == 20


def test_ventana_fallida_no_pierde_las_demas_ni_esconde_la_causa():
    # falla exactamente la ventana indice 2
    end = int(go._now().replace(tzinfo=go.timezone.utc).timestamp())
    target = end - 2 * go.PULL_WINDOW_S - go.PULL_WINDOW_S
    with patch.object(go, "_get_activities_window",
                      side_effect=_by_window(fail=lambda a, b: abs(a - target) <= 2)):
        items, errors, timings = go.fetch_recent_activities_detailed("tok")
    assert len(items) == 6 and len(errors) == 1 and errors[0][0] == 2
    assert "ReadTimeout" in str(errors[0][1]) and len(timings) == 7


def test_endpoint_guarda_parciales_y_reporta_la_causa(client, db, athlete_user, configured):
    from api.models import GarminActivity
    go.save_tokens(db, athlete_user.id, TOKENS, "G-1")
    end = int(go._now().replace(tzinfo=go.timezone.utc).timestamp())
    target = end - go.PULL_WINDOW_S
    fake = _by_window(fail=lambda a, b: abs(a - target) <= 2)
    with patch.object(go, "_get_activities_window", side_effect=fake):
        r = client.post(f"{BASE}/sync", headers=_h(client))
    assert r.status_code == 502 and r.json()["status"] == "pull_timeout"
    assert db.query(GarminActivity).filter(GarminActivity.user_id == athlete_user.id).count() >= 1


def test_endpoint_responde_dentro_del_limite_en_el_caso_normal(client, db, athlete_user, configured):
    """7 ventanas de 0,3 s: en paralelo ~0,6 s (secuencial serian 2,1 s). Escala 1:100 de 20 s/ventana."""
    go.save_tokens(db, athlete_user.id, TOKENS, "G-1")
    with patch.object(go, "_get_activities_window", side_effect=_by_window(0.3)):
        t0 = time.monotonic()
        r = client.post(f"{BASE}/sync", headers=_h(client))
        dur = time.monotonic() - t0
    assert r.status_code == 200
    assert dur < 7 * 0.3 * 0.7  # claramente por debajo del tiempo secuencial


def test_peor_caso_teorico_bajo_el_limite():
    rondas = -(-go.PULL_MAX_DAYS // go.PULL_WORKERS)
    assert rondas * 20 <= 90
