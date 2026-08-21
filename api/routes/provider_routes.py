"""
Sprint 50 — expone qué wearables están habilitados, para que el
frontend (tab "Conexiones") pueda ocultar marcas que todavía no están
implementadas o cuyo flag está apagado. Ver
docs/plan-multi-brand-wearables.md.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import get_current_user
from ..models import User
from ..providers.registry import enabled_providers

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/enabled")
def get_enabled_providers(me: User = Depends(get_current_user)):
    """{'garmin': true, 'strava': true, 'wahoo': false, ...}"""
    return enabled_providers()
