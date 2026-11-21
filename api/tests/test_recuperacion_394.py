"""RECUPERACION-ATLETAS (394): /api/recovery/coach-view con un atleta real."""
from api.models import Group, GroupMember
from api.tests.conftest import login, auth_headers


def test_coach_view_con_atleta(client, db, coach_user, athlete_user):
    g = Group(nombre="G", coach_id=coach_user.id)
    db.add(g)
    db.commit()
    db.add(GroupMember(group_id=g.id, athlete_id=athlete_user.id))
    db.commit()
    tok = login(client, "coach@test.com", "CoachPass123")
    r = client.get("/api/recovery/coach-view", headers=auth_headers(tok))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["n"] == 1
    assert d["athletes"][0]["athlete_id"] == athlete_user.id


def test_coach_view_atleta_sigue_en_403(client, db, athlete_user):
    tok = login(client, "athlete@test.com", "AthlPass123")
    r = client.get("/api/recovery/coach-view", headers=auth_headers(tok))
    assert r.status_code == 403


def test_build_394_y_sello():
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    sw = (root / "sw.js").read_text(encoding="utf8")
    assert "var BUILD_VERSION = '405'" in sw and "'/i18n.js?v=404'" in sw
    assert "i18n.js?v=404" in (root / "recovery.html").read_text(encoding="utf8")
    i18n = (root / "i18n.js").read_text(encoding="utf8")
    assert len(re.findall(r"rcw_load_error:", i18n)) == 3
