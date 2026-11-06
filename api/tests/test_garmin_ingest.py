"""Ingestor Garmin fase B: procesador de la bandeja garmin_push_payloads (payloads sinteticos)."""
import json
from datetime import datetime, timedelta

from api import garmin_ingest as gi
from api.models import (
    GarminActivity, GarminHealthDaily, GarminOAuthToken, GarminPushPayload, GarminSleepSession,
)

T0 = datetime(2026, 11, 1, 8, 0, 0)
START = 1793520000  # 2026-11-01 08:00:00 UTC


def _connect(db, user):
    db.add(GarminOAuthToken(user_id=user.id, garmin_user_id="g-1", access_token="x"))
    db.commit()


def _push(db, ptype, items, user_id, offset=0):
    row = GarminPushPayload(payload_type=ptype, user_id=user_id, received_at=T0 + timedelta(seconds=offset),
                            payload_json=json.dumps({ptype: items}), processed=False)
    db.add(row)
    db.commit()
    return row.id


ACTIVITY = {"userId": "g-1", "summaryId": "s-77", "activityId": 7700001, "activityName": "Rodaje",
            "activityType": "RUNNING", "startTimeInSeconds": START, "startTimeOffsetInSeconds": -10800,
            "durationInSeconds": 3000, "distanceInMeters": 10000.0, "averageSpeedInMetersPerSecond": 3.33,
            "averageHeartRateInBeatsPerMinute": 150, "activeKilocalories": 600,
            "totalElevationGainInMeters": 45.0}
SLEEP = {"userId": "g-1", "summaryId": "sl-1", "calendarDate": "2026-11-01", "startTimeInSeconds": START - 30000,
         "durationInSeconds": 27000, "deepSleepDurationInSeconds": 5400, "lightSleepDurationInSeconds": 14400,
         "remSleepInSeconds": 5400, "awakeDurationInSeconds": 1800,
         "overallSleepScore": {"value": 82, "qualifierKey": "GOOD"}}
DAILY = {"userId": "g-1", "summaryId": "d-1", "calendarDate": "2026-11-01", "steps": 9000,
         "activeKilocalories": 700, "restingHeartRateInBeatsPerMinute": 48, "averageStressLevel": 31}


def test_activity_creates_one_and_is_idempotent(db, athlete_user):
    _connect(db, athlete_user)
    pid = _push(db, "activities", [ACTIVITY], athlete_user.id)
    s = gi.process_pending(db)
    assert s["processed"] == 1 and s["written"] == 1
    acts = db.query(GarminActivity).all()
    assert len(acts) == 1
    a = acts[0]
    assert a.activity_id == "7700001" and a.sport == "run" and a.dur_min == 50
    assert a.dist_km == 10.0 and a.date_iso == "2026-11-01" and a.avg_hr == 150
    # re-procesar el mismo payload (forzando processed=False) no duplica
    row = db.get(GarminPushPayload, pid)
    row.processed = False
    db.commit()
    gi.process_pending(db)
    assert db.query(GarminActivity).count() == 1
    # y un segundo payload con el mismo activityId tampoco
    _push(db, "activities", [ACTIVITY], athlete_user.id, offset=5)
    gi.process_pending(db)
    assert db.query(GarminActivity).count() == 1


def test_sleep_and_daily_write_destination_tables(db, athlete_user):
    _connect(db, athlete_user)
    _push(db, "sleeps", [SLEEP], athlete_user.id)
    _push(db, "dailies", [DAILY], athlete_user.id, offset=1)
    gi.process_pending(db)
    sl = db.query(GarminSleepSession).one()
    assert sl.total_min == 450 and sl.deep_min == 90 and sl.rem_min == 90 and sl.sleep_score == 82
    hd = db.query(GarminHealthDaily).one()
    assert hd.steps == 9000 and hd.resting_hr == 48 and hd.avg_stress == 31
    # idempotencia
    db.query(GarminPushPayload).update({"processed": False})
    db.commit()
    gi.process_pending(db)
    assert db.query(GarminSleepSession).count() == 1 and db.query(GarminHealthDaily).count() == 1


def test_unknown_type_marked_processed(db, athlete_user):
    _connect(db, athlete_user)
    _push(db, "mysteryType", [{"userId": "g-1", "x": 1}], athlete_user.id)
    s = gi.process_pending(db)
    assert s["processed"] == 1 and s["failed"] == 0
    row = db.query(GarminPushPayload).one()
    assert row.processed is True and row.error is None
    assert db.query(GarminActivity).count() == 0


def test_user_none_writes_nothing(db, athlete_user):
    _connect(db, athlete_user)
    _push(db, "activities", [ACTIVITY], None)
    s = gi.process_pending(db)
    assert s["processed"] == 1
    assert db.query(GarminActivity).count() == 0
    assert db.query(GarminPushPayload).one().processed is True


def test_disconnected_user_writes_nothing(db, athlete_user):
    _push(db, "activities", [ACTIVITY], athlete_user.id)  # sin token oficial
    gi.process_pending(db)
    assert db.query(GarminActivity).count() == 0
    assert db.query(GarminPushPayload).one().processed is True


def test_corrupt_payload_does_not_block_next(db, athlete_user):
    _connect(db, athlete_user)
    bad = GarminPushPayload(payload_type="activities", user_id=athlete_user.id, received_at=T0,
                            payload_json="{no es json", processed=False)
    db.add(bad)
    db.commit()
    _push(db, "activities", [ACTIVITY], athlete_user.id, offset=10)
    s = gi.process_pending(db)
    assert s["failed"] == 1 and s["processed"] == 1
    assert db.query(GarminActivity).count() == 1
    db.refresh(bad)
    assert bad.processed is False and bad.error
    # un fallido no se reintenta (ni acapara el lote) salvo retry_failed
    assert gi.process_pending(db)["selected"] == 0
    assert gi.process_pending(db, retry_failed=True)["failed"] == 1


def test_batch_limit_and_order(db, athlete_user):
    _connect(db, athlete_user)
    for i in range(5):
        _push(db, "dailies", [dict(DAILY, calendarDate=f"2026-10-{10 + i}")], athlete_user.id, offset=i)
    s = gi.process_pending(db, limit=3)
    assert s["selected"] == 3
    assert db.query(GarminHealthDaily).count() == 3
    assert gi.process_pending(db)["selected"] == 2
