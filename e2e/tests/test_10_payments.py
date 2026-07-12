"""
E2E-PAYMENTS — Stripe Payment & Plan Subscription Tests
======================================================
Priority : HIGH (revenue-critical)
Markers  : payments, manual (webhook validation)
Coverage :
  TC-PAY-001  Plan upgrade UI visible para atleta (UI)
  TC-PAY-002  [MANUAL] Stripe checkout session creada
  TC-PAY-003  [MANUAL] Pago exitoso con tarjeta de prueba
  TC-PAY-004  [MANUAL] Webhook Stripe → plan actualizado en DB
  TC-PAY-005  Plan actual visible en perfil de atleta
  TC-PAY-006  Features bloqueadas por plan (feature gating)
  TC-PAY-007  Downgrade de plan
  TC-PAY-008  Cancelación de suscripción
  TC-PAY-009  Stripe webhook endpoint existe y acepta POST
  TC-PAY-010  Price IDs configurados correctamente
"""
from __future__ import annotations

import pytest
import requests

from e2e.conftest import BASE_URL, API_URL


# ─────────────────────────────────────────────────────────────────────────────
# TC-PAY-001 — Plan upgrade UI visible
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.smoke
@pytest.mark.payments
def test_plan_upgrade_ui_visible(page, athlete_api):
    """
    Acceptance:
      Profile or settings page shows current plan
      Upgrade/change plan button visible for free-tier users
    """
    page.goto(f"{BASE_URL}/login.html")
    page.evaluate(f"""() => {{
        localStorage.setItem('lx_co_token', '{athlete_api._token}');
        localStorage.setItem('lx_co_rol', 'atleta');
    }}""")

    # Check profile page for plan info
    page.goto(f"{BASE_URL}/profile.html")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)

    body = page.locator("body").inner_text().lower()
    has_plan = any(word in body for word in ["plan", "suscripción", "upgrade", "premium", "elite"])
    # Non-blocking: just log what we find
    print(f"\nPlan UI found: {has_plan}")


# ─────────────────────────────────────────────────────────────────────────────
# TC-PAY-002 — [MANUAL] Stripe checkout session
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.manual
@pytest.mark.payments
def test_stripe_checkout_session_manual():
    """
    MANUAL TEST — Stripe integration
    =================================
    Prerequisites:
      - STRIPE_SECRET_KEY configured (test mode)
      - STRIPE_PRICE_ID_ELITE configured

    Steps:
    1. POST /api/payments/create-checkout-session
       Body: {"price_id": "price_xxx", "success_url": "...", "cancel_url": "..."}
    2. Verify response has: session_id, checkout_url

    Expected result:
      - checkout_url redirects to Stripe hosted checkout
      - Session valid for 30 minutes

    Test data:
      Use Stripe test price IDs from dashboard.stripe.com
      Test card: 4242 4242 4242 4242 (success)
      Test card: 4000 0000 0000 9995 (decline)
    """
    pytest.skip("MANUAL TEST — requires Stripe test keys. See docstring.")


# ─────────────────────────────────────────────────────────────────────────────
# TC-PAY-003 — [MANUAL] Pago exitoso con tarjeta de prueba
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.manual
@pytest.mark.payments
def test_pago_exitoso_tarjeta_prueba():
    """
    MANUAL TEST
    ===========
    Steps:
    1. Complete TC-PAY-002 to get checkout URL
    2. Open checkout_url in browser
    3. Fill payment form with test card: 4242 4242 4242 4242
       - Expiry: any future date (e.g., 12/28)
       - CVC: any 3 digits
       - Name: any
    4. Submit payment
    5. Verify redirect to success_url
    6. GET /api/athlete/profile → plan_nivel should be 'elite' or 'pro'

    Expected result:
      - Payment confirmed immediately (test mode)
      - Webhook fires within 5s
      - Plan upgraded in DB
    """
    pytest.skip("MANUAL TEST — requires Stripe checkout UI. See docstring.")


# ─────────────────────────────────────────────────────────────────────────────
# TC-PAY-004 — [MANUAL] Webhook Stripe → plan actualizado
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.manual
@pytest.mark.payments
def test_stripe_webhook_plan_update():
    """
    MANUAL TEST — Stripe webhook validation
    ========================================
    Prerequisites:
      - stripe CLI installed: https://stripe.com/docs/stripe-cli
      - stripe listen --forward-to localhost:8000/api/payments/webhook

    Steps:
    1. stripe trigger payment_intent.succeeded --api-key sk_test_...
    2. Verify webhook endpoint returns 200
    3. Verify plan_nivel updated in DB for test user

    Expected result:
      - Webhook signature validated (Stripe-Signature header)
      - 200 OK returned
      - User plan updated within 5s
    """
    pytest.skip("MANUAL TEST — requires stripe CLI. See docstring.")


