"""SEXO — campo sexo en el Perfil de la app (screen-profile)."""
from pathlib import Path

import pytest

from .conftest import login

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "athlete-app.html").read_text(encoding="utf-8")
PROF = APP[APP.index('id="screen-profile"'):APP.index('id="screen-raceday"')]


@pytest.fixture
def headers(client, athlete_user):
    token = login(client, "athlete@test.com", "AthlPass123")
    return {"Authorization": f"Bearer {token}"}


def test_form_tiene_select_con_mismos_valores_que_la_web():
    assert 'id="pf-sexo"' in PROF
    sel = PROF[PROF.index('id="pf-sexo"'):]
    sel = sel[:sel.index("</select>")]
    for v in ('value=""', 'value="f"', 'value="m"'):
        assert v in sel
    for k in ("prof_sex_opt_none", "prof_sex_opt_f", "prof_sex_opt_m"):
        assert k in sel
    assert 'data-i18n-title="prof_label_sex"' in PROF


def test_app_lee_y_guarda_sexo():
    load = APP[APP.index("function loadProfileMobile"):APP.index("function saveProfileMobile")]
    assert "getElementById('pf-sexo').value = p.sexo" in load
    save = APP[APP.index("function saveProfileMobile"):]
    save = save[:save.index("fetch(")]
    assert "sexo: document.getElementById('pf-sexo').value" in save


def test_i18n_etiqueta_en_los_tres_idiomas():
    i18n = (ROOT / "i18n.js").read_text(encoding="utf-8")
    assert i18n.count("prof_label_sex:") >= 3


def test_guardar_persiste_y_perfil_abierto_devuelve_valor(client, db, athlete_user, headers):
    r = client.patch("/api/athlete/profile", json={"sexo": "f"}, headers=headers)
    assert r.status_code == 200, r.text
    db.refresh(athlete_user)
    assert athlete_user.sexo == "f"
    assert client.get("/api/athlete/profile", headers=headers).json()["sexo"] == "f"
    client.patch("/api/athlete/profile", json={"sexo": ""}, headers=headers)
    db.refresh(athlete_user)
    assert athlete_user.sexo is None
