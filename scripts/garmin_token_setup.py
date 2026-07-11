"""
Garmin Token Setup — LabX
=========================
Corre este script UNA VEZ para autenticarte con Garmin Connect
de forma interactiva. Guarda el token para que LabX no necesite
pedirte credenciales ni código MFA en el futuro.

Uso:
    python scripts/garmin_token_setup.py
"""
import sys
import os
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent.parent
TOKEN_DIR  = BASE_DIR / "data" / "garmin_tokens"
TOKEN_DIR.mkdir(parents=True, exist_ok=True)

# ── obtener user_id de la DB para guardar en el directorio correcto ────────────
def get_user_id(email: str) -> str | None:
    try:
        sys.path.insert(0, str(BASE_DIR))
        from api.database import SessionLocal
        from api.models import User
        db = SessionLocal()
        user = db.query(User).filter(User.email == email.lower()).first()
        db.close()
        return str(user.id) if user else None
    except Exception as e:
        print(f"  (aviso: no se pudo leer la DB — {e})")
        return None

def main():
    print("=" * 55)
    print("  LabX — Configuración de Garmin Connect")
    print("=" * 55)
    print()

    email    = input("  Email de Garmin Connect: ").strip()
    password = input("  Contraseña de Garmin:    ").strip()

    if not email or not password:
        print("\n  ERROR: email y contraseña son obligatorios.")
        sys.exit(1)

    # Directorio de token: por user_id si existe en DB, sino por email sanitizado
    user_id = get_user_id(email)
    if user_id:
        token_path = str(TOKEN_DIR / user_id)
        print(f"\n  User ID encontrado: {user_id}")
    else:
        safe_name  = email.replace("@", "_at_").replace(".", "_")
        token_path = str(TOKEN_DIR / safe_name)
        print(f"\n  Token se guardará en: {token_path}")

    print("\n  Conectando con Garmin Connect...")
    print("  (Si Garmin pide verificación, te pedirá el código aquí)\n")

    try:
        from garminconnect import Garmin

        def prompt_mfa():
            print()
            print("  ┌─────────────────────────────────────────────┐")
            print("  │  Garmin pide verificación adicional          │")
            print("  │  Revisa tu email o app autenticadora         │")
            print("  └─────────────────────────────────────────────┘")
            code = input("  Código de verificación: ").strip()
            return code

        client = Garmin(email, password, prompt_mfa=prompt_mfa)
        client.login(tokenstore=token_path)

        print()
        print("  ✓ Login exitoso — token guardado en:")
        print(f"    {token_path}")
        print()

        # Verificar que funciona
        user_data = client.get_full_name()
        print(f"  ✓ Cuenta verificada: {user_data}")
        print()
        print("  LabX usará este token automáticamente.")
        print("  Ya puedes conectar Garmin desde Athlete Profile.")

    except ImportError:
        print("\n  ERROR: garminconnect no instalado.")
        print("  Corre: pip install garminconnect")
        sys.exit(1)
    except Exception as e:
        print(f"\n  ERROR al conectar: {e}")
        print()
        print("  Posibles causas:")
        print("  - Contraseña incorrecta")
        print("  - IP en rate-limit de Garmin (espera 30-60 min)")
        print("  - Garmin está usando SSO con Google/Apple (no contraseña directa)")
        sys.exit(1)

if __name__ == "__main__":
    main()
