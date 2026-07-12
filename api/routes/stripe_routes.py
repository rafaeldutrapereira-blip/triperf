"""
Stripe — gestión de suscripciones LabX.
Planes: basico (gratis) | agegroup ($19/mes) | elite ($39/mes) | coach ($49/mes)

Variables de entorno requeridas:
  STRIPE_SECRET_KEY        sk_live_... o sk_test_...
  STRIPE_WEBHOOK_SECRET    whsec_...
  STRIPE_PRICE_AGEGROUP    price_...
  STRIPE_PRICE_ELITE       price_...
  STRIPE_PRICE_COACH       price_...
  APP_URL                  https://labx.app (para redirect)
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import User
# Única fuente de verdad de feature-gating por plan (usada también por
# blood_lab_routes, adaptive_routes, nutrition_routes, etc.) — se
# re-exporta acá para no romper imports existentes de este módulo.
from ..plan_features import _PLAN_FEATURES, has_feature, require_feature

logger = logging.getLogger("labx.stripe")
router = APIRouter(prefix="/stripe", tags=["stripe"])

# Mapa price_id → plan_nivel
_PRICE_TO_PLAN: dict[str, str] = {
    os.getenv("STRIPE_PRICE_AGEGROUP", "price_agegroup"): "agegroup",
    os.getenv("STRIPE_PRICE_ELITE",    "price_elite"):    "elite",
    os.getenv("STRIPE_PRICE_COACH",    "price_coach"):    "coach",
}


def _stripe():
    """Inicializa stripe con la API key — lazy para no fallar si no está instalado."""
    import stripe as _s
    _s.api_key = os.getenv("STRIPE_SECRET_KEY", "")
    if not _s.api_key:
        raise HTTPException(503, "Pagos no disponibles — configura STRIPE_SECRET_KEY.")
    return _s


# ── Endpoints ──────────────────────────────────────────────────

@router.get("/plans")
def list_plans():
    """Devuelve los planes disponibles y sus features."""
    return {
        "plans": [
            {"id": "basico",   "name": "Básico",   "price_usd": 0,  "features": sorted(_PLAN_FEATURES["basico"])},
            {"id": "agegroup", "name": "Agegroup", "price_usd": 19, "features": sorted(_PLAN_FEATURES["agegroup"])},
            {"id": "elite",    "name": "Élite",    "price_usd": 39, "features": sorted(_PLAN_FEATURES["elite"])},
            {"id": "coach",    "name": "Coach",    "price_usd": 49, "features": sorted(_PLAN_FEATURES["coach"])},
        ]
    }


@router.get("/my-features")
def my_features(user: User = Depends(get_current_user)):
    """Devuelve las features disponibles para el usuario autenticado."""
    plan = (user.plan_nivel or "basico").lower()
    if user.rol in ("coach", "admin"):
        all_feats = set().union(*_PLAN_FEATURES.values())
        return {"plan": plan, "rol": user.rol, "features": sorted(all_feats)}
    return {"plan": plan, "rol": user.rol, "features": sorted(_PLAN_FEATURES.get(plan, _PLAN_FEATURES["basico"]))}


def _get_or_create_stripe_customer(stripe, user: User, db) -> str:
    """
    S15: Retorna el stripe_customer_id del usuario (lo crea si no existe).
    Persiste el ID en el modelo para evitar duplicados.
    """
    if user.stripe_customer_id:
        return user.stripe_customer_id

    # Buscar por email primero
    customers = stripe.Customer.list(email=user.email, limit=1)
    if customers.data:
        cust_id = customers.data[0].id
    else:
        customer = stripe.Customer.create(
            email    = user.email,
            name     = user.nombre,
            metadata = {"user_id": user.id},
        )
        cust_id = customer.id
        logger.info("Stripe customer creado user_id=%s customer_id=%s", user.id, cust_id)

    user.stripe_customer_id = cust_id
    db.commit()
    return cust_id


@router.post("/checkout")
def create_checkout(
    body: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """S15: Crea una sesión de Stripe Checkout para upgrading de plan con idempotency."""
    import uuid as _uuid
    stripe = _stripe()  # raises 503 first if STRIPE_SECRET_KEY not set
    plan = body.get("plan", "agegroup").lower()
    price_map = {
        "agegroup": os.getenv("STRIPE_PRICE_AGEGROUP", ""),
        "elite":    os.getenv("STRIPE_PRICE_ELITE", ""),
        "coach":    os.getenv("STRIPE_PRICE_COACH", ""),
    }
    price_id = price_map.get(plan, "")
    if not price_id:
        raise HTTPException(400, f"Plan '{plan}' no disponible o no configurado.")

    app_url = os.getenv("APP_URL", "http://localhost:8000")

    customer_id = _get_or_create_stripe_customer(stripe, user, db)

    session = stripe.checkout.Session.create(
        mode                = "subscription",
        customer            = customer_id,
        line_items          = [{"price": price_id, "quantity": 1}],
        success_url         = f"{app_url}/dashboard.html?upgraded=1&plan={plan}",
        cancel_url          = f"{app_url}/dashboard.html?upgraded=0",
        metadata            = {"user_id": user.id, "plan": plan},
        subscription_data   = {"metadata": {"user_id": user.id, "plan": plan},
                               "trial_period_days": int(os.getenv("STRIPE_TRIAL_DAYS", "0"))},
        allow_promotion_codes = True,
        idempotency_key     = f"checkout-{user.id}-{plan}-{_uuid.uuid4().hex[:8]}",
    )
    logger.info("Checkout creado user_id=%s plan=%s session=%s", user.id, plan, session.id)
    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/portal")
def billing_portal(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """S15: Crea una sesión del Stripe Billing Portal. Usa stripe_customer_id del modelo."""
    stripe  = _stripe()
    app_url = os.getenv("APP_URL", "http://localhost:8000")

    customer_id = _get_or_create_stripe_customer(stripe, user, db)

    portal_session = stripe.billing_portal.Session.create(
        customer   = customer_id,
        return_url = f"{app_url}/dashboard.html",
    )
    return {"portal_url": portal_session.url}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    db: Session = Depends(get_db),
):
    """Webhook de Stripe — actualiza plan_nivel al activar/cancelar suscripción."""
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not webhook_secret:
        raise HTTPException(503, "Webhook no configurado.")

    payload = await request.body()
    stripe  = _stripe()

    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, webhook_secret)
    except Exception as e:
        logger.warning("Stripe webhook inválido: %s", e)
        raise HTTPException(400, f"Webhook inválido: {e}")

    evt_type = event["type"]
    logger.info("Stripe webhook: %s", evt_type)

    if evt_type in ("customer.subscription.created", "customer.subscription.updated"):
        sub = event["data"]["object"]
        user_id = sub.get("metadata", {}).get("user_id")
        plan    = sub.get("metadata", {}).get("plan", "basico")
        status  = sub.get("status", "")
        if user_id and status in ("active", "trialing"):
            u = db.query(User).filter(User.id == user_id).first()
            if u:
                u.plan_nivel              = plan
                u.stripe_subscription_id  = sub.get("id")
                if status == "trialing":
                    trial_ts = sub.get("trial_end")
                    if trial_ts:
                        from datetime import datetime, timezone
                        u.trial_end_at = datetime.fromtimestamp(trial_ts, tz=timezone.utc).replace(tzinfo=None)
                db.commit()
                logger.info("Plan actualizado user_id=%s → %s (sub=%s)", user_id, plan, sub.get("id"))

    elif evt_type == "customer.subscription.deleted":
        sub     = event["data"]["object"]
        user_id = sub.get("metadata", {}).get("user_id")
        if user_id:
            u = db.query(User).filter(User.id == user_id).first()
            if u:
                u.plan_nivel             = "basico"
                u.stripe_subscription_id = None
                u.trial_end_at           = None
                db.commit()
                logger.info("Suscripción cancelada user_id=%s → basico", user_id)

    return JSONResponse({"received": True})
