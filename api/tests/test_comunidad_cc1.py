"""CC1: privacidad del feed (GET /community/activity-feed).

Fija: visibilidad del post, privacidad de salud (recovery/training_load) de
actividades ajenas, acceso total del dueno y paginacion limit/offset.
"""
import json
import pytest

from .conftest import login, auth_headers
from api.models import (
    Follow, GarminActivity, CommunityPost, RecoveryScore, GarminTrainingLoad,
)

DAY = "2026-08-10"


@pytest.fixture(autouse=True)
def _plans(db, athlete_user, coach_user):
    athlete_user.plan_nivel = "agegroup"
    coach_user.plan_nivel = "agegroup"
    db.commit()


def _setup(db, athlete, coach, visibility="followers", act_id="cc1-a", day=DAY):
    """coach sigue a athlete; athlete tiene una actividad con post, recovery y carga."""
    if not db.query(Follow).filter_by(follower_id=coach.id, followed_id=athlete.id).first():
        db.add(Follow(follower_id=coach.id, followed_id=athlete.id))
    act = GarminActivity(user_id=athlete.id, activity_id=act_id, name="Run",
                         sport="run", date_iso=day, dur_min=45, dist_km=8.0, tss=50)
    db.add(act)
    db.flush()
    db.add(CommunityPost(user_id=athlete.id, activity_id=act.id, visibility=visibility))
    if not db.query(RecoveryScore).filter_by(user_id=athlete.id, date_iso=DAY).first():
        db.add(RecoveryScore(user_id=athlete.id, date_iso=DAY, score=77, level="good", color="#10B981"))
        db.add(GarminTrainingLoad(user_id=athlete.id, date_iso=DAY, ctl=60.0, atl=55.0, tsb=5.0))
    db.commit()
    return act


def _feed(client, email, pw, qs=""):
    tok = login(client, email, pw)
    r = client.get("/api/community/activity-feed" + qs, headers=auth_headers(tok))
    assert r.status_code == 200
    return r.json()


def _coach_feed(client, qs=""):
    return _feed(client, "coach@test.com", "CoachPass123", qs)


def _athlete_feed(client, qs=""):
    return _feed(client, "athlete@test.com", "AthlPass123", qs)


@pytest.mark.parametrize("vis", ["private", "coach_only"])
def test_follower_does_not_see_restricted_post(client, db, athlete_user, coach_user, vis):
    _setup(db, athlete_user, coach_user, visibility=vis)
    assert [c for c in _coach_feed(client)["feed"] if c["activity_id"] == "cc1-a"] == []


def test_owner_sees_own_private_post_with_everything(client, db, athlete_user, coach_user):
    _setup(db, athlete_user, coach_user, visibility="private")
    card = [c for c in _athlete_feed(client)["feed"] if c["activity_id"] == "cc1-a"][0]
    assert card["recovery"]["score"] == 77
    assert card["training_load"]["ctl"] == 60.0
    assert card["training_load"]["tsb"] == 5.0


@pytest.mark.parametrize("vis", ["public", "followers"])
def test_follower_sees_health_when_allowed(client, db, athlete_user, coach_user, vis):
    _setup(db, athlete_user, coach_user, visibility=vis)
    card = [c for c in _coach_feed(client)["feed"] if c["activity_id"] == "cc1-a"][0]
    assert card["recovery"]["score"] == 77
    assert card["training_load"]["ctl"] == 60.0


@pytest.mark.parametrize("prefs", [{"share_details": False}, {"share_hr": False}])
def test_follower_does_not_get_health_if_owner_privacy_denies(client, db, athlete_user, coach_user, prefs):
    athlete_user.community_share_prefs = json.dumps(prefs)
    _setup(db, athlete_user, coach_user, visibility="public")
    card = [c for c in _coach_feed(client)["feed"] if c["activity_id"] == "cc1-a"][0]
    assert set(card["recovery"]) >= {"score", "level", "color", "label", "suggestion"}
    assert all(v is None for v in card["recovery"].values())
    assert card["training_load"] == {"ctl": None, "tsb": None, "atl": None}


def test_privacy_prefs_do_not_affect_owner(client, db, athlete_user, coach_user):
    athlete_user.community_share_prefs = json.dumps({"share_details": False, "share_hr": False})
    _setup(db, athlete_user, coach_user, visibility="public")
    card = [c for c in _athlete_feed(client)["feed"] if c["activity_id"] == "cc1-a"][0]
    assert card["recovery"]["score"] == 77 and card["training_load"]["tsb"] == 5.0


def test_pagination_offset_over_visible_set(client, db, athlete_user, coach_user):
    # 5 visibles + 1 privada intercalada: la privada no debe consumir pagina.
    for i in range(5):
        _setup(db, athlete_user, coach_user, act_id="cc1-p%d" % i, day="2026-08-0%d" % (i + 1))
    _setup(db, athlete_user, coach_user, visibility="private", act_id="cc1-hidden", day="2026-08-03")

    p1 = _coach_feed(client, "?limit=2&offset=0")
    p2 = _coach_feed(client, "?limit=2&offset=2")
    p3 = _coach_feed(client, "?limit=2&offset=4")
    assert (p1["count"], p2["count"], p3["count"]) == (2, 2, 1)
    assert (p1["has_more"], p2["has_more"], p3["has_more"]) == (True, True, False)
    assert p1["next_offset"] == 2 and p3["next_offset"] is None
    assert (p2["limit"], p2["offset"]) == (2, 2)
    ids = [c["activity_id"] for p in (p1, p2, p3) for c in p["feed"]]
    assert len(ids) == len(set(ids)) == 5
    assert "cc1-hidden" not in ids
