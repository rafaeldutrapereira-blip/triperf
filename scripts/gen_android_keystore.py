"""
Genera el keystore de release de Android (PKCS12, RSA 4096, validez 30 años)
FUERA del repo, con sus credenciales en un archivo local de la misma carpeta.

No imprime jamás contraseñas. Aborta si el destino está dentro del repo o si
ya existe un keystore (nunca sobrescribe: perder/reemplazar la llave de subida
rompe las actualizaciones en Play).

Uso: python scripts/gen_android_keystore.py C:\\Users\\rafae\\labx-overnight\\keystore

Salida en esa carpeta:
    labx-release.p12        el keystore (copia de seguridad obligatoria fuera de esta PC)
    keystore.local.env      LABX_KEYSTORE_PATH / _PASSWORD / LABX_KEY_ALIAS / _PASSWORD
                            (formato KEY=valor, para cargar al entorno o a GitHub secrets)

Con PKCS12 la contraseña del almacén y la de la llave son la misma.
"""
from __future__ import annotations

import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parent.parent
ALIAS = "labx-release"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    out = Path(argv[0]).resolve()
    if ROOT in (out, *out.parents):
        print("ABORTADO: el destino está dentro del repo.", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    ks, envf = out / "labx-release.p12", out / "keystore.local.env"
    if ks.exists() or envf.exists():
        print("ABORTADO: ya existe un keystore/credenciales; no se sobrescribe.", file=sys.stderr)
        return 3

    password = secrets.token_urlsafe(24)
    key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "LabX"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Cumbre Servicios SpA"),
        x509.NameAttribute(NameOID.COUNTRY_NAME, "CL"),
    ])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=365 * 30))
            .sign(key, hashes.SHA256()))
    data = pkcs12.serialize_key_and_certificates(
        ALIAS.encode(), key, cert, None,
        serialization.BestAvailableEncryption(password.encode()))
    ks.write_bytes(data)
    envf.write_text(
        f"LABX_KEYSTORE_PATH={ks}\nLABX_KEYSTORE_PASSWORD={password}\n"
        f"LABX_KEY_ALIAS={ALIAS}\nLABX_KEY_PASSWORD={password}\n", encoding="utf-8")
    print(f"Keystore creado en {out} (credenciales en keystore.local.env, no impresas).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
