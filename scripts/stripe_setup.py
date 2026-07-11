"""
stripe_setup.py — Crea los 3 productos LabX en Stripe y muestra los price IDs.

Uso:
    pip install stripe
    python scripts/stripe_setup.py sk_live_...   (o sk_test_... para probar)

Copiar los price_... resultantes al .env.production
"""
import sys
import stripe

if len(sys.argv) < 2:
    print("Uso: python scripts/stripe_setup.py <STRIPE_SECRET_KEY>")
    sys.exit(1)

stripe.api_key = sys.argv[1]

PRODUCTS = [
    {"name": "LabX Pro",   "price_usd": 1900, "key": "STRIPE_PRICE_PRO"},
    {"name": "LabX Elite", "price_usd": 3900, "key": "STRIPE_PRICE_ELITE"},
    {"name": "LabX Coach", "price_usd": 4900, "key": "STRIPE_PRICE_COACH"},
]

print("\n=== Creando productos en Stripe ===\n")
for p in PRODUCTS:
    # Crear producto
    product = stripe.Product.create(
        name=p["name"],
        description=f"LabX — Plan {p['name'].split()[-1]} mensual",
        metadata={"labx_plan": p["name"].split()[-1].lower()},
    )
    # Crear precio mensual recurrente
    price = stripe.Price.create(
        product=p["product_id"] if "product_id" in p else product.id,
        unit_amount=p["price_usd"],
        currency="usd",
        recurring={"interval": "month"},
        nickname=p["name"],
    )
    print(f"✓ {p['name']}")
    print(f"  Product ID: {product.id}")
    print(f"  Price ID:   {price.id}  ← {p['key']}={price.id}")
    print()

print("=== Agregar al .env.production ===")
print("(Los price IDs de arriba)")
