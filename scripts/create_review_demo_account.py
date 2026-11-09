"""
Cuenta demo para revisores de Apple / Google (TIENDAS-BUILD).

APAGADO POR DEFECTO. Sin flags solo imprime lo que haría (dry-run) y no abre
la base de datos. Para crear la cuenta hay que pasar --apply Y tener
LABX_DEMO_ENABLE=1 en el entorno. NO se ejecuta como parte de ningún deploy
ni de la suite; se corre a mano, una vez, al momento del envío a revisión.

Uso (en la VM de producción, desde ~/labx, con el .env cargado):
    python scripts/create_review_demo_account.py                 # dry-run
    LABX_DEMO_ENABLE=1 LABX_DEMO_PASSWORD='...' \
        python scripts/create_review_demo_account.py --apply     # crea/actualiza
    LABX_DEMO_ENABLE=1 python scripts/create_review_demo_account.py --remove  # borra

Variables:
    LABX_DEMO_EMAIL     (default: revisor@labxperformanceapp.com)
    LABX_DEMO_PASSWORD  (obligatoria con --apply; cumple la política: 8+, may, min, número;
                         se pasa por entorno, nunca se escribe en el repo ni en logs)

La cuenta es un atleta plan 'agegroup' con perfil de ejemplo CLARAMENTE ficticio
(nombre "Revisor Demo"), sin Garmin/Strava/pagos vinculados. Idempotente.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DEFAULT_EMAIL = "revisor@labxperformanceapp.com"

# Datos de ejemplo, obviamente de demostración (ningún dato personal real).
DEMO_PROFILE = {
    "nombre": "Revisor Demo",
    "rol": "atleta",
    "plan_nivel": "agegroup",
    "activo": True,
    "pending_invite": False,
    "lang": "es",
    "sports": "bike,run",
    "ftp": 220,
    "weight_kg": 70.0,
    "height_cm": 175,
    "age": 30,
    "fcmax": 190,
    "run_pace": "5:00",
    "race_goal_name": "Carrera de ejemplo (demo)",
    "race_goal_dist": "21k",
}


def _password_ok(pw: str) -> bool:
    import re
    return bool(len(pw) >= 8 and re.search(r"[A-Z]", pw)
                and re.search(r"[a-z]", pw) and re.search(r"[0-9]", pw))


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    remove = "--remove" in argv
    email = os.environ.get("LABX_DEMO_EMAIL", DEFAULT_EMAIL).strip().lower()

    if not (apply or remove):
        print(f"[dry-run] Crearía/actualizaría el atleta demo {email} "
              f"(plan {DEMO_PROFILE['plan_nivel']}). No se tocó ninguna base de datos.")
        print("Para ejecutar: LABX_DEMO_ENABLE=1 LABX_DEMO_PASSWORD=... "
              "python scripts/create_review_demo_account.py --apply")
        return 0

    if os.environ.get("LABX_DEMO_ENABLE") != "1":
        print("ABORTADO: falta LABX_DEMO_ENABLE=1 (el script está apagado por defecto).",
              file=sys.stderr)
        return 2

    from api.database import SessionLocal
    from api.models import User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()

        if remove:
            if not user:
                print("No existe la cuenta demo; nada que borrar.")
                return 0
            user.activo = False
            db.commit()
            print(f"Cuenta demo {email} desactivada. Para borrado total use el flujo de "
                  "eliminación de cuenta (api/account_deletion.py).")
            return 0

        password = os.environ.get("LABX_DEMO_PASSWORD", "")
        if not _password_ok(password):
            print("ABORTADO: LABX_DEMO_PASSWORD ausente o no cumple la política "
                  "(8+ caracteres, mayúscula, minúscula y número).", file=sys.stderr)
            return 2

        from api.auth import hash_password
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        created = user is None
        if created:
            user = User(email=email, password_hash=hash_password(password))
            db.add(user)
        else:
            user.password_hash = hash_password(password)
            user.token_gen = (user.token_gen or 1) + 1  # invalida sesiones previas
        for k, v in DEMO_PROFILE.items():
            setattr(user, k, v)
        user.onboarding_completed_at = now
        user.gdpr_consent_at = now
        db.commit()
        print(f"Cuenta demo {'creada' if created else 'actualizada'}: {email} "
              f"(plan {DEMO_PROFILE['plan_nivel']}). Contraseña NO impresa.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