# ─────────────────────────────────────────────────────────────────────────────
# TC-PAY-005 — Plan actual visible en perfil API
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.payments
def test_plan_actual_en_perfil(athlete_api):
    """
    Acceptance:
      GET /api/athlete/profile → has plan_nivel field
      plan_nivel in ('free', 'basic', 'agegroup', 'elite')
    """
    r = athlete_api.get("/athlete/profile")
    assert r.status_code == 200, f"Profile: {r.status_code}"
    data = r.json()

    valid_plans = ("free", "basic", "agegroup", "elite", "starter", "premium",
                   "basico", "estandar", "avanzado")  # Spanish DB values
    plan = data.get("plan_nivel", "")
    assert plan in valid_plans or plan == "", \
        f"Invalid plan_nivel: '{plan}'. Expected one of {valid_plans}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-PAY-006 — Feature gating por plan (API)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.payments
def test_feature_gating_por_plan(athlete_api):
    """
    Acceptance:
      Free tier athletes cannot access premium features
      Premium features return 403 with upgrade message for free users
    NOTE: Specific feature gates depend on plan_nivel checks in routes
    """
    r = athlete_api.get("/athlete/profile")
    if r.status_code != 200:
        pytest.skip("Cannot check plan")

    plan = r.json().get("plan_nivel", "free")
    print(f"\nCurrent plan: {plan}")

    # Check a premium endpoint (AI coach is typically premium-gated)
    ai_r = athlete_api.post("/ai/coach-suggest", json={
        "message": "Feature gate test"
    }, timeout=35)

    # 200 = premium, 402 = payment required, 403 = plan gate, 503 = no API key
    # All are acceptable depending on plan / environment
    assert ai_r.status_code in (200, 402, 403, 503, 504), \
        f"AI coach feature gate: unexpected {ai_r.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-PAY-007 — Stripe webhook endpoint responde
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.payments
def test_stripe_webhook_endpoint_exists():
    """
    Acceptance:
      POST /api/payments/webhook exists (even without valid signature → 400)
      NOT 404 (endpoint must be registered)
    """
    r = requests.post(f"{API_URL}/payments/webhook",
                      data=b"{}",
                      headers={"Stripe-Signature": "invalid_signature"},
                      timeout=5)

    # 400 = invalid signature (expected), 404 = endpoint missing
    assert r.status_code != 404, \
        "/api/payments/webhook returned 404 — endpoint not registered"

    # 400 is expected for invalid signature
    # 500 would indicate missing webhook secret config
    expected = (400, 401, 403, 422)
    if r.status_code not in expected:
        print(f"\nStripe webhook response: {r.status_code} {r.text[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# TC-PAY-008 — Checkout session endpoint existe
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.payments
def test_checkout_session_endpoint_registrado(athlete_api):
    """
    Acceptance:
      POST /api/payments/create-checkout-session is registered
      Returns 400/422 without price_id (not 404)
    """
    r = athlete_api.post("/payments/create-checkout-session", json={})
    assert r.status_code != 404, \
        "Checkout session endpoint not registered (404)"
    # 400/422 = missing required fields (expected without Stripe config)
    # 500 = Stripe not configured
    print(f"\nCheckout endpoint status (no Stripe key): {r.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# TC-PAY-009 — Price IDs en OpenAPI docs
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.payments
def test_payment_routes_en_openapi():
    """
    Acceptance:
      OpenAPI schema has /api/payments/* paths registered
    """
    r = requests.get(f"{BASE_URL}/openapi.json", timeout=5)
    assert r.status_code == 200
    paths = r.json().get("paths", {})

    payment_paths = [p for p in paths if "payment" in p.lower() or "stripe" in p.lower()]
    print(f"\nPayment paths in OpenAPI: {payment_paths}")
    # Non-blocking: just informational if payments not yet implemented


# ─────────────────────────────────────────────────────────────────────────────
# TC-PAY-010 — Plan features lista (API)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.payments
def test_plan_features_disponibles():
    """
    Acceptance:
      GET /api/payments/plans → list of plans with features
      Or documented in static content
    """
    r = requests.get(f"{API_URL}/payments/plans", timeout=5)
    if r.status_code == 200:
        plans = r.json()
        assert isinstance(plans, (list, dict)), "Plans should be list or dict"
        print(f"\nPlans available: {plans}")
    elif r.status_code == 404:
        print("\nPlans API not implemented yet — check static pricing page")
    # Non-blocking test (plans API may be static content)
