"""
GDPR: un usuario que abrió el dashboard (y tiene registros asociados) puede borrar
su cuenta: DELETE /api/auth/account responde 200 y no queda ninguna fila que lo
apunte en ninguna tabla con FK a users.
"""
from datetime import datetime, timezone

from sqlalchemy import select

from api.database import Base
from api.models import CommunityNotification, InjuryRiskSnapshot, User
from api.auth import hash_password
from .conftest import auth_headers, login


def _fk_user_columns():
    out = []
    for table in Base.metadata.sorted_tables:
        for fk in table.foreign_keys:
            if fk.column.table.name == "users":
                out.append((table, fk.parent))
    return out


def _count_refs(db, user_id):
    total = {}
    for table, col in _fk_user_columns():
        n = db.execute(select(table).where(col == user_id)).all()
        if n:
            total[f"{table.name}.{col.name}"] = len(n)
    return total


def test_usuario_con_dashboard_puede_borrar_su_cuenta(client, db):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user = User(email="gdpr-dash@test.com", nombre="GDPR Dash", password_hash=hash_password("GdprDash123"),
                rol="atleta", plan_nivel="elite", activo=True)
    other = User(email="gdpr-otro@test.com", nombre="Otro", password_hash=hash_password("Otro12345"),
                 rol="atleta", plan_nivel="basico", activo=True)
    db.add_all([user, other])
    db.commit()
    db.refresh(user)
    db.refresh(other)

    # Registros que el uso normal deja: snapshot de riesgo (NOT NULL) y una notificación
    # que el propio usuario generó hacia otro (actor_id nullable).
    db.add(InjuryRiskSnapshot(user_id=user.id, date_iso="2026-10-20"))
    db.add(CommunityNotification(user_id=other.id, actor_id=user.id, notif_type="follow", created_at=now))
    db.commit()

    token = login(client, "gdpr-dash@test.com", "GdprDash123")
    # Abrir el dashboard: genera/toca sus datos derivados.
    r_dash = client.get("/api/athlete/dashboard", headers=auth_headers(token))
    assert r_dash.status_code == 200, r_dash.text

    uid = user.id
    r = client.delete("/api/auth/account", headers=auth_headers(token))
    assert r.status_code == 200, r.text

    db.expire_all()
    assert db.get(User, uid) is None
    assert _count_refs(db, uid) == {}, "quedaron filas que apuntan al usuario borrado"
    # La notificación de otro usuario se conserva, desvinculada del actor borrado.
    notif = db.query(CommunityNotification).filter_by(user_id=other.id).one()
    assert notif.actor_id is None
    assert db.get(User, other.id) is not None
