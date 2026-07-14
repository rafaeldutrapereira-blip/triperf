"""
compute_acwr_by_sport tenia un tope fijo de 120 dias -> los botones de
periodo 6 Meses/Ano/Todo en detalle.html?metric=acwr mostraban siempre el
mismo tramo (todos >=120 dias), pareciendo "congelados". Ahora usa el
historial completo real del atleta.
"""
import time
from datetime import date, timedelta

from ..models import GarminActivity
from ..services.training_service import compute_acwr_by_sport


def _add_activity(db, user_id, date_iso, sport, tss):
    db.add(GarminActivity(
        user_id=user_id, activity_id=f"{sport}-{date_iso}", sport=sport,
        date_iso=date_iso, date_label=date_iso, tss=tss,
    ))


def test_history_spans_beyond_120_days(db, athlete_user):
    """Actividad de hace 200 dias debe aparecer en el history devuelto."""
    old_date = (date.today() - timedelta(days=200)).isoformat()
    recent_date = (date.today() - timedelta(days=5)).isoformat()

    # Varias sesiones de run para que el chronic28 no quede en 0 durante el
    # tramo antiguo, y una reciente para tener datos "hoy".
    d = date.today() - timedelta(days=200)
    for i in range(35):
        _add_activity(db, athlete_user.id, (d + timedelta(days=i)).isoformat(), "run", 50.0)
    _add_activity(db, athlete_user.id, recent_date, "run", 60.0)
    db.commit()

    result = compute_acwr_by_sport(athlete_user.id, db)
    run_history = result["run"]["history"]
    assert run_history, "el history de run no deberia estar vacio"

    dates_in_history = {p["dt"] for p in run_history}
    # El tramo cerca del dia 200 (con datos reales) debe estar presente —
    # antes del fix, cualquier fecha mas vieja que 120 dias quedaba afuera.
    assert any(dt < (date.today() - timedelta(days=120)).isoformat() for dt in dates_in_history)


def test_no_activities_returns_empty_structure(db, athlete_user):
    result = compute_acwr_by_sport(athlete_user.id, db)
    for sport in ("swim", "bike", "run", "gym"):
        assert result[sport]["history"] == []
        assert result[sport]["insufficient_data"] is True


def test_large_history_performance(db, athlete_user):
    """~5 anos de actividad no deberian tardar mas de unos segundos."""
    start = date.today() - timedelta(days=5 * 365)
    for i in range(0, 5 * 365, 2):  # una sesion cada 2 dias
        _add_activity(db, athlete_user.id, (start + timedelta(days=i)).isoformat(), "bike", 70.0)
    db.commit()

    t0 = time.time()
    result = compute_acwr_by_sport(athlete_user.id, db)
    elapsed = time.time() - t0

    assert result["bike"]["history"]
    assert elapsed < 5.0, f"tardo {elapsed:.2f}s, demasiado lento para historial largo"
