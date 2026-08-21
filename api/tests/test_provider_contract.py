"""
Sprint 51 (multi-marca) — contract test parametrizado.

Cualquier WearableProvider (Garmin hoy; Wahoo/Polar/Coros más adelante)
debe poder normalizar sus fixtures reales a un dict con estos campos
mínimos válidos. Este test es el gate obligatorio antes de aceptar un
provider nuevo — ver docs/plan-multi-brand-wearables.md.

Los fixtures en api/tests/fixtures/<provider>/*.json son actividades
REALES anonimizadas (nombre/coords/fotos/ids reemplazados por valores
demo, métricas de esfuerzo intactas) — nunca JSON inventado a mano.
"""
from __future__ import annotations

import glob
import json
import os

import pytest

from api.garmin_pull_service import _parse_garmin_activity
from api.providers.wahoo import normalize_wahoo_workout

_FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

_VALID_SPORTS = {"swim", "bike", "run", "gym", "other"}


def _load_fixtures(provider: str) -> list[tuple[str, dict]]:
    paths = sorted(glob.glob(os.path.join(_FIXTURES_DIR, provider, "*.json")))
    fixtures = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            fixtures.append((os.path.basename(p), json.load(f)))
    return fixtures


GARMIN_FIXTURES = _load_fixtures("garmin")
WAHOO_FIXTURES = _load_fixtures("wahoo")


def assert_normalized_activity_contract(normalized: dict, fixture_name: str, has_hr_or_power: bool):
    """Reglas mínimas que CUALQUIER provider debe cumplir al normalizar
    una actividad cruda al formato interno de LabX."""
    assert normalized.get("sport") in _VALID_SPORTS, (
        f"[{fixture_name}] sport inválido: {normalized.get('sport')!r}"
    )
    assert normalized.get("date_iso"), f"[{fixture_name}] date_iso vacío"
    # formato YYYY-MM-DD
    assert len(normalized["date_iso"]) == 10 and normalized["date_iso"][4] == "-", (
        f"[{fixture_name}] date_iso con formato inesperado: {normalized['date_iso']!r}"
    )
    assert isinstance(normalized.get("dur_min"), (int, float)) and normalized["dur_min"] >= 0, (
        f"[{fixture_name}] dur_min inválido: {normalized.get('dur_min')!r}"
    )
    if has_hr_or_power:
        assert normalized.get("tss") is not None, (
            f"[{fixture_name}] tss es None con HR/power presente en el crudo"
        )


@pytest.mark.skipif(not GARMIN_FIXTURES, reason="sin fixtures de Garmin")
@pytest.mark.parametrize("fixture_name,raw", GARMIN_FIXTURES, ids=[f[0] for f in GARMIN_FIXTURES])
def test_garmin_provider_contract(fixture_name, raw):
    normalized = _parse_garmin_activity(raw, ftp=250, fcmax=190)
    has_hr_or_power = bool(raw.get("averageHR") or raw.get("avgPower"))
    assert_normalized_activity_contract(normalized, fixture_name, has_hr_or_power)


@pytest.mark.skipif(not WAHOO_FIXTURES, reason="sin fixtures de Wahoo")
@pytest.mark.parametrize("fixture_name,raw", WAHOO_FIXTURES, ids=[f[0] for f in WAHOO_FIXTURES])
def test_wahoo_provider_contract(fixture_name, raw):
    normalized = normalize_wahoo_workout(raw, ftp=250, fcmax=190)
    summary = raw.get("workout_summary") or {}
    has_hr_or_power = bool(summary.get("heart_rate_avg") or summary.get("power_avg"))
    assert_normalized_activity_contract(normalized, fixture_name, has_hr_or_power)


def test_at_least_one_fixture_per_known_provider():
    """Recordatorio duro: si se agrega un provider nuevo (Polar/Coros) sin
    fixtures reales acá, este test falla — no se puede mergear un provider
    sin al menos un fixture real de su developer portal oficial.

    Garmin: 8 fixtures reales de nuestro propio cache de sync (>=3 exigido).
    Wahoo: la documentación oficial de Wahoo Cloud API solo publica UN
    ejemplo real de 'Get a Workout Response' (siempre la misma actividad
    'Friday Fun'/'Easy Ride', repetida sin variación en cada endpoint CRUD
    de workouts) — no hay más variedad real disponible sin una app
    aprobada + un usuario real conectado. Exigir 3 acá forzaría a inventar
    2 fixtures falsos, que es exactamente lo que este plan prohíbe. Por
    eso el mínimo para Wahoo es 1, con la brecha documentada explícitamente
    como gap a cerrar en el Sprint del piloto real (ver
    docs/plan-multi-brand-wearables.md)."""
    assert len(GARMIN_FIXTURES) >= 3, "Se esperaban al menos 3 fixtures reales de Garmin"
    assert len(WAHOO_FIXTURES) >= 1, "Se esperaba al menos 1 fixture real (de la doc oficial) de Wahoo"
