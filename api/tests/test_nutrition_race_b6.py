"""
B6 — Nutrición de carrera: Race Day es la fuente única.

- nearest_race_for: la carrera futura más próxima; si no hay, la más reciente.
- GET /races/nutrition/latest: plan de la carrera más próxima.
- Migración: dry-run no escribe; --apply genera race_plans con el generador de
  Race Day; es idempotente; atletas sin carrera quedan como sin_carrera.
- nutrition.html ya no guarda un plan propio.
"""
import json
from datetime import date, timedelta
from pathlib import Path

from api.models import NutritionPlan, RaceEvent, RacePlan, User
from api.routes.race_routes import _gen_nutrition, nearest_race_for
from api.services.nutrition_migration import apply_migration, plan_migration
from .conftest import auth_headers, login

ROOT = Path(__file__).resolve().parents[2]
TODAY = date.today()


def _race(db, user, name, days, dist="olympic"):
    r = RaceEvent(user_id=user.id, name=name, date_iso=(TODAY + timedelta(days=days)).isoformat(),
                  distance=dist)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _nutrition_plan(db, user, sweat=0.9):
    db.add(NutritionPlan(user_id=user.id, race_name="legacy", race_dist="olympic",
                         params_json=json.dumps({"sweat": sweat, "heat": 1.0})))
    db.commit()


# ── selección de carrera ──
def test_carrera_futura_mas_proxima_gana(client, db, athlete_user):
    _race(db, athlete_user, "Lejana", 90)
    cercana = _race(db, athlete_user, "Cercana", 10)
    _race(db, athlete_user, "Pasada", -30)
    assert nearest_race_for(db, athlete_user.id, TODAY.isoformat()).id == cercana.id


def test_sin_futuras_usa_la_mas_reciente(client, db, athlete_user):
    _race(db, athlete_user, "Vieja", -100)
    reciente = _race(db, athlete_user, "Reciente", -10)
    assert nearest_race_for(db, athlete_user.id, TODAY.isoformat()).id == reciente.id


def test_sin_carreras_devuelve_none(client, db, athlete_user):
    assert nearest_race_for(db, athlete_user.id, TODAY.isoformat()) is None


# ── endpoint latest ──
def test_latest_404_sin_carreras(client, db, athlete_user):
    athlete_user.plan_nivel = "agegroup"  # Race Day exige agegroup+
    db.commit()
    token = login(client, "athlete@test.com", "AthlPass123")
    r = client.get("/api/races/nutrition/latest", headers=auth_headers(token))
    assert r.status_code == 404


def test_latest_devuelve_plan_de_la_carrera_mas_proxima(client, db, athlete_user):
    athlete_user.plan_nivel = "agegroup"
    db.commit()
    _race(db, athlete_user, "Ironman local", 30, dist="full")
    token = login(client, "athlete@test.com", "AthlPass123")
    r = client.get("/api/races/nutrition/latest", headers=auth_headers(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["race_name"] == "Ironman local"
    assert "strategy" in body["nutrition"]


# ── migración ──
def test_dry_run_no_escribe(client, db, athlete_user):
    _race(db, athlete_user, "Objetivo", 20)
    _nutrition_plan(db, athlete_user)
    report = plan_migration(db, TODAY.isoformat())
    assert [r["status"] for r in report] == ["migrado"]
    assert db.query(RacePlan).count() == 0


def test_apply_genera_plan_con_el_generador_de_race_day(client, db, athlete_user):
    race = _race(db, athlete_user, "Objetivo", 20, dist="olympic")
    _nutrition_plan(db, athlete_user, sweat=0.9)
    apply_migration(db, TODAY.isoformat())
    rp = db.query(RacePlan).filter_by(user_id=athlete_user.id, race_event_id=race.id).one()
    esperado = _gen_nutrition(7200, "olympic", 72.0, 0.9)  # mismo motor; 72 kg del fixture athlete_user
    assert json.loads(rp.nutrition_plan_json) == esperado


def test_apply_es_idempotente(client, db, athlete_user):
    _race(db, athlete_user, "Objetivo", 20)
    _nutrition_plan(db, athlete_user)
    apply_migration(db, TODAY.isoformat())
    first = db.query(RacePlan).one().nutrition_plan_json
    apply_migration(db, TODAY.isoformat())
    assert db.query(RacePlan).count() == 1
    assert db.query(RacePlan).one().nutrition_plan_json == first


def test_atleta_sin_carrera_queda_sin_carrera(client, db, athlete_user):
    _nutrition_plan(db, athlete_user)
    report = apply_migration(db, TODAY.isoformat())
    assert report[0]["status"] == "sin_carrera"
    assert db.query(RacePlan).count() == 0


def test_no_borra_nutrition_plans(client, db, athlete_user):
    _race(db, athlete_user, "Objetivo", 20)
    _nutrition_plan(db, athlete_user)
    apply_migration(db, TODAY.isoformat())
    assert db.query(NutritionPlan).count() == 1


def test_sweat_fuera_de_rango_se_acota(client, db, athlete_user):
    _race(db, athlete_user, "Objetivo", 20)
    _nutrition_plan(db, athlete_user, sweat=99)
    report = plan_migration(db, TODAY.isoformat())
    assert report[0]["status"] == "migrado"


# ── nutrition.html ──
def test_nutrition_html_lee_de_race_day_y_no_guarda():
    html = (ROOT / "nutrition.html").read_text(encoding="utf-8")
    assert "/races/nutrition/latest" in html
    assert "saveNutritionPlanToAPI" not in html
    assert "method: 'POST'" not in html.split("function loadNutritionPlanFromAPI")[1][:1200]
