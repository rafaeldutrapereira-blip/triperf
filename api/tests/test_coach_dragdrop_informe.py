"""DRAGDROP-INFORME (BUILD 384): mover asignaciones (fecha/atleta) con reenvio a
intervals.icu, PDF real del informe y enlace publico revocable."""
import json
import pathlib
import re
from unittest.mock import AsyncMock

import pytest

from .conftest import login, auth_headers
from .test_coach_destino_multiple import _mk_athletes
from api import intervals_connector as ic
from api.models import AssignedWorkout, AthleteReportShare, GarminTrainingLoad, WorkoutTemplate

ROOT = pathlib.Path(__file__).resolve().parents[2]
BIKE = [{"type": "steady", "duration": 600, "power": 0.75}]


def _h(client):
    return auth_headers(login(client, "coach@test.com", "CoachPass123"))


def _mk(db, coach, athlete, date="2026-12-07", status=None, event_id=None, blocks=BIKE):
    t = WorkoutTemplate(coach_id=coach.id, sport="bike", nombre="Rodaje", dur_min=60, tss=50,
                        blocks_json=json.dumps(blocks))
    db.add(t); db.flush()
    a = AssignedWorkout(template_id=t.id, athlete_id=athlete.id, date_iso=date,
                        intervals_push_status=status, intervals_push_event_id=event_id)
    db.add(a); db.commit(); db.refresh(a)
    return a


def _get(db, aid):
    db.expire_all()
    return db.query(AssignedWorkout).filter(AssignedWorkout.id == aid).first()


@pytest.fixture
def two(db, coach_user):
    return _mk_athletes(db, coach_user, 2)


@pytest.fixture
def send(monkeypatch):
    calls = []

    async def _fake(**kw):
        calls.append({"user": kw["user"].id, "date": kw["date_iso"], "event_id": kw.get("event_id")})
        return {"ok": True, "event_id": kw.get("event_id") or "NEW1"}

    monkeypatch.setattr(ic, "send_workout_event", AsyncMock(side_effect=_fake))
    dele = AsyncMock(return_value=True)
    monkeypatch.setattr(ic, "delete_workout_event", dele)
    monkeypatch.setattr(ic, "read_access_token", lambda u: "tok")
    return type("S", (), {"calls": calls, "delete": dele})


# ── /calendar/move ────────────────────────────────────────────────────────────
def test_calendar_trae_id_de_asignacion(client, db, coach_user, two):
    from api.models import Group, GroupMember
    g = Group(coach_id=coach_user.id, nombre="G"); db.add(g); db.flush()
    two[0].rol = "atleta"  # el calendario filtra por este rol
    db.add(GroupMember(group_id=g.id, athlete_id=two[0].id)); db.commit()
    a = _mk(db, coach_user, two[0])
    r = client.get("/api/coach/calendar?start=2026-12-07&end=2026-12-07", headers=_h(client))
    assert r.status_code == 200
    assert r.json()[0]["athletes"][0]["assignments"][0]["id"] == a.id


def test_mover_fecha(client, db, coach_user, two):
    a = _mk(db, coach_user, two[0])
    r = client.patch("/api/coach/calendar/move", headers=_h(client),
                     json={"assignment_id": a.id, "new_date_iso": "2026-12-09"})
    assert r.status_code == 200 and r.json()["new_date"] == "2026-12-09"
    row = _get(db, a.id)
    assert row.date_iso == "2026-12-09" and row.athlete_id == two[0].id


def test_mover_fecha_y_atleta(client, db, coach_user, two):
    a = _mk(db, coach_user, two[0])
    r = client.patch("/api/coach/calendar/move", headers=_h(client),
                     json={"assignment_id": a.id, "new_date_iso": "2026-12-10", "new_athlete_id": two[1].id})
    assert r.status_code == 200
    row = _get(db, a.id)
    assert (row.date_iso, row.athlete_id) == ("2026-12-10", two[1].id)


def test_mover_a_atleta_ajeno_403_sin_cambios(client, db, coach_user, two):
    from .test_coach_destino_multiple import foreign  # noqa: F401
    from api.auth import hash_password
    from api.models import CoachAthlete, User
    other = User(email="c2@test.com", nombre="O", password_hash=hash_password("Passw0rd123"),
                 rol="coach", plan_nivel="basico", activo=True)
    aj = User(email="aj@test.com", nombre="Aj", password_hash=hash_password("Passw0rd123"),
              rol="athlete", plan_nivel="basico", activo=True)
    db.add_all([other, aj]); db.flush()
    db.add(CoachAthlete(coach_id=other.id, athlete_id=aj.id, status="active")); db.commit()
    a = _mk(db, coach_user, two[0])
    r = client.patch("/api/coach/calendar/move", headers=_h(client),
                     json={"assignment_id": a.id, "new_date_iso": "2026-12-10", "new_athlete_id": aj.id})
    assert r.status_code == 403
    row = _get(db, a.id)
    assert row.athlete_id == two[0].id


