"""

B1 — Gating de plan en servidor para módulos que antes solo se bloqueaban en el

cliente: Race Day, Comunidad, Mi Equipo, Plan de entrenamiento (calendario,

periodización, plantillas), Mi Huella (year-in-review) e Indoor.



Por cada endpoint: un atleta de plan inferior recibe 403; un atleta del plan

mínimo (o superior) no recibe 403; un coach bypasea el gating (has_feature).

"""

import re



import pytest



from api.auth import hash_password

from api.models import User

from .conftest import auth_headers, login





# (método, ruta, cuerpo, plan mínimo que debe pasar el gating)

GATED = [

    ("GET",  "/api/races", None, "agegroup"),

    ("GET",  "/api/races/goal-countdown", None, "agegroup"),

    ("GET",  "/api/community/feed", None, "agegroup"),

    ("GET",  "/api/community/groups", None, "agegroup"),

    ("GET",  "/api/community/notifications/count", None, "agegroup"),

    ("GET",  "/api/gear/shoes", None, "agegroup"),

    ("GET",  "/api/gear/bikes", None, "agegroup"),

    ("GET",  "/api/gear/summary", None, "agegroup"),

    ("GET",  "/api/calendar/upcoming", None, "agegroup"),

    ("GET",  "/api/calendar/monthly?year=2026&month=10", None, "agegroup"),

    ("GET",  "/api/athlete/phases", None, "agegroup"),

    ("GET",  "/api/athlete/compliance-trend", None, "agegroup"),

    ("GET",  "/api/athlete/year-in-review", None, "agegroup"),

    ("POST", "/api/athlete/indoor-workout/send-to-garmin", {}, "elite"),

]



RANK = {"basico": 0, "agegroup": 1, "elite": 2}





def _slug(path: str) -> str:

    return re.sub(r"[^a-z0-9]", "", path.lower())[:40]





def _token(client, db, email: str, plan: str, rol: str = "atleta") -> str:

    u = User(

        email=email, nombre="Gating B1", password_hash=hash_password("GatingB1-Pass"),

        rol=rol, plan_nivel=plan, activo=True,

    )

    db.add(u)

    db.commit()

    return login(client, email, "GatingB1-Pass")





def _call(client, method, path, body, token):

    kwargs = {"headers": auth_headers(token)}

    if body is not None:

        kwargs["json"] = body

    return client.request(method, path, **kwargs)





@pytest.mark.parametrize("method,path,body,minimo", GATED, ids=[g[1].split("?")[0] for g in GATED])

def test_basico_recibe_403(client, db, method, path, body, minimo):

    token = _token(client, db, f"b1-basico-{_slug(path)}@test.com", "basico")

    r = _call(client, method, path, body, token)

    assert r.status_code == 403, f"{method} {path} debería bloquear basico: {r.status_code} {r.text[:200]}"





@pytest.mark.parametrize("method,path,body,minimo", GATED, ids=[g[1].split("?")[0] for g in GATED])

def test_plan_minimo_pasa_el_gating(client, db, method, path, body, minimo):

    token = _token(client, db, f"b1-min-{_slug(path)}@test.com", minimo)

    r = _call(client, method, path, body, token)

    assert r.status_code != 403, f"{method} {path} bloqueó a {minimo}: {r.text[:200]}"





@pytest.mark.parametrize("method,path,body,minimo", GATED, ids=[g[1].split("?")[0] for g in GATED])

def test_coach_bypasea_el_gating(client, db, method, path, body, minimo):

    token = _token(client, db, f"b1-coach-{_slug(path)}@test.com", "basico", rol="coach")

    r = _call(client, method, path, body, token)

    assert r.status_code != 403, f"{method} {path} bloqueó a coach: {r.text[:200]}"





@pytest.mark.parametrize("method,path,body,minimo", GATED, ids=[g[1].split("?")[0] for g in GATED])

def test_sin_token_401(client, method, path, body, minimo):

    kwargs = {}

    if body is not None:

        kwargs["json"] = body

    r = client.request(method, path, **kwargs)

    assert r.status_code == 401, f"{method} {path} sin token: {r.status_code}"





def test_agegroup_no_pasa_indoor(client, db):

    # Indoor es addon/Elite: agegroup no lo incluye (B1 no cambia la política).

    token = _token(client, db, "b1-indoor-ag@test.com", "agegroup")

    r = _call(client, "POST", "/api/athlete/indoor-workout/send-to-garmin", {}, token)

    assert r.status_code == 403





def test_plan_basic_del_cliente_se_normaliza_a_basico(client, db):

    # El cliente manda/usa 'basic'; la BD guarda 'basico'. Ambos deben tratarse igual.

    from api.plan_features import normalize_plan

    assert normalize_plan("basic") == "basico"

    assert normalize_plan("BASIC") == "basico"

    assert normalize_plan("basico") == "basico"

    assert normalize_plan(None) == "basico"

    assert normalize_plan("elite") == "elite"

