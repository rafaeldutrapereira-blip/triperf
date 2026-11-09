"""
Flow — checkout web, suscripciones recurrentes y webhook (FLOW-INTEGRA, BUILD 366).

Detrás de FLOW_ENABLED (apagado por defecto): sin el flag todas las rutas dan 404.
Flujo (https://developers.flow.cl/api): customer/create -> customer/register (el
usuario registra su tarjeta en Flow) -> retorno del navegador (solo informativo) ->
subscription/create -> Flow cobra y avisa por urlCallback del plan (token) -> el
webhook consulta payment/getStatus + subscription/get con request firmado y SOLO
entonces activa el plan.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from .. import flow_billing as fb
from ..app_url import get_app_url
from ..auth import get_current_user
from ..database import get_db
from ..flow_client import (FLOW_PRODUCTS, PAY_CANCELLED, PAY_PAID, PAY_REJECTED,
                           SUB_ACTIVE_STATES, SUB_CANCELLED, FlowError,
                           flow_enabled, get_client, verify_signature)
from ..models import FlowPaymentEvent, FlowSubscription, User
from ..plan_features import normalize_plan

logger = logging.getLogger("labx.flow")


def _require_flag():
    if not flow_enabled():
        raise HTTPException(404, "Not Found")


router = APIRouter(prefix="/flow", tags=["flow"], dependencies=[Depends(_require_flag)])


def _public_products() -> list[dict]:
    return [{
        "id": pid, "name": p["name"], "amount": p["amount"], "currency": p["currency"],
        "interval": "month", "available": bool(p["sellable"]), "coming_soon": not p["sellable"],
    } for pid, p in FLOW_PRODUCTS.items()]


@router.get("/config")
def flow_config():
    return {"enabled": True, "products": _public_products()}


def _sub_view(row: FlowSubscription | None) -> dict | None:
    if row is None:
        return None
    return {
        "product": row.product, "status": row.status,
        "period_end": row.period_end.isoformat() if row.period_end else None,
        "cancel_at_period_end": bool(row.cancel_at_period_end),
    }


@router.get("/status")
def flow_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for r in db.query(FlowSubscription).filter(FlowSubscription.user_id == user.id,
                                               FlowSubscription.status == "activa").all():
        fb.reconcile_row(db, r)
    return {"subscription": _sub_view(fb.latest_subscription(db, user.id))}


def _ensure_flow_plan(client, product: dict, app_url: str) -> None:
    try:
        client.get_plan(product["flow_plan_id"])
        return
    except FlowError:
        pass   # no existe todavía
    client.create_plan(product["flow_plan_id"], f"LabX {product['name']}", product["amount"],
                       product["currency"], product["interval"], f"{app_url}/api/flow/webhook")


@router.post("/checkout")
def flow_checkout(body: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pid = str(body.get("product", "esencial")).lower()
    product = FLOW_PRODUCTS.get(pid)
    if product is None:
        raise HTTPException(400, "Producto desconocido.")
    if not product["sellable"]:
        raise HTTPException(400, f"El plan {product['name']} todavía no está disponible.")
    if user.rol in ("coach", "admin"):
        raise HTTPException(400, "Las cuentas de coach no se cobran en esta fase.")

    active = fb.latest_subscription(db, user.id, ("activa",))
    if active is not None and not (active.cancel_at_period_end and active.period_end
                                   and active.period_end <= fb.now()):
        raise HTTPException(409, "Ya tienes una suscripción activa.")
    if active is None and normalize_plan(user.plan_nivel) in ("agegroup", "elite"):
        raise HTTPException(409, "Tu cuenta ya tiene un plan de pago.")

    app_url = get_app_url()
    client = get_client()
    try:
        # Idempotencia: un solo intento pendiente por usuario/producto; se reutiliza.
        row = (db.query(FlowSubscription)
               .filter(FlowSubscription.user_id == user.id, FlowSubscription.product == pid,
                       FlowSubscription.status == "pendiente").first())
        any_row = db.query(FlowSubscription).filter(
            FlowSubscription.user_id == user.id, FlowSubscription.flow_customer_id.isnot(None)).first()
        customer_id = (row.flow_customer_id if row and row.flow_customer_id else
                       any_row.flow_customer_id if any_row else None)
        if not customer_id:
            customer_id = client.create_customer(user.nombre or user.email, user.email, user.id)["customerId"]
        _ensure_flow_plan(client, product, app_url)
        reg = client.register_card(customer_id, f"{app_url}/api/flow/register-return")
    except FlowError as e:
        logger.warning("Flow checkout falló user_id=%s: %s", user.id, e)
        raise HTTPException(502, "No pudimos iniciar el pago con Flow. Intenta nuevamente.")

    if row is None:
        row = FlowSubscription(user_id=user.id, product=pid, plan_nivel=product["plan_nivel"],
                               status="pendiente")
        db.add(row)
    row.flow_customer_id = customer_id
    row.register_token = reg["token"]
    row.updated_at = fb.now()
    db.commit()
    return {"checkout_url": f"{reg['url']}?token={reg['token']}"}


def _back(result: str) -> RedirectResponse:
    # 303: Flow nos hace POST; el navegador sigue con GET a la página de perfil.
    return RedirectResponse(f"{get_app_url()}/athlete_profile.html?flow={result}", status_code=303)


@router.post("/register-return")
async def flow_register_return(request: Request, db: Session = Depends(get_db)):
    """Retorno del navegador tras registrar la tarjeta. NUNCA activa el plan: solo
    crea la suscripción en Flow; la activación llega por webhook."""
    form = await request.form()
    token = str(form.get("token", "") or "")
    row = (db.query(FlowSubscription).filter(FlowSubscription.register_token == token).first()
           if token else None)
    if row is None:
        return _back("fail")
    if row.flow_subscription_id:          # reintento / doble envío: no se vuelve a crear
        return _back("pending")
    client = get_client()
    try:
        reg = client.register_status(token)
        if str(reg.get("status")) != "1":
            row.status = "fallida"
            row.updated_at = fb.now()
            db.commit()
            return _back("fail")
        sub = client.create_subscription(FLOW_PRODUCTS[row.product]["flow_plan_id"], row.flow_customer_id)
    except FlowError as e:
        logger.warning("Flow register-return falló sub=%s: %s", row.id, e)
        row.status = "fallida"
        row.updated_at = fb.now()
        db.commit()
        return _back("fail")
    row.flow_subscription_id = sub["subscriptionId"]
    row.updated_at = fb.now()
    db.commit()
    return _back("pending")


@router.post("/webhook")
async def flow_webhook(request: Request, db: Session = Depends(get_db)):
    """urlCallback del plan. Flow envía `token`; el resultado autoritativo se consulta a
    Flow con request firmado (payment/getStatus) — el POST por sí solo no activa nada."""
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    token = params.get("token", "")
    if not token:
        raise HTTPException(400, "Falta token.")
    # Si el request trae firma `s`, debe ser válida (HMAC-SHA256 con el secret).
    if "s" in params and not verify_signature(params, os.getenv("FLOW_SECRET_KEY", "")):
        logger.warning("Flow webhook con firma inválida")
        raise HTTPException(400, "Firma inválida.")

    client = get_client()
    try:
        pay = client.payment_status(token)
        flow_order = str(pay["flowOrder"])
        pay_status = int(pay["status"])
    except (FlowError, KeyError, ValueError, TypeError):
        raise HTTPException(400, "Token no verificable.")

    ev = db.query(FlowPaymentEvent).filter(FlowPaymentEvent.flow_order == flow_order).first()
    if ev is not None and (ev.pay_status == pay_status or ev.pay_status == PAY_PAID):
        return JSONResponse({"received": True, "duplicate": True})

    payer = str(pay.get("payer", "") or "").strip().lower()
    user = db.query(User).filter(User.email.ilike(payer)).first() if payer else None
    row = None
    if user is not None:
        row = (db.query(FlowSubscription)
               .filter(FlowSubscription.user_id == user.id,
                       FlowSubscription.flow_subscription_id.isnot(None),
                       FlowSubscription.status.in_(("pendiente", "activa", "fallida")))
               .order_by(FlowSubscription.created_at.desc()).first())

    if ev is None:
        ev = FlowPaymentEvent(flow_order=flow_order, pay_status=pay_status,
                              user_id=user.id if user else None)
        db.add(ev)
    else:
        ev.pay_status = pay_status

    if row is not None:
        if pay_status == PAY_PAID:
            try:
                fsub = client.get_subscription(row.flow_subscription_id)
            except FlowError:
                db.rollback()
                raise HTTPException(502, "No se pudo verificar la suscripción; Flow reintentará.")
            fstatus = int(fsub.get("status", -1))
            if fstatus in SUB_ACTIVE_STATES:
                fb.activate(db, row, fsub)
            elif fstatus == SUB_CANCELLED:
                row.status = "cancelada"
        elif pay_status in (PAY_REJECTED, PAY_CANCELLED) and row.status == "pendiente":
            row.status = "fallida"      # pago rechazado/anulado: nunca activa
        row.updated_at = fb.now()
    db.commit()
    return JSONResponse({"received": True})


@router.post("/cancel")
def flow_cancel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Cancela al fin del período pagado: el acceso sigue hasta period_end."""
    row = fb.latest_subscription(db, user.id, ("activa",))
    if row is None or not row.flow_subscription_id:
        raise HTTPException(404, "No tienes una suscripción activa.")
    if row.cancel_at_period_end:
        return {"subscription": _sub_view(row)}      # idempotente
    try:
        get_client().cancel_subscription(row.flow_subscription_id, at_period_end=True)
    except FlowError as e:
        logger.warning("Flow cancel falló user_id=%s: %s", user.id, e)
        raise HTTPException(502, "No pudimos cancelar con Flow. Intenta nuevamente.")
    row.cancel_at_period_end = True
    row.updated_at = fb.now()
    db.commit()
    return {"subscription": _sub_view(row)}