def test_mover_404_422_400(client, db, coach_user, two):
    a = _mk(db, coach_user, two[0])
    h = _h(client)
    assert client.patch("/api/coach/calendar/move", headers=h,
                        json={"assignment_id": "no-existe", "new_date_iso": "2026-12-09"}).status_code == 404
    assert client.patch("/api/coach/calendar/move", headers=h,
                        json={"new_date_iso": "2026-12-09"}).status_code == 422
    assert client.patch("/api/coach/calendar/move", headers=h,
                        json={"assignment_id": a.id, "new_date_iso": "no-es-fecha"}).status_code == 400
    assert _get(db, a.id).date_iso == "2026-12-07"


# ── reenvio a intervals.icu ───────────────────────────────────────────────────
def test_mover_con_push_ok_reenvia_con_mismo_event_id(client, db, coach_user, two, send):
    two[0].intervals_access_token = "x"; db.commit()
    a = _mk(db, coach_user, two[0], status="ok", event_id="EV9")
    r = client.patch("/api/coach/calendar/move", headers=_h(client),
                     json={"assignment_id": a.id, "new_date_iso": "2026-12-11"})
    assert r.status_code == 200 and r.json()["intervals_push_status"] == "ok"
    assert send.calls == [{"user": two[0].id, "date": "2026-12-11", "event_id": "EV9"}]
    assert _get(db, a.id).intervals_push_event_id == "EV9"


def test_mover_con_push_fallido_queda_failed_visible(client, db, coach_user, two, monkeypatch):
    two[0].intervals_access_token = "x"; db.commit()
    monkeypatch.setattr(ic, "read_access_token", lambda u: "tok")
    monkeypatch.setattr(ic, "send_workout_event",
                        AsyncMock(side_effect=ic.IntervalsError("intervals caido")))
    a = _mk(db, coach_user, two[0], status="ok", event_id="EV9")
    r = client.patch("/api/coach/calendar/move", headers=_h(client),
                     json={"assignment_id": a.id, "new_date_iso": "2026-12-11"})
    assert r.status_code == 200
    assert r.json()["intervals_push_status"] == "failed"
    assert "intervals caido" in r.json()["intervals_push_error"]
    row = _get(db, a.id)
    assert row.date_iso == "2026-12-11" and row.intervals_push_status == "failed"


@pytest.mark.parametrize("status", [None, "pending", "skipped", "failed"])
def test_mover_sin_push_ok_no_reintenta(client, db, coach_user, two, send, status):
    a = _mk(db, coach_user, two[0], status=status)
    r = client.patch("/api/coach/calendar/move", headers=_h(client),
                     json={"assignment_id": a.id, "new_date_iso": "2026-12-11"})
    assert r.status_code == 200 and r.json()["intervals_push_status"] is None
    assert send.calls == []
    assert _get(db, a.id).intervals_push_status == status


def test_mover_a_otro_atleta_borra_evento_viejo_y_crea_nuevo(client, db, coach_user, two, send):
    for u in two:
        u.intervals_access_token = "x"
    db.commit()
    a = _mk(db, coach_user, two[0], status="ok", event_id="EV9")
    r = client.patch("/api/coach/calendar/move", headers=_h(client),
                     json={"assignment_id": a.id, "new_date_iso": "2026-12-11", "new_athlete_id": two[1].id})
    assert r.status_code == 200
    assert send.delete.await_count == 1
    assert send.calls == [{"user": two[1].id, "date": "2026-12-11", "event_id": None}]
    assert _get(db, a.id).intervals_push_event_id == "NEW1"


# ── PDF ───────────────────────────────────────────────────────────────────────
def _seed_report(db, coach, athlete):
    _mk(db, coach, athlete, date="2026-12-07")
    db.add(GarminTrainingLoad(user_id=athlete.id, date_iso="2026-12-13", ctl=42.5, atl=50.1, tsb=-7.6, acwr=1.23))
    athlete.race_goal_name = "Ironman Pucon"; athlete.race_goal_date = "2027-01-30"
    db.commit()


def test_pdf_es_un_pdf_real_con_los_datos(client, db, coach_user, two):
    _seed_report(db, coach_user, two[0])
    r = client.get(f"/api/coach/report/athlete/{two[0].id}/pdf?start=2026-12-01&end=2026-12-13", headers=_h(client))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    assert r.content[:5] == b"%PDF-" and r.content.rstrip().endswith(b"%%EOF")
    # el texto del PDF va comprimido: se verifica con el constructor sobre el mismo reporte
    from api.report_pdf import build_report_pdf
    from api.routes.coach_routes import build_athlete_report
    rep = build_athlete_report(db, coach_user.id, two[0].id, "2026-12-01", "2026-12-13")
    assert rep.ctl == 42.5 and rep.acwr == 1.23 and rep.sessions_total == 1
    assert build_report_pdf(rep)[:5] == b"%PDF-"


