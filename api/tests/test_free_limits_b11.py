"""
B11 — Límites Free (flag LABX_FREE_LIMITS). Apagado por defecto.

- Historial de carga: 28 días en la respuesta (el cálculo no cambia).
- Plan de entrenamiento: solo la semana actual.
- Calendario y periodización no se abren a Free.
"""
from datetime import date, timedelta

import pytest

from api import free_limits as fl
from api.auth import hash_password
from api.models import User
from api.plan_features import has_feature
from api.routes import athlete_routes
from .conftest import auth_headers, login


TODAY = date(2026, 10, 21)  # miércoles


# ── funciones puras ──
def test_cutoff_son_28_dias():
    assert fl.history_cutoff(TODAY) == (TODAY - timedelta(days=28)).isoformat()


def test_clip_history_recorta_por_fecha():
    rows = [{"dt": (TODAY - timedelta(days=d)).isoformat(), "v": d} for d in (0, 27, 28, 29, 200)]
    kept = fl.clip_history(rows, TODAY)
    assert [r["v"] for r in kept] == [0, 27, 28]


def test_semana_es_lunes_a_domingo():
    assert fl.week_bounds(TODAY) == ("2026-10-19", "2026-10-25")


def test_clip_range_recorta_al_rango_de_la_semana():
    assert fl.clip_range("2000-01-01", "2099-12-31", TODAY) == ("2026-10-19", "2026-10-25")


def test_clip_range_sin_solape_queda_vacio():
    s, e = fl.clip_range("2026-01-01", "2026-01-31", TODAY)
    assert s > e  # ningún día cae dentro del filtro


def test_clip_range_sin_fechas_usa_la_semana():
    assert fl.clip_range(None, None, TODAY) == ("2026-10-19", "2026-10-25")


# ── flag y quién aplica ──
def _user(plan, rol="atleta"):
    return User(email=f"b11-{plan}-{rol}@x.com", nombre="B11", password_hash="x", rol=rol, plan_nivel=plan)


def test_flag_apagado_por_defecto(monkeypatch):
    monkeypatch.delenv(fl.FLAG_ENV, raising=False)
    assert fl.free_limits_enabled() is False
    assert fl.applies_to(_user("basico")) is False


def test_flag_encendido_solo_afecta_a_basico_atleta(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    assert fl.applies_to(_user("basico")) is True
    assert fl.applies_to(_user("agegroup")) is False
    assert fl.applies_to(_user("elite")) is False
    assert fl.applies_to(_user("basico", rol="coach")) is False


def test_training_plan_para_basico_solo_con_flag(monkeypatch):
    monkeypatch.delenv(fl.FLAG_ENV, raising=False)
    assert has_feature(_user("basico"), "training_plan") is False
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    assert has_feature(_user("basico"), "training_plan") is True


def test_calendario_y_periodizacion_no_se_abren_a_free(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    assert has_feature(_user("basico"), "calendar") is False
    assert has_feature(_user("basico"), "periodization") is False
    assert has_feature(_user("agegroup"), "calendar") is True
    assert has_feature(_user("agegroup"), "periodization") is True


# ── recorte de la respuesta del dashboard ──
def test_dashboard_recorta_pmc_solo_con_flag(monkeypatch):
    user = _user("basico")
    data = {"pmc": [{"dt": (date.today() - timedelta(days=d)).isoformat(), "ctl": 1} for d in (5, 40)],
            "acwr_history": [], "otro": 1}

    monkeypatch.delenv(fl.FLAG_ENV, raising=False)
    assert len(athlete_routes._free_clip_dashboard(data, user)["pmc"]) == 2

    monkeypatch.setenv(fl.FLAG_ENV, "1")
    out = athlete_routes._free_clip_dashboard(data, user)
    assert len(out["pmc"]) == 1
    assert out["otro"] == 1
    assert len(data["pmc"]) == 2  # el original no se modifica (la caché guarda el completo)


def test_dashboard_no_recorta_para_agegroup(monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    data = {"pmc": [{"dt": "2000-01-01", "ctl": 1}]}
    assert athlete_routes._free_clip_dashboard(data, _user("agegroup"))["pmc"] == data["pmc"]


# ── endpoints ──
def _login_basico(client, db, email):
    db.add(User(email=email, nombre="B11", password_hash=hash_password("B11-Pass-1"),
                rol="atleta", plan_nivel="basico", activo=True))
    db.commit()
    return login(client, email, "B11-Pass-1")


def test_calendario_sigue_bloqueado_para_basico(client, db, monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    h = auth_headers(_login_basico(client, db, "b11-cal@test.com"))
    assert client.get("/api/calendar/upcoming", headers=h).status_code == 403


def test_plan_con_flag_responde_para_basico_sin_403(client, db, monkeypatch):
    monkeypatch.setenv(fl.FLAG_ENV, "1")
    h = auth_headers(_login_basico(client, db, "b11-plan@test.com"))
    r = client.get("/api/athlete/plan?start=2000-01-01&end=2099-12-31", headers=h)
    assert r.status_code == 200, r.text


def test_plan_sin_flag_no_cambia_la_respuesta(client, db, monkeypatch):
    # /athlete/plan no tiene gating de módulo en el servidor; sin flag no se recorta nada.
    monkeypatch.delenv(fl.FLAG_ENV, raising=False)
    h = auth_headers(_login_basico(client, db, "b11-plan-off@test.com"))
    r = client.get("/api/athlete/plan?start=2000-01-01&end=2099-12-31", headers=h)
    assert r.status_code == 200, r.text
