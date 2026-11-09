"""PILA 374 DEDUPE: la misma sesion por varias vias se marca (nunca se borra), las lecturas
y la carga de entrenamiento no la cuentan dos veces, y sesiones distintas no se fusionan."""
import importlib.util
from datetime import date
from pathlib import Path

from api import activity_dedupe as dd
from api.models import GarminActivity, GarminTrainingLoad
from api.services.training_service import recalculate_training_load

ROOT = Path(__file__).resolve().parents[2]
DAY = "2026-11-09"


def _add(db, uid, aid, sport="gym", dur=43, dist=0.0, name="x", tss=0.0, day=DAY, **kw):
    r = GarminActivity(user_id=uid, activity_id=aid, sport=sport, dur_min=dur, dist_km=dist,
                       name=name, tss=tss, date_iso=day, **kw)
    db.add(r)
    db.flush()
    return r


def _raw(db):
    return db.query(GarminActivity).execution_options(include_duplicates=True)


def _canonical_pair(db, uid):
    a = _add(db, uid, "9001", dur=43, name="Strength")                      # Garmin (sin prefijo)
    b = _add(db, uid, "intervals:i1", dur=50, name="Entrenamiento con pesas matutino",
             avg_hr=120, calories=200)
    db.commit()
    return a, b


def _load_script():
    spec = importlib.util.spec_from_file_location("dedupe_activities",
                                                  ROOT / "scripts" / "dedupe_activities.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_caso_canonico_se_agrupa(db, athlete_user):
    a, b = _canonical_pair(db, athlete_user.id)
    groups = dd.find_duplicate_groups(db, athlete_user.id)
    assert len(groups) == 1
    g = groups[0]
    assert {g["canonical"].id} | {d.id for d in g["duplicates"]} == {a.id, b.id}
    assert g["canonical"].id == b.id  # la mas completa (mas campos)


def test_deportes_distintos_no_se_agrupan(db, athlete_user):
    _add(db, athlete_user.id, "1", sport="run", dur=45, dist=8.0)
    _add(db, athlete_user.id, "intervals:2", sport="bike", dur=45, dist=8.0)
    db.commit()
    assert dd.find_duplicate_groups(db, athlete_user.id) == []


def test_mismo_deporte_duraciones_claramente_distintas_no_se_agrupan(db, athlete_user):
    # Dos sesiones reales el mismo dia (manana corta, tarde larga), de origenes distintos.
    _add(db, athlete_user.id, "1", sport="run", dur=30, dist=5.0)
    _add(db, athlete_user.id, "intervals:2", sport="run", dur=90, dist=16.0)
    db.commit()
    assert dd.find_duplicate_groups(db, athlete_user.id) == []


def test_misma_via_no_se_fusiona_ni_otro_dia(db, athlete_user):
    _add(db, athlete_user.id, "1", dur=45)
    _add(db, athlete_user.id, "2", dur=46)                       # ambas Garmin: dos sesiones
    _add(db, athlete_user.id, "intervals:3", dur=45, day="2026-11-08")  # otro dia
    db.commit()
    assert dd.find_duplicate_groups(db, athlete_user.id) == []


def test_distancia_distinta_no_agrupa(db, athlete_user):
    _add(db, athlete_user.id, "1", sport="run", dur=50, dist=10.0)
    _add(db, athlete_user.id, "strava_2", sport="run", dur=50, dist=5.0)
    db.commit()
    assert dd.find_duplicate_groups(db, athlete_user.id) == []


def test_hora_distinta_no_agrupa_si_ambas_tienen_hora(db, athlete_user):
    from datetime import datetime
    a = _add(db, athlete_user.id, "1", dur=45)
    b = _add(db, athlete_user.id, "intervals:2", dur=45)
    a.start_local, b.start_local = datetime(2026, 11, 9, 7, 0), datetime(2026, 11, 9, 18, 0)
    assert dd.pair_score(a, b) is None
    b.start_local = datetime(2026, 11, 9, 7, 10)
    assert dd.pair_score(a, b) is not None


def test_dry_run_no_escribe_y_apply_es_idempotente(db, athlete_user):
    a, b = _canonical_pair(db, athlete_user.id)
    m = _load_script()
    lines = []
    r = m.run(db, apply=False, out=lines.append)
    assert r["groups"] == 1 and r["marked"] == 0
    assert all(x.duplicate_of_id is None for x in _raw(db).all())
    assert any("detectado" in l for l in lines)

    r1 = m.run(db, apply=True, out=lambda *_: None)
    assert r1["marked"] == 1
    marked = [x for x in _raw(db).all() if x.duplicate_of_id]
    assert len(marked) == 1 and marked[0].id == a.id and marked[0].duplicate_of_id == b.id
    assert marked[0].duplicate_reason
    assert _raw(db).count() == 2  # nunca se borra

    r2 = m.run(db, apply=True, out=lambda *_: None)
    assert r2["marked"] == 0 and r2["pending"] == 0


def test_lecturas_excluyen_duplicados_y_son_reversibles(db, athlete_user):
    a, b = _canonical_pair(db, athlete_user.id)
    assert db.query(GarminActivity).filter(GarminActivity.user_id == athlete_user.id).count() == 2
    dd.apply_groups(dd.find_duplicate_groups(db, athlete_user.id))
    db.commit()
    rows = db.query(GarminActivity).filter(GarminActivity.user_id == athlete_user.id).all()
    assert [r.id for r in rows] == [b.id]
    a.duplicate_of_id = None  # reversible
    db.commit()
    assert db.query(GarminActivity).filter(GarminActivity.user_id == athlete_user.id).count() == 2


def test_recalculate_training_load_no_cuenta_el_duplicado(db, athlete_user):
    today = date.today().isoformat()
    _add(db, athlete_user.id, "1", dur=60, tss=50.0, name="Strength", day=today)
    _add(db, athlete_user.id, "intervals:2", dur=62, tss=50.0, name="Pesas", avg_hr=110, day=today)
    db.commit()
    recalculate_training_load(db, athlete_user.id)
    db.commit()
    doble = db.query(GarminTrainingLoad).filter_by(user_id=athlete_user.id, date_iso=today).one().tss
    assert doble == 100.0
    dd.apply_groups(dd.find_duplicate_groups(db, athlete_user.id))
    db.commit()
    recalculate_training_load(db, athlete_user.id)
    db.commit()
    unico = db.query(GarminTrainingLoad).filter_by(user_id=athlete_user.id, date_iso=today).one().tss
    assert unico == 50.0


def test_ingesta_marca_al_vuelo(db, athlete_user):
    _add(db, athlete_user.id, "9001", dur=43, name="Strength")
    nueva = _add(db, athlete_user.id, "intervals:i1", dur=50, name="Pesas matutino", avg_hr=118)
    dup = dd.mark_new_activity(db, nueva)
    db.commit()
    assert dup is not None and dup.activity_id == "9001"
    assert dup.duplicate_of_id == nueva.id
    # una sesion distinta (otra hora/duracion) llegando despues no se marca
    otra = _add(db, athlete_user.id, "strava_77", dur=120, name="Largo")
    assert dd.mark_new_activity(db, otra) is None


def test_ingesta_intervals_real_marca_en_el_punto_de_insercion(db, athlete_user):
    from api import intervals_sync_service as iss
    _add(db, athlete_user.id, "9001", sport="gym", dur=43, name="Strength")
    db.commit()
    it = {"id": "i9", "start_date_local": f"{DAY}T07:30:00", "type": "WeightTraining",
          "name": "Pesas", "moving_time": 50 * 60}
    counters = {"ignored_fields": 0}
    # La fila de Garmin ya existe y coincide -> el dedupe previo de intervals la fusiona;
    # con una duracion fuera de su tolerancia (>10 min) pero dentro de la del matcher se importa y se marca.
    it["moving_time"] = 54 * 60
    assert iss._upsert_activity(db, athlete_user.id, it, counters) == "imported"
    db.commit()
    marked = [x for x in _raw(db).all() if x.duplicate_of_id]
    assert len(marked) == 1
    assert db.query(GarminActivity).filter(GarminActivity.user_id == athlete_user.id).count() == 1