def test_pdf_sin_dato_no_inventa_cifras(db, coach_user, two):
    from api.report_pdf import build_report_pdf
    from api.routes.coach_routes import build_athlete_report
    rep = build_athlete_report(db, coach_user.id, two[0].id, "2026-12-01", "2026-12-13")
    assert rep.ctl is None and rep.acwr is None
    assert build_report_pdf(rep)[:5] == b"%PDF-"


def test_pdf_periodo_invalido_400_y_atleta_ajeno_403(client, db, coach_user, two):
    h = _h(client)
    assert client.get(f"/api/coach/report/athlete/{two[0].id}/pdf?start=x&end=2026-12-13", headers=h).status_code == 400
    assert client.get(f"/api/coach/report/athlete/{two[0].id}/pdf?start=2026-12-20&end=2026-12-13", headers=h).status_code == 400
    assert client.get("/api/coach/report/athlete/otro/pdf?start=2026-12-01&end=2026-12-13", headers=h).status_code in (403, 404)


def test_pdf_requiere_login(client, two):
    assert client.get(f"/api/coach/report/athlete/{two[0].id}/pdf?start=2026-12-01&end=2026-12-13").status_code in (401, 403)


# ── enlace compartido ─────────────────────────────────────────────────────────
def test_enlace_publico_abre_sin_login_y_revocado_no(client, db, coach_user, two):
    _seed_report(db, coach_user, two[0])
    h = _h(client)
    r = client.post(f"/api/coach/report/athlete/{two[0].id}/share", headers=h,
                    json={"start": "2026-12-01", "end": "2026-12-13"})
    assert r.status_code == 200
    sh = r.json()
    tok = sh["share_token"]
    assert sh["share_url"] == f"/shared_report.html?t={tok}"
    # idempotente: mismo atleta + periodo = mismo enlace
    r2 = client.post(f"/api/coach/report/athlete/{two[0].id}/share", headers=h,
                     json={"start": "2026-12-01", "end": "2026-12-13"})
    assert r2.json()["share_token"] == tok

    client.cookies.clear()
    pub = client.get(f"/api/public/reports/{tok}")
    assert pub.status_code == 200
    j = pub.json()
    assert j["ctl"] == 42.5 and j["race_goal_name"] == "Ironman Pucon"
    assert "athlete_id" not in j and "has_garmin" not in j

    assert client.delete(f"/api/coach/report/shares/{sh['id']}", headers=h).status_code == 200
    assert client.get(f"/api/public/reports/{tok}").status_code == 404
    assert db.query(AthleteReportShare).count() == 0


def test_enlace_listado_y_revocar_ajeno_404(client, db, coach_user, two):
    h = _h(client)
    sh = client.post(f"/api/coach/report/athlete/{two[0].id}/share", headers=h,
                     json={"start": "2026-12-01", "end": "2026-12-13"}).json()
    lst = client.get(f"/api/coach/report/athlete/{two[0].id}/shares", headers=h).json()
    assert [x["id"] for x in lst] == [sh["id"]]
    assert client.delete("/api/coach/report/shares/nope", headers=h).status_code == 404


def test_enlace_atleta_ajeno_o_periodo_invalido_rechazado(client, db, coach_user, two):
    h = _h(client)
    assert client.post("/api/coach/report/athlete/otro/share", headers=h,
                       json={"start": "2026-12-01", "end": "2026-12-13"}).status_code in (403, 404)
    assert client.post(f"/api/coach/report/athlete/{two[0].id}/share", headers=h,
                       json={"start": "mal", "end": "2026-12-13"}).status_code == 400


def test_token_inexistente_404(client):
    assert client.get("/api/public/reports/no-existe").status_code == 404


# ── estructura ────────────────────────────────────────────────────────────────
def test_reportlab_declarado_y_i18n_trilingue():
    assert "reportlab" in (ROOT / "requirements-api.txt").read_text(encoding="utf8")
    src = (ROOT / "i18n.js").read_text(encoding="utf8")
    for k in ("dd_move_ok", "dd_pdf_btn", "dd_share_btn", "dd_share_revoke", "dd_pub_gone"):
        assert len(re.findall(r"\b%s:" % k, src)) == 3, k
    assert "BUILD_VERSION = '384'" in (ROOT / "sw.js").read_text(encoding="utf8")
