"""
Tests — asignación automática de equipamiento (assign_gear), Sprint 3 del
módulo de Equipamiento. Contra la BD real de test, con actividades reales
(GarminActivity) y equipo real -- sin mocks del motor de asignación.
"""
import uuid

from ..models import GarminActivity, RunningShoe, Bike, BikeComponent, ShoeActivityLink, BikeActivityLink
from ..services.gear_service import assign_gear


def _make_activity(db, user_id, sport, dist_km=10.0, dur_min=50.0):
    act = GarminActivity(
        id=str(uuid.uuid4()), user_id=user_id, activity_id=str(uuid.uuid4()),
        sport=sport, date_iso="2026-08-20", date_label="2026-08-20",
        dur_min=dur_min, dist_km=dist_km,
    )
    db.add(act)
    db.commit()
    db.refresh(act)
    return act


class TestAssignShoe:
    def test_run_activity_assigns_to_default_rodaje_shoe(self, db, athlete_user):
        shoe = RunningShoe(user_id=athlete_user.id, brand="Hoka", model="Clifton", default_for_json='["rodaje"]')
        db.add(shoe)
        db.commit()

        act = _make_activity(db, athlete_user.id, "run", dist_km=12.5)
        assign_gear(db, act)
        db.commit()

        link = db.query(ShoeActivityLink).filter(ShoeActivityLink.activity_id == act.id).first()
        assert link is not None
        assert link.distance_km == 12.5

        db.refresh(shoe)
        assert shoe.accumulated_km == 12.5

    def test_run_activity_without_default_shoe_stays_unassigned(self, db, athlete_user):
        db.add(RunningShoe(user_id=athlete_user.id, brand="Hoka", model="Clifton"))
        db.commit()

        act = _make_activity(db, athlete_user.id, "run", dist_km=8.0)
        assign_gear(db, act)
        db.commit()

        link = db.query(ShoeActivityLink).filter(ShoeActivityLink.activity_id == act.id).first()
        assert link is None

    def test_repeated_sync_does_not_double_count(self, db, athlete_user):
        shoe = RunningShoe(user_id=athlete_user.id, brand="Hoka", model="Clifton", default_for_json='["rodaje"]')
        db.add(shoe)
        db.commit()

        act = _make_activity(db, athlete_user.id, "run", dist_km=10.0)
        assign_gear(db, act)
        db.commit()
        assign_gear(db, act)  # re-sync mismo activity_id
        db.commit()

        links = db.query(ShoeActivityLink).filter(ShoeActivityLink.activity_id == act.id).all()
        assert len(links) == 1
        db.refresh(shoe)
        assert shoe.accumulated_km == 10.0

    def test_retired_shoe_not_used_as_default(self, db, athlete_user):
        shoe = RunningShoe(
            user_id=athlete_user.id, brand="Hoka", model="Clifton",
            default_for_json='["rodaje"]', status="retired",
        )
        db.add(shoe)
        db.commit()

        act = _make_activity(db, athlete_user.id, "run", dist_km=10.0)
        assign_gear(db, act)
        db.commit()

        link = db.query(ShoeActivityLink).filter(ShoeActivityLink.activity_id == act.id).first()
        assert link is None


class TestAssignBike:
    def test_bike_activity_fans_out_to_all_active_components(self, db, athlete_user):
        bike = Bike(user_id=athlete_user.id, brand="Canyon", model="Aeroad", is_default=True)
        db.add(bike)
        db.commit()

        chain = BikeComponent(bike_id=bike.id, component_type="cadena", tracking_unit="km", target_value=3000)
        tires = BikeComponent(bike_id=bike.id, component_type="cubiertas", tracking_unit="horas", target_value=500)
        battery = BikeComponent(bike_id=bike.id, component_type="bateria_grupo", tracking_unit="carga_pct", target_value=100, charge_pct=90)
        db.add_all([chain, tires, battery])
        db.commit()

        act = _make_activity(db, athlete_user.id, "bike", dist_km=40.0, dur_min=90.0)
        assign_gear(db, act)
        db.commit()

        link = db.query(BikeActivityLink).filter(BikeActivityLink.activity_id == act.id).first()
        assert link is not None
        assert link.distance_km == 40.0
        assert link.duration_s == 90.0 * 60.0

        db.refresh(chain)
        db.refresh(tires)
        db.refresh(battery)
        assert chain.accumulated_value == 40.0
        assert tires.accumulated_value == 1.5  # 90 min = 1.5 h
        assert battery.accumulated_value == 0.0  # nunca se toca por fan-out
        assert battery.charge_pct == 90  # sin cambios

    def test_no_default_bike_stays_unassigned(self, db, athlete_user):
        db.add(Bike(user_id=athlete_user.id, brand="Canyon", model="Aeroad", is_default=False))
        db.commit()

        act = _make_activity(db, athlete_user.id, "bike", dist_km=30.0)
        assign_gear(db, act)
        db.commit()

        link = db.query(BikeActivityLink).filter(BikeActivityLink.activity_id == act.id).first()
        assert link is None

    def test_inactive_component_excluded_from_fanout(self, db, athlete_user):
        bike = Bike(user_id=athlete_user.id, brand="Trek", model="Domane", is_default=True)
        db.add(bike)
        db.commit()

        replaced = BikeComponent(bike_id=bike.id, component_type="cadena", tracking_unit="km", target_value=3000, status="replaced")
        db.add(replaced)
        db.commit()

        act = _make_activity(db, athlete_user.id, "bike", dist_km=25.0)
        assign_gear(db, act)
        db.commit()

        db.refresh(replaced)
        assert replaced.accumulated_value == 0.0


