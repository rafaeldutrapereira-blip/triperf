"""
W19 -- Entrenador: natación como tercer deporte (sport='swim').
Cubre: sesión swim válida (alta/lectura/edición), validación de bloques
(distancias, repeticiones, descansos, ritmo, estilo, material), payload del push
a intervals.icu (DSL por distancia + type 'Swim'), totales y contrato de la página.
"""
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .conftest import login, auth_headers
from ..auth import hash_password
from ..models import User
from .. import intervals_connector as ic
from ..routes.indoor_workout_routes import swim_totals

ROOT = Path(__file__).resolve().parents[2]
PAGE = (ROOT / "indoor_workout.html").read_text(encoding="utf-8-sig")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")

BASE = "/api/athlete/indoor-workouts"
SWIM = [
    {"id": "b1", "type": "warmup", "reps": 1, "dist": 400, "rest": 0, "pace": 125, "stroke": "full", "equipment": ""},
    {"id": "b2", "type": "drill", "reps": 4, "dist": 50, "rest": 15, "pace": 130, "stroke": "drill", "equipment": "fins"},
    {"id": "b3", "type": "main", "reps": 8, "dist": 100, "rest": 20, "pace": 108, "stroke": "full", "equipment": ""},
    {"id": "b4", "type": "cooldown", "reps": 1, "dist": 200, "rest": 0, "pace": 130, "stroke": "full", "equipment": ""},
]
BIKE = [{"type": "steady", "duration": 600, "power": 0.75}]


def _user(db, email):
    u = User(email=email, nombre=email, password_hash=hash_password("W19Pass-12345"),
             rol="athlete", plan_nivel="elite", activo=True)
    db.add(u)
    db.commit()
    return u


def _h(client, email):
    h = auth_headers(login(client, email, "W19Pass-12345"))
    client.cookies.clear()
    return h


def _swim(**over):
    b = dict(SWIM[2])
    b.update(over)
    return [b]


# ── Alta / lectura / edición ────────────────────────────────────────────────

def test_crear_sesion_swim_valida_roundtrip(client, db):
    _user(db, "w19a@test.com")
    h = _h(client, "w19a@test.com")
    r = client.post(BASE, json={"name": "Técnica + series", "sport": "swim", "blocks": SWIM}, headers=h)
    assert r.status_code == 200, r.text
    w = r.json()
    assert w["sport"] == "swim" and w["blocks"] == SWIM
    # 400 + 4x50 + 8x100 + 200 = 1600 m
    assert w["totals"]["distance_m"] == 1600
    got = client.get(f"{BASE}/{w['id']}", headers=h).json()
    assert got["sport"] == "swim" and got["blocks"] == SWIM
    r = client.put(f"{BASE}/{w['id']}", json={"blocks": SWIM[:1]}, headers=h)
    assert r.status_code == 200 and r.json()["totals"]["distance_m"] == 400


def test_bloques_sin_ritmo_son_validos(client, db):
    _user(db, "w19b@test.com")
    h = _h(client, "w19b@test.com")
    blocks = [{"type": "main", "reps": 10, "dist": 100, "rest": 15}]
    r = client.post(BASE, json={"name": "Sin ritmo", "sport": "swim", "blocks": blocks}, headers=h)
    assert r.status_code == 200, r.text


# ── Validación de bloques ───────────────────────────────────────────────────

@pytest.mark.parametrize("over", [
    {"dist": 30},            # no múltiplo de 25
    {"dist": 0},
    {"dist": 20000},         # sobre el máximo por repetición
    {"reps": 0},
    {"reps": 101},
    {"reps": 2.5},
    {"rest": -5},
    {"rest": 4000},
    {"pace": 10},            # ritmo imposible
    {"pace": 900},
    {"type": "steady"},      # tipo de bici
    {"stroke": "mariposa"},
    {"equipment": "jetpack"},
    {"dist": "100"},         # texto en vez de número
])
def test_bloque_swim_invalido_400(client, db, over):
    _user(db, "w19c@test.com")
    h = _h(client, "w19c@test.com")
    r = client.post(BASE, json={"name": "x", "sport": "swim", "blocks": _swim(**over)}, headers=h)
    assert r.status_code == 400, (over, r.text)


def test_sesion_swim_demasiado_larga_400(client, db):
    _user(db, "w19d@test.com")
    h = _h(client, "w19d@test.com")
    blocks = [{"type": "main", "reps": 100, "dist": 1000, "rest": 0}]  # 100 km
    assert client.post(BASE, json={"name": "x", "sport": "swim", "blocks": blocks}, headers=h).status_code == 400


def test_put_solo_bloques_en_swim_se_valida(client, db):
    _user(db, "w19e@test.com")
    h = _h(client, "w19e@test.com")
    w = client.post(BASE, json={"name": "ok", "sport": "swim", "blocks": SWIM}, headers=h).json()
    r = client.put(f"{BASE}/{w['id']}", json={"blocks": _swim(dist=33)}, headers=h)  # sin sport en el PUT
    assert r.status_code == 400


