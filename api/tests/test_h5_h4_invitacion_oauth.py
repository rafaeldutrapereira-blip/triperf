"""H5-H4: invitacion con verificacion por correo y state OAuth de un solo uso."""
import base64
import json
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from urllib.parse import unquote

import pytest

from api import intervals_connector as ic
from api import provider_oauth
from api.models import CoachAthlete, PasswordResetToken, ProviderOAuthState, User
from api.routes import auth_routes, strava_routes as sr
from api.auth import hash_password, verify_password
from .conftest import auth_headers, login

INV = "invitado@test.com"
PW = "GoodPass123"


@pytest.fixture
def invited(db, coach_user):
    u = User(email=INV, nombre="Inv", password_hash=hash_password("x" * 20), rol="atleta",
             plan_nivel="agegroup", activo=False, pending_invite=True)
    db.add(u)
    db.flush()
    db.add(CoachAthlete(coach_id=coach_user.id, athlete_id=u.id, status="pending"))
    db.commit()
    return u


@pytest.fixture
def mails(monkeypatch):
    sent = []
    import api.mailer as mailer
    monkeypatch.setattr(mailer, "send_email", lambda to, subj, html, **k: sent.append((to, html)) or True)
    monkeypatch.setattr(auth_routes, "send_welcome", lambda *a, **k: None)
    return sent


def _reg(client, **extra):
    return client.post("/api/auth/register", json={"email": INV, "nombre": "Inv", "password": PW, **extra})


def _claim_token(mails):
    return unquote(re.search(r"claim=([^&\"]+)", mails[-1][1]).group(1))


def test_reclamar_sin_verificar_correo_se_rechaza(client, db, invited, mails):
    r = _reg(client)
    assert r.status_code == 202 and r.json()["code"] == "invite_verification_sent"
    assert "access_token" not in r.json()
    db.refresh(invited)
    assert invited.pending_invite is True and invited.activo is False
    assert not verify_password(PW, invited.password_hash)
    assert db.query(CoachAthlete).one().status == "pending"
    assert mails and mails[-1][0] == INV  # el enlace va al correo invitado, no al solicitante


def test_token_invalido_no_reclama(client, db, invited, mails):
    assert _reg(client, claim_token="inventado").status_code == 202
    db.refresh(invited)
    assert invited.pending_invite is True


def test_con_enlace_activa_vinculos_y_es_de_un_solo_uso(client, db, invited, mails):
    _reg(client)
    tok = _claim_token(mails)
    r = _reg(client, claim_token=tok)
    assert r.status_code == 201 and r.json()["access_token"]
    db.refresh(invited)
    assert invited.pending_invite is False and invited.activo is True
    assert verify_password(PW, invited.password_hash)
    assert db.query(CoachAthlete).one().status == "active"
    # reutilizar el token: la cuenta ya no es invitacion -> 409 legitimo
    assert _reg(client, claim_token=tok).status_code == 409


def test_token_expirado_o_de_otro_usuario_se_rechaza(client, db, invited, mails, athlete_user):
    raw, raw2 = "tok-expirado", "tok-ajeno"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(PasswordResetToken(token_hash=auth_routes._prt_hash(raw), user_id=invited.id,
                              expires_at=now - timedelta(minutes=1)))
    db.add(PasswordResetToken(token_hash=auth_routes._prt_hash(raw2), user_id=athlete_user.id,
                              expires_at=now + timedelta(hours=1)))
    db.commit()
    assert _reg(client, claim_token=raw).status_code == 202
    assert _reg(client, claim_token=raw2).status_code == 202
    db.refresh(invited)
    assert invited.pending_invite is True


def test_409_solo_si_el_email_ya_esta_registrado(client, athlete_user, mails):
    r = client.post("/api/auth/register", json={"email": "athlete@test.com", "nombre": "A", "password": PW})
    assert r.status_code == 409


