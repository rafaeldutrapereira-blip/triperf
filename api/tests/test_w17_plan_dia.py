"""W17 - el plan del dia suma asignaciones LabX + plan de Garmin."""
import re
from datetime import date, timedelta
from pathlib import Path

from .conftest import login, auth_headers
from api.models import (
    AssignedWorkout, GarminActivity, GarminPlannedWorkout, WorkoutTemplate,
)

TODAY = date.today().isoformat()
OTHER = (date.today() + timedelta(days=1)).isoformat()


def _gpw(db, uid, day=TODAY, title="Intervalos UL extensivos", sport="bike", sid="s1"):
    g = GarminPlannedWorkout(user_id=uid, date_iso=day, garmin_scheduled_id=sid,
                             title=title, sport=sport, dur_min=91, dist_km=None, source="garmin")
    db.add(g)
    db.commit()
    return g


def _assign(db, uid, day=TODAY, nombre="Intervalos UL extensivos", sport="bike"):
    t = WorkoutTemplate(coach_id="c", sport=sport, nombre=nombre, dur_min=90)
    db.add(t)
    db.flush()
    a = AssignedWorkout(template_id=t.id, athlete_id=uid, date_iso=day)
    db.add(a)
    db.commit()
    return a


def _get(client, tok, day=TODAY, end=None, garmin=True):
    url = "/api/athlete/plan?start=%s&end=%s%s" % (day, end or day, "&include_garmin=1" if garmin else "")
    r = client.get(url, headers=auth_headers(tok))
    assert r.status_code == 200, r.text
    return r.json()


def _tok(client):
    return login(client, "athlete@test.com", "AthlPass123")


def test_fila_garmin_de_hoy_aparece_con_source_garmin(client, db, athlete_user):
    _gpw(db, athlete_user.id)
    rows = _get(client, _tok(client))
    assert len(rows) == 1
    r = rows[0]
    assert r["source"] == "garmin" and r["date_iso"] == TODAY
    assert r["template"]["sport"] == "bike"
    assert r["template"]["nombre"] == "Intervalos UL extensivos"
    assert r["template"]["dur_min"] == 91
    assert r["logs"] == [] and r["done"] is False


def test_sin_include_garmin_el_contrato_anterior_no_cambia(client, db, athlete_user):
    _gpw(db, athlete_user.id)
    assert _get(client, _tok(client), garmin=False) == []


def test_fila_de_otro_dia_queda_fuera_del_rango(client, db, athlete_user):
    _gpw(db, athlete_user.id, day=OTHER)
    assert _get(client, _tok(client)) == []
    assert len(_get(client, _tok(client), end=OTHER)) == 1


def test_filas_de_otro_usuario_nunca_aparecen(client, db, athlete_user, coach_user):
    _gpw(db, coach_user.id, sid="x1")
    _gpw(db, "otro-usuario", sid="x2")
    assert _get(client, _tok(client)) == []


def test_dedupe_gana_la_asignacion_labx(client, db, athlete_user):
    _assign(db, athlete_user.id, nombre="Intervalos UL extensivos")
    _gpw(db, athlete_user.id, title="intervalos ul extensivos")
    rows = _get(client, _tok(client))
    assert len(rows) == 1 and rows[0]["source"] == "labx"


def test_mismo_titulo_otro_deporte_no_es_duplicado(client, db, athlete_user):
    _assign(db, athlete_user.id, sport="run")
    _gpw(db, athlete_user.id, sport="bike")
    assert sorted(r["source"] for r in _get(client, _tok(client))) == ["garmin", "labx"]


def test_done_solo_con_actividad_real_del_mismo_dia_y_deporte(client, db, athlete_user):
    _gpw(db, athlete_user.id, sport="bike", sid="a")
    db.add(GarminActivity(user_id=athlete_user.id, activity_id="act1", sport="run", date_iso=TODAY))
    db.commit()
    assert _get(client, _tok(client))[0]["done"] is False
    db.add(GarminActivity(user_id=athlete_user.id, activity_id="act2", sport="bike", date_iso=TODAY))
    db.commit()
    assert _get(client, _tok(client))[0]["done"] is True


def test_asignaciones_labx_siguen_igual(client, db, athlete_user):
    _assign(db, athlete_user.id, nombre="Rodaje")
    rows = _get(client, _tok(client))
    assert len(rows) == 1 and rows[0]["source"] == "labx" and rows[0]["done"] is None
    assert rows[0]["template"]["nombre"] == "Rodaje" and rows[0]["logs"] == []


def test_dashboard_consume_la_fuente_garmin():
    root = Path(__file__).resolve().parents[2]
    h = re.sub(r"\s+", " ", (root / "dashboard.html").read_text(encoding="utf-8"))
    assert "include_garmin=1" in h
    assert "a.source === 'garmin'" in h
    assert "dash_w13_src_garmin" in h
    assert "mergeToday(coachToday(assigns), ownToday())" in h
    i18n = (root / "i18n.js").read_text(encoding="utf-8")
    assert i18n.count("dash_w13_src_garmin:") == 3
