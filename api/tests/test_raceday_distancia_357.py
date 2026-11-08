"""RACEDAY-DISTANCIA (BUILD 357): vocabulario unico de distancias, sin default
silencioso a olimpico, sin peso 70 ni recovery 70 inventados en auto-plan."""
import os
import uuid
from datetime import datetime, timedelta

import pytest

from api.models import RaceEvent, RecoveryScore
from api.routes.race_routes import (
    _ctl_predict_splits, _physics_predict_splits, normalize_race_type,
)
from api.tests.conftest import auth_headers, login

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("raw,canon", [
    ("70.3", "703"), (" 70.3 ", "703"), ("703", "703"), ("140.6", "full"),
    ("Ironman", "full"), ("full", "full"), ("marathon", "42k"), ("Maratón", "42k"),
    ("42k", "42k"), ("Half Marathon", "21k"), ("half_marathon", "21k"),
    ("media maratón", "21k"), ("Medio  Maratón", "21k"), ("21k", "21k"),
    ("OLYMPIC", "olympic"), ("sprint", "sprint"),
])
def test_normalize_aliases(raw, canon):
    assert normalize_race_type(raw) == canon


@pytest.mark.parametrize("raw", [None, "", "half", "10k", "other", "custom", "zzz"])
def test_normalize_desconocidas_son_none(raw):
    assert normalize_race_type(raw) is None


def test_predictores_sin_fallback_a_olimpico():
    with pytest.raises(ValueError):
        _ctl_predict_splits("zzz", 60, 0, 70, 250)
    with pytest.raises(ValueError):
        _physics_predict_splits("zzz", 60, 0, 70, 250, 72.0)


def _setup(client, db, athlete_user, distance=None, weight=72.0, recovery=None):
    athlete_user.plan_nivel = "elite"
    athlete_user.weight_kg = weight
    athlete_user.ftp = 250
    today = datetime.utcnow().date()
    if distance is not None:
        db.add(RaceEvent(id=str(uuid.uuid4()), user_id=athlete_user.id, name="Valdivia",
                         date_iso=(today + timedelta(days=30)).isoformat(), distance=distance))
    if recovery is not None:
        db.add(RecoveryScore(id=str(uuid.uuid4()), user_id=athlete_user.id,
                             date_iso=today.isoformat(), score=recovery))
    db.commit()
    tok = login(client, "athlete@test.com", "AthlPass123")
    return auth_headers(tok)


def _post(client, h, body=None):
    r = client.post("/api/races/auto-plan", json=body or {}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_distancia_70_3_usa_splits_de_703(client, db, athlete_user):
    h = _setup(client, db, athlete_user, distance="70.3", recovery=80)
    d = _post(client, h)
    assert d["prediction"] is True and d["race_type"] == "703"
    ref = _ctl_predict_splits("703", d["ctl_used"], d["tsb_used"], 80, 250)
    assert d["splits"]["total_s"] == ref["total_s"]
    # base 90 km de bici / 21.1 km de corrida: mucho mas largo que un olimpico
    oly = _ctl_predict_splits("olympic", d["ctl_used"], d["tsb_used"], 80, 250)
    assert d["splits"]["total_s"] > 2 * oly["total_s"]
    assert d["splits"]["bike_s"] > 0 and d["splits"]["swim_s"] > 0


def test_marathon_es_42k_solo_corrida(client, db, athlete_user):
    h = _setup(client, db, athlete_user, distance="marathon", recovery=80)
    d = _post(client, h)
    assert d["race_type"] == "42k"
    assert d["splits"]["swim_s"] == 0 and d["splits"]["bike_s"] == 0
    assert d["splits"]["run_s"] > 0 and d["splits"]["run_s"] == d["splits"]["total_s"]


def test_distancia_desconocida_sin_prediccion(client, db, athlete_user):
    h = _setup(client, db, athlete_user, distance="zzz", recovery=80)
    d = _post(client, h)
    assert d["prediction"] is False and d["reason"] == "no_race_type"
    assert "splits" not in d


def test_sin_carrera_sin_prediccion(client, db, athlete_user):
    h = _setup(client, db, athlete_user, distance=None)
    d = _post(client, h)
    assert d["prediction"] is False and d["reason"] == "no_race_type"


def test_selector_manual_valido_sigue_funcionando(client, db, athlete_user):
    h = _setup(client, db, athlete_user, distance=None)
    d = _post(client, h, {"race_type": "70.3"})
    assert d["prediction"] is True and d["race_type"] == "703"


def test_sin_peso_sin_prediccion(client, db, athlete_user):
    h = _setup(client, db, athlete_user, distance="70.3", weight=None, recovery=80)
    d = _post(client, h)
    assert d["prediction"] is False and d["reason"] == "no_weight"
    assert "splits" not in d


def test_sin_recovery_omite_confianza(client, db, athlete_user):
    h = _setup(client, db, athlete_user, distance="70.3", recovery=None)
    d = _post(client, h)
    assert d["prediction"] is True
    assert d["confidence"] is None
    assert d["recovery"] is None


def test_con_recovery_trae_confianza(client, db, athlete_user):
    h = _setup(client, db, athlete_user, distance="70.3", recovery=80)
    d = _post(client, h)
    assert d["confidence"]["confidence_pct"] == 90


def test_gestor_de_carreras_emite_claves_canonicas():
    html = _read("athlete_profile.html")
    sel = html[html.index('id="rc-dist"'):]
    sel = sel[:sel.index("</select>")]
    for v in ('value="full"', 'value="703"', 'value="42k"', 'value="21k"',
              'value="olympic"', 'value="sprint"'):
        assert v in sel
    for v in ('value="70.3"', 'value="marathon"', 'value="half_marathon"', 'value="ironman"'):
        assert v not in sel


def test_race_day_maneja_sin_prediccion():
    s = _read("race_day.html")
    assert "d.prediction === false" in s
    assert "BUILD_VERSION = '357'" in _read("sw.js")
