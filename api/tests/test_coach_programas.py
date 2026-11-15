"""PROGRAMAS (BUILD 383): PlanTemplate expuesto como «Programas»; el assign escribe en el
sistema vivo (AssignedWorkout + WorkoutTemplate por sesion) + TrainingPhase, cero
WorkoutPrescription nuevas, push a intervals.icu con estado por asignacion."""
import json
import pathlib
import re
from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from .conftest import login, auth_headers, TestingSessionLocal
from .test_coach_destino_multiple import _mk_athletes
from api import coach_intervals_push as cip
from api import intervals_connector as ic
from api.auth import hash_password
from api.models import (
    AssignedWorkout, CoachAthlete, TrainingPhase, User, WorkoutPrescription, WorkoutTemplate,
)
from api.services.template_service import (
    BUILTIN_TEMPLATES, assign_template_to_athlete, synthesize_blocks,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
START = "2026-12-07"  # lunes


def _h(client):
    return auth_headers(login(client, "coach@test.com", "CoachPass123"))


def _builtin(tid):
    return next(b for b in BUILTIN_TEMPLATES if b["id"] == tid)


def _assign(client, tid, athlete_id, start=START):
    return client.post(f"/api/coach/templates/{tid}/assign", headers=_h(client),
                       json={"athlete_id": athlete_id, "start_date": start})


def _rows(db, athlete_id):
    db.expire_all()
    return (db.query(AssignedWorkout).filter(AssignedWorkout.athlete_id == athlete_id)
            .order_by(AssignedWorkout.date_iso).all())


@pytest.fixture
def no_push(monkeypatch):
    """Sin hilos: registra los ids que se habrian enviado."""
    from api.routes import coach_routes
    sent = []
    monkeypatch.setattr(coach_routes, "_start_intervals_push", lambda ids: sent.append(list(ids)))
    return sent


@pytest.fixture
def sync_push(monkeypatch):
    from api.routes import coach_routes
    import api.database as database
    monkeypatch.setattr(database, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(coach_routes, "_start_intervals_push",
                        lambda ids: cip.push_assignments_background(list(ids)))
    users = []

    async def _fake(**kw):
        users.append(kw["user"].id)
        return {"ok": True, "event_id": 555}

    mock = AsyncMock(side_effect=_fake)
    mock.users = users
    monkeypatch.setattr(ic, "send_workout_event", mock)
    return mock


@pytest.fixture
def ath(db, coach_user):
    return _mk_athletes(db, coach_user, 1)[0]


# ── Lista / detalle / CRUD ────────────────────────────────────────────────────

def test_lista_incluye_builtins_y_propios(client, db, coach_user):
    h = _h(client)
    r = client.get("/api/coach/templates", headers=h)
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert {"builtin-ironman-20w", "builtin-703-12w", "builtin-sprint-8w"} <= ids
    c = client.post("/api/coach/templates", headers=h, json={
        "name": "Mi base", "sport": "run", "plan_weeks": [{"week_num": 1, "phase_type": "base"}]})
    assert c.status_code == 201
    lst = client.get("/api/coach/templates", headers=h).json()
    own = [t for t in lst if t["id"] == c.json()["id"]]
    assert own and own[0]["is_builtin"] is False and own[0]["weeks"] == 1


def test_detalle_builtin_trae_semanas_fases_tss_y_sesiones(client, db, coach_user):
    d = client.get("/api/coach/templates/builtin-703-12w", headers=_h(client)).json()
    assert len(d["plan_weeks"]) == 12
    w1 = d["plan_weeks"][0]
    assert w1["phase_type"] == "base" and w1["tss_target"] == 300
    assert len(w1["sessions"]) == 3 and w1["sessions"][0]["sport"] == "swim"


def test_crud_programa_propio(client, db, coach_user):
    h = _h(client)
    c = client.post("/api/coach/templates", headers=h, json={
        "name": "P1", "sport": "triathlon", "is_public": False, "plan_weeks": [
            {"week_num": 1, "phase_type": "base", "tss_target": 100,
             "sessions": [{"sport": "run", "title": "Rodaje", "duration_min": 40, "tss": 30, "zone": "Z2"}]}]})
    tid = c.json()["id"]
    u = client.put(f"/api/coach/templates/{tid}", headers=h, json={"name": "P1b", "is_public": True})
    assert u.status_code == 200 and u.json()["name"] == "P1b" and u.json()["is_public"] is True
    assert client.put("/api/coach/templates/builtin-703-12w", headers=h, json={"name": "x"}).status_code == 403
    assert client.delete("/api/coach/templates/builtin-703-12w", headers=h).status_code == 403
    assert client.delete(f"/api/coach/templates/{tid}", headers=h).status_code == 204
    assert client.get(f"/api/coach/templates/{tid}", headers=h).status_code == 404


# ── Assign builtin ────────────────────────────────────────────────────────────

def test_assign_builtin_703_crea_assigned_fases_y_cero_prescripciones(client, db, coach_user, ath, no_push):
    before = db.query(WorkoutPrescription).count()
    r = _assign(client, "builtin-703-12w", ath.id)
    assert r.status_code == 201, r.text
    body = r.json()
    bt = _builtin("builtin-703-12w")
    expected = sum(len(w["sessions_json"]) for w in bt["plan_weeks"])
    assert body["assigned_created"] == expected
    assert "prescriptions_created" not in body
    assert body["weeks"] == 12 and body["start_date"] == START
    assert body["end_date"] == (date.fromisoformat(START) + timedelta(weeks=12, days=-1)).isoformat()
    rows = _rows(db, ath.id)
    assert len(rows) == expected
    # CERO prescripciones nuevas
    db.expire_all()
    assert db.query(WorkoutPrescription).count() == before
    # fechas: Lun/Mie/Vie/Sab de cada semana
    start = date.fromisoformat(START)
    exp_dates = []
    for w in bt["plan_weeks"]:
        ws = start + timedelta(weeks=w["week_num"] - 1)
        for i in range(len(w["sessions_json"])):
            exp_dates.append((ws + timedelta(days=[0, 2, 4, 5][i % 4])).isoformat())
    assert sorted(r_.date_iso for r_ in rows) == sorted(exp_dates)
    assert rows[0].date_iso == START
    # fases: base / recovery / build / taper (el tracker agrupa por tipo)
    phases = db.query(TrainingPhase).filter(TrainingPhase.athlete_id == ath.id).all()
    assert len(phases) == body["phases_created"] >= 3
    assert {p.phase_type for p in phases} >= {"base", "build", "taper"}
    # el push se disparo con exactamente esos ids
    assert len(no_push) == 1 and set(no_push[0]) == {r_.id for r_ in rows}


def test_cada_sesion_tiene_su_workout_template_con_bloques_sintetizados(client, db, coach_user, ath, no_push):
    assert _assign(client, "builtin-sprint-8w", ath.id).status_code == 201
    rows = _rows(db, ath.id)
    by_sport = {}
    for a in rows:
        t = a.template
        assert t.coach_id == coach_user.id
        assert "[programa:builtin-sprint-8w]" in t.notas
        by_sport.setdefault(t.sport, []).append(t)
    assert set(by_sport) == {"swim", "bike", "run"}  # brick -> bici
    bike = by_sport["bike"][0]
    blocks = json.loads(bike.blocks_json)
    assert len(blocks) == 1 and blocks[0]["type"] == "steady"
    assert blocks[0]["duration"] == bike.dur_min * 60 and blocks[0]["power"] == 0.65  # Z2
    run = json.loads(by_sport["run"][0].blocks_json)[0]
    assert run["mode"] == "hr" and run["val"] == 0.72
    # natacion: el stub no trae distancia -> sin estructura inventada
    assert all(t.blocks_json is None for t in by_sport["swim"])
    brick = [t for t in by_sport["bike"] if "brick" in (t.notas or "")]
    assert brick and "registrado como sesi" in brick[0].notas


def test_synthesize_sin_zona_ni_duracion_no_inventa():
    assert synthesize_blocks({"sport": "bike", "title": "x"}) is None
    assert synthesize_blocks({"sport": "bike", "title": "x", "zone": "Z2"}) is None
    assert synthesize_blocks({"sport": "bike", "title": "x", "duration_min": 60}) is None
    assert synthesize_blocks({"sport": "bike", "title": "x", "duration_min": 60, "zone": "Zx"}) is None
    assert synthesize_blocks({"sport": "swim", "title": "x", "duration_min": 30, "zone": "Z2"}) is None
    assert synthesize_blocks({"sport": "bike", "duration_min": 60, "zone": "Z4"})[0]["power"] == 0.98


# ── Assign propio ─────────────────────────────────────────────────────────────

def _own(client, h):
    return client.post("/api/coach/templates", headers=h, json={
        "name": "Propio", "sport": "triathlon", "plan_weeks": [
            {"week_num": 1, "phase_type": "base", "label": "B1", "tss_target": 120, "sessions": [
                {"sport": "bike", "title": "Z2 bici", "duration_min": 60, "tss": 40, "zone": "Z2"},
                {"sport": "run", "title": "Sin datos"},
                {"sport": "run", "title": "Tempo", "duration_min": 30, "tss": 35, "zone": "Z3"}]},
            {"week_num": 2, "phase_type": "build", "label": "C1", "tss_target": 150, "sessions": [
                {"sport": "bike", "title": "Umbral", "duration_min": 50, "tss": 60, "zone": "Z4"}]}]}).json()["id"]


def test_assign_programa_propio_y_stub_sin_estructura(client, db, coach_user, ath, no_push):
    h = _h(client)
    tid = _own(client, h)
    r = _assign(client, tid, ath.id)
    assert r.status_code == 201
    b = r.json()
    assert b["assigned_created"] == 4 and b["with_structure"] == 3 and b["without_structure"] == 1
    assert b["phases_created"] == 2
    rows = _rows(db, ath.id)
    assert [a.date_iso for a in rows] == ["2026-12-07", "2026-12-09", "2026-12-11", "2026-12-14"]
    sin = [a for a in rows if a.template.nombre == "Sin datos"][0]
    assert sin.template.blocks_json is None


def test_programa_ajeno_es_404(client, db, coach_user, ath, no_push):
    otro = User(email="coach9@test.com", nombre="O", password_hash=hash_password("Passw0rd123"),
                rol="coach", plan_nivel="basico", activo=True)
    db.add(otro); db.commit()
    tpl = login(client, "coach9@test.com", "Passw0rd123")
    pid = client.post("/api/coach/templates", headers=auth_headers(tpl), json={
        "name": "Ajeno", "plan_weeks": [{"week_num": 1, "sessions": []}]}).json()["id"]
    assert _assign(client, pid, ath.id).status_code == 404
    assert _rows(db, ath.id) == []


# ── Seguridad / validacion ────────────────────────────────────────────────────

def test_atleta_ajeno_403_y_nada_escrito(client, db, coach_user, no_push):
    other = User(email="coach2@test.com", nombre="Otro", password_hash=hash_password("Passw0rd123"),
                 rol="coach", plan_nivel="basico", activo=True)
    a = User(email="ajeno@test.com", nombre="Ajeno", password_hash=hash_password("Passw0rd123"),
             rol="athlete", plan_nivel="basico", activo=True)
    db.add_all([other, a]); db.flush()
    db.add(CoachAthlete(coach_id=other.id, athlete_id=a.id, status="active"))
    db.commit()
    r = _assign(client, "builtin-703-12w", a.id)
    assert r.status_code == 403
    assert _rows(db, a.id) == [] and no_push == []
    assert db.query(TrainingPhase).filter(TrainingPhase.athlete_id == a.id).count() == 0


def test_atleta_inexistente_404(client, db, coach_user, no_push):
    assert _assign(client, "builtin-703-12w", "no-existe").status_code == 404


def test_plantilla_inexistente_404(client, db, coach_user, ath, no_push):
    r = _assign(client, "no-existe", ath.id)
    assert r.status_code == 404 and _rows(db, ath.id) == []


def test_atleta_no_puede_asignar(client, db, coach_user, athlete_user, no_push):
    tok = login(client, "athlete@test.com", "AthlPass123")
    r = client.post("/api/coach/templates/builtin-703-12w/assign", headers=auth_headers(tok),
                    json={"athlete_id": athlete_user.id, "start_date": START})
    assert r.status_code in (401, 403)


def test_start_date_no_lunes_o_invalida_422(client, db, coach_user, ath, no_push):
    assert _assign(client, "builtin-703-12w", ath.id, "2026-12-08").status_code == 422  # martes
    assert _assign(client, "builtin-703-12w", ath.id, "basura").status_code == 422
    assert _rows(db, ath.id) == [] and no_push == []


# ── Re-assign con solape ──────────────────────────────────────────────────────

def test_reassign_con_solape_409_sin_duplicados(client, db, coach_user, ath, no_push):
    assert _assign(client, "builtin-sprint-8w", ath.id).status_code == 201
    n = len(_rows(db, ath.id))
    ph = db.query(TrainingPhase).filter(TrainingPhase.athlete_id == ath.id).count()
    r = _assign(client, "builtin-sprint-8w", ath.id)  # misma fecha: solape total
    assert r.status_code == 409
    err = r.json()["errors"][0]
    assert err["code"] == "program_overlap" and "No se asigno nada" in err["message"]
    # desplazado una semana: solapa 7 de 8 semanas
    assert _assign(client, "builtin-sprint-8w", ath.id, "2026-12-14").status_code == 409
    db.expire_all()
    assert len(_rows(db, ath.id)) == n
    assert db.query(TrainingPhase).filter(TrainingPhase.athlete_id == ath.id).count() == ph
    assert len(no_push) == 1  # el rechazo no dispara push


def test_reassign_sin_solape_ok_y_borrado_blando_libera_fechas(client, db, coach_user, ath, no_push):
    assert _assign(client, "builtin-sprint-8w", ath.id).status_code == 201
    n = len(_rows(db, ath.id))
    # arranca justo despues de terminar (8 semanas): sin solape
    nxt = (date.fromisoformat(START) + timedelta(weeks=8)).isoformat()
    assert _assign(client, "builtin-sprint-8w", ath.id, nxt).status_code == 201
    assert len(_rows(db, ath.id)) == 2 * n
    # filas con deleted_at ya no cuentan como solape
    from datetime import datetime
    db.query(AssignedWorkout).filter(AssignedWorkout.athlete_id == ath.id,
                                     AssignedWorkout.date_iso < nxt).update(
        {"deleted_at": datetime.utcnow()}, synchronize_session=False)
    db.commit()
    assert _assign(client, "builtin-sprint-8w", ath.id).status_code == 201


def test_otro_programa_misma_fecha_no_es_solape(client, db, coach_user, ath, no_push):
    assert _assign(client, "builtin-sprint-8w", ath.id).status_code == 201
    assert _assign(client, "builtin-703-12w", ath.id).status_code == 201


def test_sesion_manual_en_la_misma_fecha_no_bloquea(client, db, coach_user, ath, no_push):
    t = WorkoutTemplate(coach_id=coach_user.id, sport="run", nombre="Manual", dur_min=30)
    db.add(t); db.commit()
    db.add(AssignedWorkout(template_id=t.id, athlete_id=ath.id, date_iso=START)); db.commit()
    assert _assign(client, "builtin-sprint-8w", ath.id).status_code == 201


# ── Push a intervals.icu ──────────────────────────────────────────────────────

def test_push_con_intervals_ok_pending_y_skipped(client, db, coach_user, ath, sync_push):
    ath.intervals_access_token = "tok-" + ath.id[:6]
    db.commit()
    assert _assign(client, "builtin-sprint-8w", ath.id).status_code == 201
    rows = _rows(db, ath.id)
    st = {}
    for a in rows:
        st.setdefault((a.template.sport, a.template.blocks_json is not None), set()).add(a.intervals_push_status)
    assert st[("bike", True)] == {"ok"} and st[("run", True)] == {"ok"}
    assert st[("swim", False)] == {"skipped"}  # sin estructura: honesto
    ok = [a for a in rows if a.intervals_push_status == "ok"]
    assert sync_push.await_count == len(ok) and all(a.intervals_push_event_id == "555" for a in ok)
    assert set(sync_push.users) == {ath.id}


def test_push_sin_intervals_queda_pending(client, db, coach_user, ath, sync_push):
    assert _assign(client, "builtin-sprint-8w", ath.id).status_code == 201
    rows = _rows(db, ath.id)
    structured = [a for a in rows if a.template.blocks_json]
    assert structured and all(a.intervals_push_status == "pending" for a in structured)
    assert all(a.intervals_push_status == "skipped" for a in rows if not a.template.blocks_json)
    assert sync_push.await_count == 0


# ── Sistema vivo: adherencia; sistema viejo intacto ───────────────────────────

def test_adherencia_cuenta_el_programa(client, db, coach_user, ath, no_push):
    from api.models import WorkoutLog
    assert _assign(client, "builtin-sprint-8w", ath.id).status_code == 201
    h = _h(client)
    q = {"start": START, "end": "2026-12-13"}
    mine = [x for x in client.get("/api/coach/adherence", headers=h, params=q).json() if x["user_id"] == ath.id]
    assert mine and mine[0]["total"] == 3 and mine[0]["completado"] == 0  # semana 1 del sprint: 3 sesiones
    first = _rows(db, ath.id)[0]
    db.add(WorkoutLog(user_id=ath.id, assignment_id=first.id, completado=True)); db.commit()
    mine = [x for x in client.get("/api/coach/adherence", headers=h, params=q).json() if x["user_id"] == ath.id]
    assert mine[0]["completado"] == 1 and mine[0]["pct"] == 33.3
    # y plan-vs-real del atleta responde con el sistema vivo
    r = client.get(f"/api/coach/athletes/{ath.id}/plan-vs-actual", headers=h, params=q)
    assert r.status_code == 200


def test_prescripciones_existentes_y_endpoints_viejos_se_conservan(client, db, coach_user, ath, no_push):
    db.add(WorkoutPrescription(coach_id=coach_user.id, athlete_id=ath.id, title="Vieja",
                               sport="run", date_iso="2026-12-01", status="pending"))
    db.commit()
    assert _assign(client, "builtin-sprint-8w", ath.id).status_code == 201
    db.expire_all()
    assert db.query(WorkoutPrescription).filter(WorkoutPrescription.athlete_id == ath.id).count() == 1
    h = _h(client)
    assert client.get(f"/api/coach/athletes/{ath.id}/compliance-trend", headers=h).status_code == 200
    assert client.get("/api/coach/squad/compliance-trend", headers=h).status_code == 200
    assert client.get("/api/coach/prescriptions", headers=h, params={"athlete_id": ath.id}).status_code in (200, 422)


def test_servicio_directo_devuelve_error_sin_escribir(db, coach_user, ath):
    r = assign_template_to_athlete("nada", ath.id, coach_user.id, START, db)
    assert r == {"error": "template_not_found"}
    assert assign_template_to_athlete("builtin-sprint-8w", ath.id, coach_user.id, "2026-12-08", db)["error"] == "start_not_monday"


# ── Alcance de la pila ────────────────────────────────────────────────────────

def test_notes_macro_routes_intacto_y_build():
    assert (ROOT / "api" / "routes" / "notes_macro_routes.py").exists()
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    assert int(re.search(r"var BUILD_VERSION = '(\d+)';", sw).group(1)) >= 383
    m = re.search(r"'/i18n\.js\?v=(\d+)'", sw)
    assert f"i18n.js?v={m.group(1)}" in (ROOT / "coach.html").read_text(encoding="utf-8")


def test_seccion_programas_en_coach_html_aditiva():
    html = (ROOT / "coach.html").read_text(encoding="utf-8")
    for tab in ("overview", "athletes", "groups", "workouts", "mi-atleta", "assign", "plan",
                "adherence", "gantt", "report", "adp-coach", "rec-coach", "tablero", "programas"):
        assert f'data-tab="{tab}"' in html and f'id="tab-{tab}"' in html, tab
    assert "/coach/templates" in html


def test_i18n_programas_en_tres_idiomas():
    i18n = (ROOT / "i18n.js").read_text(encoding="utf-8")
    html = (ROOT / "coach.html").read_text(encoding="utf-8")
    keys = set(re.findall(r"data-i18n=\"(prog_\w+|tab_programas)\"", html))
    keys |= set(re.findall(r"'(prog_\w+)'", html))
    keys = {k for k in keys if not k.endswith("_")}  # prefijos dinamicos ('prog_sp_' + deporte)
    for fam, vals in (("prog_sp_", ("triathlon", "swim", "bike", "run", "str", "brick")),
                      ("prog_ph_", ("base", "build", "peak", "taper", "recovery", "transition")),
                      ("prog_df_", ("beginner", "intermediate", "advanced"))):
        keys |= {fam + v for v in vals}
    assert len(keys) > 60
    for k in keys:
        assert len(re.findall(rf"\b{k}:", i18n)) == 3, k
