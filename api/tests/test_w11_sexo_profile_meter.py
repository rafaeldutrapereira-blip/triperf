"""W11 — campo sexo (Blood Labs, hallazgo I6) + medidor de perfil completo (D10)."""
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import sqlalchemy as sa

from .conftest import login
from ..models import BloodLabAlert
from ..routes.blood_lab_routes import _analyze_marker, _sex

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def headers(client, db, athlete_user):
    athlete_user.plan_nivel = "elite"   # Blood Labs es Elite
    db.commit()
    token = login(client, "athlete@test.com", "AthlPass123")
    return {"Authorization": f"Bearer {token}"}


def _set_sexo(db, user, sexo):
    user.sexo = sexo
    db.commit()


def _exam(client, headers, values=None):
    r = client.post("/api/labs/exams", json={
        "date_iso": "2026-01-15",
        "values": values or {"hb": 14.0, "ferritin": 25.0},
    }, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ── Rangos por sexo ──────────────────────────────────────────────────────────
def test_hb_14_distinto_por_sexo():
    # hb 14.0: hombre = subóptimo (aviso); mujer = óptimo
    assert _analyze_marker("hb", 14.0, "m")["status"] in ("warning", "critical")
    assert _analyze_marker("hb", 14.0, "f")["status"] == "ok"


def test_sex_helper_valores():
    class U:
        sexo = None
    assert _sex(U()) is None
    U.sexo = ""
    assert _sex(U()) is None
    U.sexo = "f"
    assert _sex(U()) == "f"
    U.sexo = "m"
    assert _sex(U()) == "m"


def test_mujer_recibe_rangos_femeninos(client, db, athlete_user, headers):
    _set_sexo(db, athlete_user, "f")
    d = _exam(client, headers, {"hb": 14.0})
    assert d["sex_missing"] is False
    assert d["alerts"] == 0            # con rango _f, 14.0 es óptimo
    det = client.get(f"/api/labs/exams/{d['exam_id']}", headers=headers).json()
    assert det["markers"]["hb"]["status"] == "ok"


def test_hombre_recibe_rangos_masculinos(client, db, athlete_user, headers):
    _set_sexo(db, athlete_user, "m")
    d = _exam(client, headers, {"hb": 14.0})
    assert d["alerts"] == 1


# ── Sin sexo declarado: nada calculado con el rango equivocado ───────────────
def test_sin_sexo_no_hay_alertas_ni_semaforos(client, db, athlete_user, headers):
    assert athlete_user.sexo is None
    d = _exam(client, headers, {"hb": 14.0, "ferritin": 10.0})
    assert d["sex_missing"] is True
    assert d["alerts"] == 0
    assert db.query(BloodLabAlert).count() == 0

    det = client.get(f"/api/labs/exams/{d['exam_id']}", headers=headers).json()
    assert det["sex_missing"] is True
    assert "Declara tu sexo" in det["sex_missing_message"]
    # el valor cargado se muestra tal cual, sin status/zona/tip
    assert det["markers"]["hb"]["value"] == 14.0
    assert "status" not in det["markers"]["hb"]
    assert det["alerts"] == []

    assert client.get("/api/labs/alerts", headers=headers).json() == []
    lst = client.get("/api/labs/exams", headers=headers).json()
    assert lst[0]["n_alerts"] == 0 and lst[0]["n_critical"] == 0

    summ = client.get("/api/labs/summary", headers=headers).json()
    assert summ["sex_missing"] is True
    assert summ["markers_ok"] is None and summ["markers_critical"] is None
    assert summ["total_markers"] == 2

    ti = client.get("/api/labs/training-impact", headers=headers).json()
    assert ti["sex_missing"] is True and ti["trs"] is None
    assert "Declara tu sexo" in ti["message"]


def test_sin_sexo_ia_rechaza(client, headers, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    d = _exam(client, headers, {"hb": 14.0})
    r = client.post(f"/api/labs/exams/{d['exam_id']}/analyze", headers=headers)
    assert r.status_code == 422


def test_declarar_sexo_recalcula_alertas(client, db, athlete_user, headers):
    d = _exam(client, headers, {"hb": 14.0})
    assert d["alerts"] == 0
    r = client.patch("/api/athlete/profile", json={"sexo": "m"}, headers=headers)
    assert r.status_code == 200
    db.expire_all()
    assert db.query(BloodLabAlert).count() == 1       # hombre: hb 14.0 avisa
    r = client.patch("/api/athlete/profile", json={"sexo": "f"}, headers=headers)
    db.expire_all()
    assert db.query(BloodLabAlert).count() == 0       # mujer: óptimo
    r = client.patch("/api/athlete/profile", json={"sexo": ""}, headers=headers)
    db.expire_all()
    assert athlete_user.sexo is None


# ── Perfil: persistencia y validación ────────────────────────────────────────
def test_perfil_guarda_y_devuelve_sexo(client, headers):
    assert client.get("/api/athlete/profile", headers=headers).json()["sexo"] is None
    assert client.patch("/api/athlete/profile", json={"sexo": "F"}, headers=headers).status_code == 200
    assert client.get("/api/athlete/profile", headers=headers).json()["sexo"] == "f"


def test_perfil_rechaza_sexo_invalido(client, headers):
    r = client.patch("/api/athlete/profile", json={"sexo": "x"}, headers=headers)
    assert r.status_code in (400, 422)


# ── Migración idempotente ────────────────────────────────────────────────────
def _load_migration():
    path = ROOT / "alembic" / "versions" / "t6u7v8w9x0y1_add_sexo_to_users.py"
    spec = importlib.util.spec_from_file_location("mig_w11", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migracion_sexo_corre_dos_veces(tmp_path):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    eng = sa.create_engine(f"sqlite:///{tmp_path / 'prod.db'}")
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE users (id VARCHAR PRIMARY KEY, email VARCHAR)"))
        c.execute(sa.text("INSERT INTO users VALUES ('u1', 'a@b.c')"))
    mig = _load_migration()
    assert mig.down_revision == "s5t6u7v8w9x0"
    for _ in range(2):                       # segunda corrida = no-op sin error
        with eng.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                mig.upgrade()
    with eng.connect() as c:
        cols = [r[1] for r in c.execute(sa.text("PRAGMA table_info(users)"))]
        assert cols.count("sexo") == 1
        # datos existentes intactos y sexo = NULL (sin declarar)
        row = c.execute(sa.text("SELECT id, sexo FROM users")).fetchone()
        assert row[0] == "u1" and row[1] is None


def test_migracion_head_unico():
    ids, downs = set(), set()
    import re
    for f in (ROOT / "alembic" / "versions").glob("*.py"):
        t = f.read_text(encoding="utf-8")
        m = re.search(r'^revision\s*=\s*"([^"]+)"', t, re.M)
        d = re.search(r'^down_revision\s*=\s*(?:"([^"]+)"|None)', t, re.M)
        if m:
            ids.add(m.group(1))
        if d and d.group(1):
            downs.add(d.group(1))
    assert len(ids - downs) == 1


# ── Medidor de perfil completo (función real de athlete_profile.html) ────────
@pytest.mark.skipif(shutil.which("node") is None, reason="node no disponible")
def test_medidor_perfil(tmp_path):
    html = (ROOT / "athlete_profile.html").read_text(encoding="utf-8")
    code = html.split("/* PC-BEGIN */")[1].split("/* PC-END */")[0]
    script = code + """
    var full = {ftp:250, weight_kg:70, fcmax:185, css:'1:40', run_pace:'4:30', sexo:'f'};
    var out = {
      full: profileCompleteness(full),
      empty: profileCompleteness({}),
      none: profileCompleteness(null),
      part: profileCompleteness({ftp:250, weight_kg:70, sexo:'m', css:'  ', fcmax:0}),
      badSex: profileCompleteness(Object.assign({}, full, {sexo:'x'})),
    };
    function s(c){return {done:c.done,total:c.total,missing:c.missing.map(function(f){return f.key;})};}
    console.log(JSON.stringify({full:s(out.full),empty:s(out.empty),none:s(out.none),part:s(out.part),badSex:s(out.badSex)}));
    """
    f = tmp_path / "pc.js"
    f.write_text(script, encoding="utf-8")
    res = subprocess.run(["node", str(f)], capture_output=True, text=True, check=True)
    o = json.loads(res.stdout)
    assert o["full"] == {"done": 6, "total": 6, "missing": []}
    assert o["empty"]["done"] == 0 and len(o["empty"]["missing"]) == 6
    assert o["none"]["done"] == 0
    assert o["part"] == {"done": 3, "total": 6, "missing": ["fcmax", "css", "run_pace"]}
    assert o["badSex"] == {"done": 5, "total": 6, "missing": ["sexo"]}


def test_pagina_perfil_tiene_selector_y_medidor():
    html = (ROOT / "athlete_profile.html").read_text(encoding="utf-8")
    assert 'id="p-sexo"' in html and 'id="profile-meter"' in html
    i18n = (ROOT / "i18n.js").read_text(encoding="utf-8")
    assert i18n.count("prof_label_sex:") == 3
    assert i18n.count("prof_meter_title:") == 3
    assert i18n.count("bl_beta_badge:") == 3


def test_blood_labs_html_beta_y_aviso():
    html = (ROOT / "blood_labs.html").read_text(encoding="utf-8")
    assert 'class="bl-beta"' in html and 'id="sex-missing-banner"' in html
