"""SALUD-AL-DIA (386): la salud de intervals.icu llega por un job programado, no solo por
el pull legacy de Garmin ni por un boton. La regla dura (no pisar con vacio) se mantiene."""
import pathlib
import re

import pytest

from api import scheduler
from api.models import GarminHealthDaily, User
from api.tests.conftest import TestingSessionLocal
from api.tests.test_intervals_sync import _connect, _patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
D1, D2 = "2026-11-12", "2026-11-13"


@pytest.fixture
def job_db(monkeypatch):
    import api.database as dbmod
    monkeypatch.setattr(dbmod, "SessionLocal", TestingSessionLocal)
    monkeypatch.setenv("INTERVALS_READ_ENABLED", "1")


def test_job_registrado_cada_3h_junto_al_del_plan():
    src = (ROOT / "api" / "scheduler.py").read_text(encoding="utf8")
    assert 'id="intervals_data_sync"' in src and 'id="intervals_plan_sync"' in src
    assert "_background_intervals_data_sync_all," in src


def test_job_trae_hrv_y_sella_last_sync(db, athlete_user, monkeypatch, job_db):
    _connect(db, athlete_user)
    _patch(monkeypatch, well=[{"id": D2, "restingHR": 48, "hrv": 63, "steps": 19477}])
    assert athlete_user.intervals_last_sync_at is None
    scheduler._background_intervals_data_sync_all()
    db.expire_all()
    hd = db.query(GarminHealthDaily).filter_by(user_id=athlete_user.id, date_iso=D2).one()
    assert hd.hrv_last_night == 63 and hd.resting_hr == 48 and hd.steps == 19477
    assert db.query(User).get(athlete_user.id).intervals_last_sync_at is not None


def test_job_no_sella_si_hay_errores(db, athlete_user, monkeypatch, job_db):
    from unittest.mock import AsyncMock
    from api import intervals_connector as ic
    _connect(db, athlete_user)
    _patch(monkeypatch)
    monkeypatch.setattr(ic, "fetch_wellness", AsyncMock(side_effect=ic.IntervalsError("boom")))
    scheduler._background_intervals_data_sync_all()
    db.expire_all()
    assert db.query(User).get(athlete_user.id).intervals_last_sync_at is None


def test_job_apagado_sin_flag_no_llama_a_intervals(db, athlete_user, monkeypatch):
    monkeypatch.delenv("INTERVALS_READ_ENABLED", raising=False)
    _connect(db, athlete_user)
    fa, fw = _patch(monkeypatch, well=[{"id": D2, "hrv": 63}])
    scheduler._background_intervals_data_sync_all()
    assert fa.await_count == 0 and fw.await_count == 0


def test_job_ignora_usuarios_sin_intervals_y_sigue_ante_fallo(db, athlete_user, monkeypatch, job_db):
    # sin token -> no se consulta; con token y fallo inesperado -> no revienta el job
    fa, _ = _patch(monkeypatch)
    scheduler._background_intervals_data_sync_all()
    assert fa.await_count == 0
    _connect(db, athlete_user)
    from api import intervals_sync_service as iss

    async def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(iss, "sync_intervals_user", boom)
    scheduler._background_intervals_data_sync_all()  # no lanza


def test_job_jamas_pisa_valor_con_vacio_ni_inventa(db, athlete_user, monkeypatch, job_db):
    _connect(db, athlete_user)
    db.add(GarminHealthDaily(user_id=athlete_user.id, date_iso=D1, hrv_last_night=79.0))
    db.commit()
    # D1: intervals trae HRV vacio; D2: sin HRV -> debe quedar NULL (no se repite el ultimo)
    _patch(monkeypatch, well=[{"id": D1, "restingHR": 48, "hrv": None},
                              {"id": D2, "restingHR": 48}])
    scheduler._background_intervals_data_sync_all()
    db.expire_all()
    rows = {r.date_iso: r for r in db.query(GarminHealthDaily).filter_by(user_id=athlete_user.id)}
    assert rows[D1].hrv_last_night == 79.0
    assert rows[D2].hrv_last_night is None


def test_build_386_en_sw():
    sw = (ROOT / "sw.js").read_text(encoding="utf8")
    assert int(re.search(r"var BUILD_VERSION = '(\d+)';", sw).group(1)) >= 386
