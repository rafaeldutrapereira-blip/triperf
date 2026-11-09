"""COACH-TABLERO-PERF (BUILD 365): fixture deterministico de N atletas + contador de queries.

Se usa en el test de contrato (queries independientes de N) y para las
mediciones antes/despues del reporte del sprint.
"""
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import event

from api.auth import hash_password
from api.models import (
    User, CoachAthlete, Group, GroupMember, WorkoutTemplate, AssignedWorkout,
    WorkoutLog, AIAthleteContext, AIInsight, GarminHealthDaily,
)

SPORTS = ["swim", "bike", "run", "strength", "bike"]


def _naive_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def seed_team(db, coach, n=200, prefix="p", week_start=None):
    """Siembra n atletas del coach con datos en todas las tablas que leen los tableros.

    Determinista (sin azar): la variedad sale de i % k.
    """
    today = date.today()
    now = _naive_now()
    week_start = week_start or (today - timedelta(days=today.weekday()))
    g = Group(coach_id=coach.id, nombre=f"G-{prefix}")
    db.add(g)
    tpls = []
    for k, sp in enumerate(SPORTS):
        t = WorkoutTemplate(coach_id=coach.id, sport=sp, nombre=f"T{k}-{sp}", dur_min=40 + k, tss=40 + k)
        db.add(t)
        tpls.append(t)
    db.flush()
    users = []
    for i in range(n):
        u = User(email=f"{prefix}{i}@perf.com", nombre=f"Atleta {prefix}{i:03d}",
                 password_hash="x", rol="athlete", plan_nivel="basico", activo=True,
                 garmin_email=(f"g{i}@x.com" if i % 3 == 0 else None))
        users.append(u)
    db.add_all(users)
    db.flush()
    for i, u in enumerate(users):
        db.add(CoachAthlete(coach_id=coach.id, athlete_id=u.id, status="active"))
        if i % 2 == 0:
            db.add(GroupMember(group_id=g.id, athlete_id=u.id))
        # contexto IA (1 de cada 7 sin contexto)
        if i % 7 != 0:
            db.add(AIAthleteContext(
                user_id=u.id, current_ctl=40 + i % 30, current_atl=45 + i % 25, current_tsb=-5 + i % 11,
                current_acwr=0.8 + (i % 9) * 0.1, current_hrv=50 + i % 20,
                current_readiness=30 + (i * 7) % 70, injury_risk_score=(i % 10) / 10,
                days_to_race=(i % 40) if i % 4 else None,
                context_built_at=now - timedelta(hours=1 + i % 30)))
        if i % 3 == 0:
            db.add(GarminHealthDaily(user_id=u.id, date_iso=today.isoformat(),
                                     hrv_last_night=55 + i % 15, body_battery_end=40 + i % 50))
        for k in range(i % 5):  # insights: 0..4, algunos descartados/expirados
            db.add(AIInsight(
                user_id=u.id, type="low_hrv", severity=["info", "warning", "critical"][(i + k) % 3],
                title=f"I{i}-{k}", body="b", created_at=now - timedelta(minutes=10 * (k + 1) + i),
                dismissed_at=(now if k == 3 else None),
                expires_at=(now - timedelta(days=1) if k == 2 and i % 2 else None)))
        # asignaciones: 6 en la ventana de 14 dias hacia atras, 1 en cada uno de 5 dias de la semana del Gantt
        days = {today - timedelta(days=d) for d in range(0, 14, 2 + i % 3)}
        days |= {week_start + timedelta(days=d) for d in range(0, 7, 1 + i % 3)}
        for j, d in enumerate(sorted(days)):
            tpl = tpls[(i + j) % len(tpls)]
            a = AssignedWorkout(template_id=tpl.id, athlete_id=u.id, date_iso=d.isoformat())
            db.add(a)
            db.flush()
            if (i + j) % 2 == 0:
                db.add(WorkoutLog(user_id=u.id, assignment_id=a.id, completado=(i + j) % 4 != 0, rpe=5,
                                  logged_at=now - timedelta(days=(i + j) % 12)))
    db.commit()
    return users


class QueryCounter:
    def __init__(self):
        self.n = 0
        self.ms = 0.0


@contextmanager
def count_queries(engine):
    qc = QueryCounter()

    def _before(conn, cursor, statement, params, context, executemany):
        qc.n += 1

    event.listen(engine, "before_cursor_execute", _before)
    t0 = time.perf_counter()
    try:
        yield qc
    finally:
        qc.ms = (time.perf_counter() - t0) * 1000
        event.remove(engine, "before_cursor_execute", _before)
