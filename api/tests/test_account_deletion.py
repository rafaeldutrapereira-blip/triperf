"""
GDPR: DELETE /api/auth/account debe funcionar para cualquier usuario, también
para los que ya tienen filas en tablas con FK a users (snapshots de riesgo de
lesión, notificaciones, etc.). Bug original: la ruta solo borraba 4 tablas, y
el ORM ponía NULL en injury_risk_snapshots.user_id (NOT NULL) -> 500.
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
    """Filas que aún apuntan a user_id en cualquier columna FK a users."""
    total = {}
    for table, col in _fk_user_columns():
        n = db.execute(select(table).where(col == user_id)).all()
        if n:
            total[f"{table.name}.{col.name}"] = len(n)
    return total


def test_delete_account_with_snapshots_and_notifications_leaves_no_orphans(client, db, athlete_user):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    coach = User(
        email="coach-del@test.com", nombre="Coach Del", password_hash=hash_password("CoachDel123"),
        rol="coach", plan_nivel="agegroup", activo=True,
    )
    db.add(coach)
    db.commit()
    db.refresh(coach)

    # Caso del bug: fila NOT NULL que la ruta vieja no borraba.
    db.add(InjuryRiskSnapshot(user_id=athlete_user.id, date_iso="2026-10-18"))
    # Caso nullable: notificación al coach generada por el atleta. Debe sobrevivir
    # con actor_id en NULL (no es contenido del atleta que haya que borrar).
    notif = CommunityNotification(
        user_id=coach.id, actor_id=athlete_user.id, notif_type="follow", created_at=now,
    )
    db.add(notif)
    db.commit()
    notif_id = notif.id

    uid = athlete_user.id  # guardar antes: tras el borrado el objeto ya no es legible
    token = login(client, "athlete@test.com", "AthlPass123")
    r = client.delete("/api/auth/account", headers=auth_headers(token))

    assert r.status_code == 200, r.text
    db.expire_all()  # la sesión del test tiene caché de identidad: releer desde la base
    assert _count_refs(db, uid) == {}, "quedaron filas que apuntan al usuario borrado"
    assert db.get(User, uid) is None
    kept = db.get(CommunityNotification, notif_id)
    assert kept is not None, "la notificación del coach no debe borrarse"
    assert kept.actor_id is None
    assert kept.user_id == coach.id


def test_delete_account_without_dependents_still_works(client, db, athlete_user):
    uid = athlete_user.id
    token = login(client, "athlete@test.com", "AthlPass123")
    r = client.delete("/api/auth/account", headers=auth_headers(token))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(User, uid) is None
