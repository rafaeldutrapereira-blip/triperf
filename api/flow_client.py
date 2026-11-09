"""
Flow (flow.cl) — cliente de la API REST, catálogo de productos y firma.

Fuentes: https://developers.flow.cl/api (OpenAPI), https://developers.flow.cl/docs/intro
(firmado), https://www.flow.cl/docs/apiFlow.yaml?v=6.

Todo detrás del flag FLOW_ENABLED (apagado por defecto). Credenciales SOLO desde
el entorno (.env): FLOW_API_KEY, FLOW_SECRET_KEY, FLOW_API_URL (por defecto sandbox).
Nada de esto se imprime en logs.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os

import httpx

logger = logging.getLogger("labx.flow")

SANDBOX_URL = "https://sandbox.flow.cl/api"

# ── Catálogo de productos ────────────────────────────────────────
# Mapeo explícito producto Flow → plan_nivel de LabX (sin tocar planes base).
#   Esencial → "agegroup": es el nivel pago de entrada que en plan_features.py
#     desbloquea todas las funciones pagas del atleta (plan, nutrición, analytics,
#     recuperación, mental, race day, comunidad, calendario...). Elite solo añade
#     labs/detalle/adaptativo/indoor.
#   Completo → "elite" (app + dispositivo, FASE 2): definido pero NO vendible.
# interval=3 es MENSUAL según apiFlow.yaml (1 diario, 2 semanal, 3 mensual, 4 anual).
FLOW_PRODUCTS: dict[str, dict] = {
    "esencial": {
        "name": "Esencial",
        "plan_nivel": "agegroup",
        "amount": 9900,
        "currency": "CLP",
        "interval": 3,
        "flow_plan_id": "labx_esencial_mensual",
        "sellable": True,
    },
    "completo": {
        "name": "Completo",
        "plan_nivel": "elite",
        "amount": 15900,
        "currency": "CLP",
        "interval": 3,
        "flow_plan_id": "labx_completo_mensual",
        "sellable": False,   # fase 2: sin checkout
    },
}

# Estados de pago (payment/getStatus): 1 pendiente, 2 pagada, 3 rechazada, 4 anulada.
PAY_PENDING, PAY_PAID, PAY_REJECTED, PAY_CANCELLED = 1, 2, 3, 4
# Estados de suscripción Flow: 0 inactiva, 1 activa, 2 trial, 4 cancelada.
SUB_ACTIVE_STATES = (1, 2)
SUB_CANCELLED = 4


class FlowError(Exception):
    """Error de la API de Flow o de configuración."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


def flow_enabled() -> bool:
    return os.getenv("FLOW_ENABLED", "0").strip() == "1"


def sign_params(params: dict, secret: str) -> str:
    """HMAC-SHA256 hex de 'nombre+valor' concatenados con los nombres en orden
    alfabético. El parámetro 's' nunca entra en la firma."""
    to_sign = "".join(f"{k}{params[k]}" for k in sorted(params) if k != "s")
    return hmac.new(secret.encode("utf-8"), to_sign.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(params: dict, secret: str) -> bool:
    given = str(params.get("s", "") or "")
    if not given or not secret:
        return False
    return hmac.compare_digest(sign_params(params, secret), given)


class FlowClient:
    def __init__(self, api_key: str | None = None, secret_key: str | None = None,
                 base_url: str | None = None, timeout: float = 15.0):
        self.api_key = api_key if api_key is not None else os.getenv("FLOW_API_KEY", "").strip()
        self.secret_key = secret_key if secret_key is not None else os.getenv("FLOW_SECRET_KEY", "").strip()
        self.base_url = (base_url or os.getenv("FLOW_API_URL", "").strip() or SANDBOX_URL).rstrip("/")
        self.timeout = timeout
        if not self.api_key or not self.secret_key:
            raise FlowError("Flow no está configurado (FLOW_API_KEY / FLOW_SECRET_KEY).")

    def _signed(self, params: dict) -> dict:
        p = {k: v for k, v in params.items() if v is not None}
        p["apiKey"] = self.api_key
        p["s"] = sign_params(p, self.secret_key)
        return p

    def _call(self, method: str, path: str, params: dict) -> dict:
        p = self._signed(params)
        try:
            if method == "GET":
                r = httpx.get(self.base_url + path, params=p, timeout=self.timeout)
            else:
                r = httpx.post(self.base_url + path, data=p, timeout=self.timeout)
        except httpx.HTTPError as e:
            logger.warning("Flow %s %s falló de red: %s", method, path, type(e).__name__)
            raise FlowError("No se pudo contactar a Flow.") from e
        try:
            body = r.json()
        except ValueError:
            body = {}
        if r.status_code != 200:
            msg = body.get("message") if isinstance(body, dict) else None
            logger.warning("Flow %s %s -> %s", method, path, r.status_code)
            raise FlowError(msg or f"Flow respondió {r.status_code}", r.status_code)
        return body

    # ── Clientes y tarjeta ──
    def create_customer(self, name: str, email: str, external_id: str) -> dict:
        return self._call("POST", "/customer/create",
                          {"name": name, "email": email, "externalId": external_id})

    def register_card(self, customer_id: str, url_return: str) -> dict:
        """→ {'url','token'}; redirigir a url + '?token=' + token."""
        return self._call("POST", "/customer/register",
                          {"customerId": customer_id, "url_return": url_return})

    def register_status(self, token: str) -> dict:
        return self._call("GET", "/customer/getRegisterStatus", {"token": token})

    # ── Planes y suscripciones ──
    def get_plan(self, plan_id: str) -> dict:
        return self._call("GET", "/plans/get", {"planId": plan_id})

    def create_plan(self, plan_id: str, name: str, amount: int, currency: str,
                    interval: int, url_callback: str) -> dict:
        return self._call("POST", "/plans/create", {
            "planId": plan_id, "name": name, "amount": amount, "currency": currency,
            "interval": interval, "urlCallback": url_callback,
        })

    def create_subscription(self, plan_id: str, customer_id: str) -> dict:
        return self._call("POST", "/subscription/create",
                          {"planId": plan_id, "customerId": customer_id})

    def get_subscription(self, subscription_id: str) -> dict:
        return self._call("GET", "/subscription/get", {"subscriptionId": subscription_id})

    def cancel_subscription(self, subscription_id: str, at_period_end: bool = True) -> dict:
        return self._call("POST", "/subscription/cancel", {
            "subscriptionId": subscription_id, "at_period_end": 1 if at_period_end else 0})

    # ── Pagos ──
    def payment_status(self, token: str) -> dict:
        return self._call("GET", "/payment/getStatus", {"token": token})


def get_client() -> FlowClient:
    """Punto único de construcción: los tests lo reemplazan por un mock."""
    return FlowClient()
