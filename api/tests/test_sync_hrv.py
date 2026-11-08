"""SYNC-HRV: el HRV de intervals.icu aterriza en garmin_health_daily, se rellena tarde
y jamas se pisa un valor existente con vacio."""
from unittest.mock import MagicMock

from api import garmin_pull_service as gps
from api.models import GarminHealthDaily
from api.tests.test_intervals_sync import _connect, _patch, _run

DAY = "2026-11-07"


def _well(**kw):
    return dict({"id": DAY, "restingHR": 49, "hrv": 63, "sleepSecs": 27240}, **kw)


def test_wellness_con_hrv_crea_fila_con_hrv(db, athlete_user, monkeypatch):
    _connect(db, athlete_user)
    _patch(monkeypatch, well=[_well()])
    _run(db, athlete_user)
    hd = db.query(GarminHealthDaily).one()
    assert hd.hrv_last_night == 63 and hd.resting_hr == 49


def test_fila_sin_hrv_se_rellena_en_sync_posterior(db, athlete_user, monkeypatch):
    _connect(db, athlete_user)
    db.add(GarminHealthDaily(user_id=athlete_user.id, date_iso=DAY, resting_hr=49))
    db.commit()
    _patch(monkeypatch, well=[_well(hrv=None)])  # primer sync: el HRV aun no llego a intervals
    _run(db, athlete_user)
    assert db.query(GarminHealthDaily).one().hrv_last_night is None
    _patch(monkeypatch, well=[_well()])  # llego tarde
    _run(db, athlete_user)
    db.expire_all()
    assert db.query(GarminHealthDaily).one().hrv_last_night == 63


def test_hrv_cero_guardado_no_bloquea_el_relleno(db, athlete_user, monkeypatch):
    _connect(db, athlete_user)
    db.add(GarminHealthDaily(user_id=athlete_user.id, date_iso=DAY, hrv_last_night=0.0))
    db.commit()
    _patch(monkeypatch, well=[_well()])
    _run(db, athlete_user)
    db.expire_all()
    assert db.query(GarminHealthDaily).one().hrv_last_night == 63


def test_fila_con_hrv_no_se_pisa_ni_con_vacio_ni_con_otro_valor(db, athlete_user, monkeypatch):
    _connect(db, athlete_user)
    db.add(GarminHealthDaily(user_id=athlete_user.id, date_iso=DAY, hrv_last_night=71.0))
    db.commit()
    for hrv in (None, 0, 99):
        _patch(monkeypatch, well=[_well(hrv=hrv)])
        _run(db, athlete_user)
        db.expire_all()
        assert db.query(GarminHealthDaily).one().hrv_last_night == 71.0


def test_sin_scope_wellness_se_reporta_no_en_silencio(db, athlete_user, monkeypatch):
    _connect(db, athlete_user, scope="ACTIVITY:READ")
    _patch(monkeypatch, well=[_well()])
    r = _run(db, athlete_user)
    assert r["wellness_skipped"] == "sin_scope"
    assert db.query(GarminHealthDaily).count() == 0


def test_sync_garmin_dispara_wellness_de_intervals(monkeypatch):
    called = {}

    async def fake(db, user_id, days=90):
        called["args"] = (user_id, days)
        return {"status": "ok"}

    from api import intervals_sync_service as iss
    monkeypatch.setattr(iss, "sync_intervals_user", fake)
    monkeypatch.setenv("INTERVALS_READ_ENABLED", "1")
    gps._sync_intervals_wellness_after_garmin("u1", MagicMock())
    assert called["args"] == ("u1", gps.INTERVALS_FILL_DAYS)

    called.clear()
    monkeypatch.delenv("INTERVALS_READ_ENABLED")
    gps._sync_intervals_wellness_after_garmin("u1", MagicMock())
    assert not called  # flag apagado: no hace nada


def test_fallo_de_intervals_no_rompe_el_sync_de_garmin(monkeypatch):
    async def boom(db, user_id, days=90):
        raise RuntimeError("x")

    from api import intervals_sync_service as iss
    monkeypatch.setattr(iss, "sync_intervals_user", boom)
    monkeypatch.setenv("INTERVALS_READ_ENABLED", "1")
    gps._sync_intervals_wellness_after_garmin("u1", MagicMock())  # no lanza