def test_no_reenvia_correo_en_menos_de_un_minuto(client, db, invited, mails):
    _reg(client)
    _reg(client)
    assert len(mails) == 1


# ── H4 ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def me(db, athlete_user):
    athlete_user.plan_nivel = "elite"
    db.commit()
    return athlete_user


def _forged(uid):
    return base64.urlsafe_b64encode(json.dumps({"uid": uid}).encode()).decode()


def _st(url):
    return unquote(re.search(r"state=([^&]+)", url).group(1))


def _hdr(client):
    h = auth_headers(login(client, "athlete@test.com", "AthlPass123"))
    client.cookies.clear()
    return h


@pytest.fixture
def ivl(monkeypatch):
    monkeypatch.setattr(ic, "CLIENT_ID", "id")
    monkeypatch.setattr(ic, "CLIENT_SECRET", "sec")
    monkeypatch.setattr(ic, "exchange_code", AsyncMock(return_value={"access_token": "t", "scope": "ACTIVITY:READ"}))
    monkeypatch.setattr(ic, "fetch_athlete_id", AsyncMock(return_value="i1"))


def _connect_ivl(client):
    r = client.get("/api/integrations/intervals/connect", headers=_hdr(client), follow_redirects=False)
    return _st(r.headers["location"])


def test_intervals_state_forjado_se_rechaza(client, db, me, ivl):
    r = client.get(f"/api/integrations/intervals/callback?code=abc&state={_forged(me.id)}", follow_redirects=False)
    assert r.status_code == 400
    db.refresh(me)
    assert me.intervals_access_token is None


def test_intervals_state_feliz_y_reutilizado(client, db, me, ivl):
    st = _connect_ivl(client)
    assert "." in st and db.query(ProviderOAuthState).count() == 1
    r = client.get(f"/api/integrations/intervals/callback?code=abc&state={st}", follow_redirects=False)
    assert r.headers["location"].endswith("indoor_workout.html?intervals=connected")
    db.expire_all()
    db.refresh(me)
    assert me.intervals_access_token and db.query(ProviderOAuthState).count() == 0
    r2 = client.get(f"/api/integrations/intervals/callback?code=abc&state={st}", follow_redirects=False)
    assert r2.status_code == 400


def test_intervals_state_expirado_y_de_otro_proveedor(client, db, me, ivl):
    st = _connect_ivl(client)
    db.query(ProviderOAuthState).update({"expires_at": datetime.utcnow() - timedelta(minutes=1)})
    db.commit()
    assert client.get(f"/api/integrations/intervals/callback?code=a&state={st}").status_code == 400
    polar = provider_oauth.create_state(db, me.id, "polar")
    assert client.get(f"/api/integrations/intervals/callback?code=a&state={polar}").status_code == 400


@pytest.fixture
def strava(monkeypatch):
    monkeypatch.setattr(sr, "_CLIENT_ID", "sid")
    monkeypatch.setattr(sr, "_CLIENT_SECRET", "ssec")


class _Resp:
    status_code = 200

    def json(self):
        return {"access_token": "a", "refresh_token": "r", "expires_at": 9999999999, "athlete": {"id": 7}}


class _Client:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        return _Resp()


def test_strava_state_forjado_reutilizado_y_feliz(client, db, me, strava, monkeypatch):
    monkeypatch.setattr(sr.httpx, "AsyncClient", _Client)
    r = client.get(f"/api/strava/callback?code=abc&state={_forged(me.id)}", follow_redirects=False)
    assert r.status_code == 400
    loc = client.get("/api/strava/connect", headers=_hdr(client), follow_redirects=False).headers["location"]
    st = _st(loc)
    ok = client.get(f"/api/strava/callback?code=abc&state={st}", follow_redirects=False)
    assert ok.headers["location"].endswith("strava=connected")
    db.expire_all()
    db.refresh(me)
    assert me.strava_access_token
    assert client.get(f"/api/strava/callback?code=abc&state={st}", follow_redirects=False).status_code == 400