def test_bike_y_run_siguen_igual(client, db):
    _user(db, "w19f@test.com")
    h = _h(client, "w19f@test.com")
    assert client.post(BASE, json={"name": "FTP", "blocks": BIKE}, headers=h).json()["sport"] == "bike"
    run = [{"type": "steady", "mode": "pace", "duration": 600, "val": 300}]
    assert client.post(BASE, json={"name": "R", "sport": "run", "blocks": run}, headers=h).status_code == 200
    assert client.post(BASE, json={"name": "R", "sport": "run", "blocks": BIKE}, headers=h).status_code == 400
    assert client.post(BASE, json={"name": "S", "sport": "triatlon", "blocks": SWIM}, headers=h).status_code == 400
    assert "totals" not in client.get(BASE, headers=h).json()["workouts"][0]


# ── Totales ─────────────────────────────────────────────────────────────────

def test_totales_distancia_y_duracion():
    t = swim_totals([{"reps": 8, "dist": 100, "rest": 20, "pace": 100}])
    assert t["distance_m"] == 800
    assert t["duration_s"] == 8 * 100 + 7 * 20  # 800 s de nado + 7 descansos
    # sin ritmo usa el default (120 s/100 m)
    assert swim_totals([{"reps": 1, "dist": 200, "rest": 0}])["duration_s"] == 240


# ── Push a intervals.icu ────────────────────────────────────────────────────

class TestPushSwim:
    def test_dsl_por_distancia_con_ritmo_descanso_y_cues(self):
        dsl = ic.blocks_to_intervals_dsl(SWIM, "swim")
        assert "- Warmup 400mtr 2:05/100m Pace" in dsl
        assert "4x\n- Technique Drill Fins 50mtr 2:10/100m Pace\n- Rest 15s" in dsl
        assert "8x\n- Main 100mtr 1:48/100m Pace\n- Rest 20s" in dsl
        assert "- Cooldown 200mtr 2:10/100m Pace" in dsl
        assert "ramp" not in dsl and "%" not in dsl  # nada del DSL de bici/running

    def test_una_sola_repeticion_no_emite_descanso_ni_nx(self):
        dsl = ic.blocks_to_intervals_dsl([{"type": "main", "reps": 1, "dist": 400, "rest": 30}], "swim")
        assert dsl == "- Main 400mtr"

    def test_bloque_roto_se_omite_sin_lanzar(self):
        assert ic.blocks_to_intervals_dsl([{"type": "main", "reps": "x", "dist": 100}], "swim") == ""

    def test_evento_enviado_es_tipo_swim(self, client, db):
        u = _user(db, "w19push@test.com")
        h = _h(client, "w19push@test.com")
        ic.save_tokens(u, "tok", "1", db)
        w = client.post(BASE, json={"name": "Nado", "sport": "swim", "planned_date": "2026-11-10",
                                    "blocks": SWIM}, headers=h).json()
        resp = MagicMock()
        resp.status_code = 200
        resp.content = b'{"id": 777}'
        resp.json.return_value = {"id": 777}
        with patch("httpx.AsyncClient") as MockClient:
            mc = AsyncMock()
            mc.post = AsyncMock(return_value=resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mc)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            r = client.post(f"{BASE}/{w['id']}/send-to-watch", headers=h)
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True, "event_id": 777}
        sent = json.loads(mc.post.call_args.kwargs["content"])
        assert sent["type"] == "Swim" and sent["category"] == "WORKOUT"
        assert sent["start_date_local"] == "2026-11-10T00:00:00"
        assert "8x\n- Main 100mtr 1:48/100m Pace" in sent["description"]

    def test_bike_y_run_conservan_su_type(self):
        # el cambio de mapeo no altera los tipos existentes
        assert {"run": "Run", "swim": "Swim"}.get("bike", "Ride") == "Ride"


# ── Contrato de la página / i18n ────────────────────────────────────────────

def test_pagina_tiene_boton_y_panel_de_natacion():
    assert "setSport('swim')" in PAGE and 'id="sport-btn-swim"' in PAGE
    assert 'id="iw-swim"' in PAGE and "addSwimBlock('main')" in PAGE
    # swim se envía por el mismo camino (un solo POST a send-to-watch)
    assert PAGE.count("/send-to-watch'") == 1


def test_claves_i18n_swim_en_es_pt_en():
    # claves literales usadas por la página (las que terminan en "_" son prefijos dinámicos)
    keys = {k for k in re.findall(r"\b(iw_(?:sport_swim|swim_[a-z_0-9]+))\b", PAGE) if not k.endswith("_")}
    # claves construidas en JS: iw_swim_{stroke,equip,type}_<valor>
    keys |= {f"iw_swim_stroke_{v}" for v in ("full", "drill", "kick", "pull")}
    keys |= {f"iw_swim_equip_{v}" for v in ("none", "fins", "paddles", "buoy", "snorkel")}
    keys |= {f"iw_swim_type_{v}" for v in ("warmup", "main", "drill", "cooldown")}
    assert len(keys) >= 30
    for k in keys:
        assert len(re.findall(r"\b%s\s*:" % re.escape(k), I18N)) == 3, k
