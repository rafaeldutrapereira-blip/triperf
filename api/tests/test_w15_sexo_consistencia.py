"""W15 — consistencia del campo sexo ('f'/'m'/NULL) en nutricion y readiness."""
import json
from datetime import date

import pytest

from .conftest import login
from ..models import BloodLabExam
from ..routes.nutrition_routes import _compute_kcal_targets
from ..services.blood_labs_impact_service import declared_sex
from ..services.readiness_service import get_trs


class _U:
    def __init__(self, sexo=None):
        self.sexo = sexo
        self.peso_kg = 70.0
        self.altura_cm = 175.0
        self.edad = 35


def _kcal(sexo):
    return _compute_kcal_targets(_U(sexo), "moderate")["kcal"]


def test_declared_sex_normaliza():
    assert declared_sex(_U("f")) == "f"
    assert declared_sex(_U("F")) == "f"
    assert declared_sex(_U("m")) == "m"
    assert declared_sex(_U(None)) is None
    assert declared_sex(_U("")) is None
    assert declared_sex(_U("x")) is None


def test_nutricion_sexo_f_toma_rama_femenina():
    assert _kcal("f") < _kcal("m")


def test_nutricion_sin_sexo_no_es_masculino():
    neutro = _kcal(None)
    assert neutro != _kcal("m")
    assert _kcal("f") < neutro < _kcal("m")


def _add_exam(db, user):
    # Hb 13.0: warning en hombre (<14.0), normal en mujer (>=13.0)
    db.add(BloodLabExam(user_id=user.id, date_iso=date.today().isoformat(),
                        values_json=json.dumps({"hb": 13.0})))
    db.commit()


def test_readiness_sexo_f_toma_rama_femenina(db, athlete_user):
    _add_exam(db, athlete_user)
    athlete_user.sexo = "f"
    db.commit()
    trs_f = get_trs(athlete_user.id, db)
    athlete_user.sexo = "m"
    db.commit()
    trs_m = get_trs(athlete_user.id, db)
    assert trs_f is not None and trs_m is not None
    assert trs_f > trs_m


def test_readiness_sin_sexo_no_calcula_como_hombre(db, athlete_user):
    _add_exam(db, athlete_user)
    assert athlete_user.sexo is None
    assert get_trs(athlete_user.id, db) is None


@pytest.fixture
def headers(client, db, athlete_user):
    athlete_user.plan_nivel = "elite"
    db.commit()
    return {"Authorization": f"Bearer {login(client, 'athlete@test.com', 'AthlPass123')}"}


def test_labs_sync_sin_sexo_y_con_sexo_f(client, db, athlete_user, headers):
    _add_exam(db, athlete_user)
    r = client.get("/api/nutrition/labs-sync", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["has_labs"] is False and r.json()["sex_missing"] is True
    athlete_user.sexo = "f"
    db.commit()
    r = client.get("/api/nutrition/labs-sync", headers=headers)
    assert r.json()["has_labs"] is True
    athlete_user.sexo = "m"
    db.commit()
    r2 = client.get("/api/nutrition/labs-sync", headers=headers)
    assert r.json()["trs"] > r2.json()["trs"]