class TestAssignGearOtherSports:
    def test_swim_activity_is_a_noop(self, db, athlete_user):
        act = _make_activity(db, athlete_user.id, "swim", dist_km=2.0)
        assign_gear(db, act)  # no debe lanzar ni crear ningún link
        db.commit()
        assert db.query(ShoeActivityLink).count() == 0
        assert db.query(BikeActivityLink).count() == 0


class TestLifeThresholdAlerts:
    """RESEND_API_KEY/VAPID_PRIVATE_KEY no están configurados en el entorno
    de test, así que mailer.send_email y send_push_to_user retornan de
    inmediato sin red real -- se ejercita el código real de decisión de
    umbral (last_alert_pct), no un mock de la capa de negocio."""

    def test_shoe_crossing_80pct_marks_last_alert_pct(self, db, athlete_user):
        shoe = RunningShoe(
            user_id=athlete_user.id, brand="Hoka", model="Clifton",
            default_for_json='["rodaje"]', target_km=100.0, accumulated_km=75.0,
        )
        db.add(shoe)
        db.commit()

        act = _make_activity(db, athlete_user.id, "run", dist_km=10.0)  # 85%
        assign_gear(db, act)
        db.commit()

        db.refresh(shoe)
        assert shoe.accumulated_km == 85.0
        assert shoe.last_alert_pct == 80

    def test_shoe_does_not_realert_same_threshold_on_next_sync(self, db, athlete_user):
        shoe = RunningShoe(
            user_id=athlete_user.id, brand="Hoka", model="Clifton",
            default_for_json='["rodaje"]', target_km=100.0, accumulated_km=82.0, last_alert_pct=80,
        )
        db.add(shoe)
        db.commit()

        act = _make_activity(db, athlete_user.id, "run", dist_km=2.0)  # 84%, sigue en banda 80
        assign_gear(db, act)
        db.commit()

        db.refresh(shoe)
        assert shoe.last_alert_pct == 80  # no reescribe ni reenvía

    def test_shoe_crossing_100pct_after_80_updates_to_100(self, db, athlete_user):
        shoe = RunningShoe(
            user_id=athlete_user.id, brand="Hoka", model="Clifton",
            default_for_json='["rodaje"]', target_km=100.0, accumulated_km=95.0, last_alert_pct=80,
        )
        db.add(shoe)
        db.commit()

        act = _make_activity(db, athlete_user.id, "run", dist_km=10.0)  # 105%
        assign_gear(db, act)
        db.commit()

        db.refresh(shoe)
        assert shoe.last_alert_pct == 100

    def test_bike_component_km_crossing_80pct_marks_alert(self, db, athlete_user):
        bike = Bike(user_id=athlete_user.id, brand="Canyon", model="Aeroad", is_default=True)
        db.add(bike)
        db.commit()
        chain = BikeComponent(bike_id=bike.id, component_type="cadena", tracking_unit="km", target_value=100.0, accumulated_value=70.0)
        db.add(chain)
        db.commit()

        act = _make_activity(db, athlete_user.id, "bike", dist_km=15.0)  # 85%
        assign_gear(db, act)
        db.commit()

        db.refresh(chain)
        assert chain.accumulated_value == 85.0
        assert chain.last_alert_pct == 80

    def test_battery_component_never_gets_threshold_alert_from_sync(self, db, athlete_user):
        bike = Bike(user_id=athlete_user.id, brand="Canyon", model="Aeroad", is_default=True)
        db.add(bike)
        db.commit()
        battery = BikeComponent(bike_id=bike.id, component_type="bateria_grupo", tracking_unit="carga_pct", target_value=100.0, charge_pct=15)
        db.add(battery)
        db.commit()

        act = _make_activity(db, athlete_user.id, "bike", dist_km=50.0)
        assign_gear(db, act)
        db.commit()

        db.refresh(battery)
        assert battery.last_alert_pct is None
        assert battery.accumulated_value == 0.0
