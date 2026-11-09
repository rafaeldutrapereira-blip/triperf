#!/usr/bin/env python3
"""
LabX — Backup automático CIFRADO
================================
Uso:
    python backup.py                    # Backup cifrado a backups/ (retención BACKUP_KEEP_DAYS, 30 por defecto)
    python backup.py --restore <file>   # Restaurar desde un backup (.enc, .db, .sql, .sql.gz)
    python backup.py --list             # Listar backups disponibles

SEGURIDAD-VERIFICADA (BUILD 368):
  * SQLite se copia con la API de backup de sqlite3 (consistente aunque la app esté
    escribiendo / en modo WAL). Antes era shutil.copy2 del archivo vivo.
  * El respaldo se cifra con Fernet (AES-128-CBC + HMAC-SHA256) por bloques de 4 MiB.
    Clave: BACKUP_ENCRYPTION_KEY o, en su defecto, FERNET_KEY. Para descifrar también se
    prueba FERNET_KEY_OLD (rotación). Sin clave el backup FALLA (no se escribe en claro),
    salvo BACKUP_ALLOW_PLAINTEXT=1 fuera de producción.
  * Retención: BACKUP_KEEP_DAYS (30 por defecto) sobre el timestamp del nombre.
  * La app lo ejecuta sola cada día (api/scheduler.py, 03:30). Cron manual equivalente:
        30 3 * * * cd /ruta/labx && venv/bin/python backup.py >> logs/backup.log 2>&1
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sqlite3
import struct
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Cargar .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

BACKUP_DIR  = Path(__file__).parent / "backups"
DB_URL      = os.getenv("DATABASE_URL", "sqlite:///./data/labx_coach.db")
KEEP_DAYS   = int(os.getenv("BACKUP_KEEP_DAYS", "30"))

MAGIC       = b"LXBK1\n"
CHUNK       = 4 * 1024 * 1024
_TS_RE      = re.compile(r"^labx_(\d{8}_\d{6})\.")


class BackupError(RuntimeError):
    pass


# ── Cifrado ──────────────────────────────────────────────────
def _fernets(for_decrypt: bool):
    from cryptography.fernet import Fernet, MultiFernet
    names = ["BACKUP_ENCRYPTION_KEY", "FERNET_KEY"] + (["FERNET_KEY_OLD"] if for_decrypt else [])
    keys = []
    for n in names:
        v = os.getenv(n, "").strip()
        if v:
            try:
                keys.append(Fernet(v.encode()))
            except Exception:
                raise BackupError(f"{n} no es una clave Fernet válida")
    return MultiFernet(keys) if keys else None


def encrypt_file(src: Path, dst: Path) -> None:
    f = _fernets(False)
    if f is None:
        raise BackupError("Sin clave de cifrado: configura BACKUP_ENCRYPTION_KEY o FERNET_KEY")
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        fo.write(MAGIC)
        while True:
            block = fi.read(CHUNK)
            if not block:
                break
            tok = f.encrypt(block)
            fo.write(struct.pack(">I", len(tok)))
            fo.write(tok)


def decrypt_file(src: Path, dst: Path) -> None:
    f = _fernets(True)
    if f is None:
        raise BackupError("Sin clave para descifrar: configura BACKUP_ENCRYPTION_KEY o FERNET_KEY")
    from cryptography.fernet import InvalidToken
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        if fi.read(len(MAGIC)) != MAGIC:
            raise BackupError(f"{src.name} no es un backup cifrado de LabX")
        while True:
            hdr = fi.read(4)
            if not hdr:
                break
            (n,) = struct.unpack(">I", hdr)
            tok = fi.read(n)
            if len(tok) != n:
                raise BackupError("Backup truncado")
            try:
                fo.write(f.decrypt(tok))
            except InvalidToken:
                raise BackupError("Clave incorrecta o backup corrupto")


def _plaintext_allowed() -> bool:
    return (os.getenv("BACKUP_ALLOW_PLAINTEXT") == "1"
            and os.getenv("APP_ENV", "development") != "production")


# ── Backup ───────────────────────────────────────────────────
def _sqlite_path() -> Path | None:
    if not DB_URL.startswith("sqlite"):
        return None
    path = DB_URL.replace("sqlite:///", "").replace("sqlite://", "")
    p = Path(path)
    if not p.is_absolute():
        p = Path(__file__).parent / p
    return p


def _finish(plain: Path, final_base: Path) -> Path:
    """Cifra `plain` hacia final_base+'.enc' y borra el claro. Devuelve el archivo final."""
    if _fernets(False) is None:
        if _plaintext_allowed():
            final = final_base
            shutil.move(str(plain), final)
            return final
        plain.unlink(missing_ok=True)
        raise BackupError("Sin clave de cifrado (BACKUP_ENCRYPTION_KEY/FERNET_KEY): backup NO creado")
    final = final_base.with_name(final_base.name + ".enc")
    try:
        encrypt_file(plain, final)
    except Exception:
        final.unlink(missing_ok=True)
        raise
    finally:
        plain.unlink(missing_ok=True)
    return final


def backup() -> Path:
    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fd, tmp_name = tempfile.mkstemp(prefix=".labx_tmp_", dir=BACKUP_DIR)
    os.close(fd)
    tmp = Path(tmp_name)

    try:
        if DB_URL.startswith("sqlite"):
            src = _sqlite_path()
            if not src or not src.exists():
                raise BackupError(f"DB no encontrada: {src}")
            s = sqlite3.connect(str(src))
            d = sqlite3.connect(str(tmp))
            try:
                s.backup(d)
            finally:
                d.close()
                s.close()
            base = BACKUP_DIR / f"labx_{ts}.db"
        else:
            # PostgreSQL: pg_dump | gzip (sin shell → sin inyección)
            import subprocess
            base = BACKUP_DIR / f"labx_{ts}.sql.gz"
            with open(tmp, "wb") as f_out:
                dump = subprocess.Popen(["pg_dump", "--no-password", DB_URL],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    gz = subprocess.Popen(["gzip", "-c"], stdin=dump.stdout,
                                          stdout=f_out, stderr=subprocess.PIPE)
                    dump.stdout.close()
                    gz.communicate()
                except FileNotFoundError:
                    # gzip no disponible: dump sin comprimir
                    dump.kill()
                    base = BACKUP_DIR / f"labx_{ts}.sql"
                    f_out.seek(0)
                    f_out.truncate()
                    r = subprocess.run(["pg_dump", "--no-password", DB_URL],
                                       stdout=f_out, stderr=subprocess.PIPE)
                    if r.returncode != 0:
                        raise BackupError(f"pg_dump falló: {r.stderr.decode()}")
                else:
                    err = dump.stderr.read()
                    dump.wait()
                    if dump.returncode != 0:
                        raise BackupError(f"pg_dump falló: {err.decode()}")
        final = _finish(tmp, base)
    finally:
        tmp.unlink(missing_ok=True)

    print(f"[OK] Backup {'cifrado' if final.suffix == '.enc' else 'EN CLARO'}: {final} ({final.stat().st_size // 1024} KB)")
    _cleanup_old()
    return final


def _file_ts(f: Path):
    m = _TS_RE.match(f.name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _cleanup_old() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    for f in BACKUP_DIR.glob("labx_*"):
        fts = _file_ts(f)
        if fts and fts < cutoff:
            try:
                f.unlink()
                print(f"[LIMPIEZA] Eliminado backup antiguo: {f.name}")
            except OSError:
                pass


# ── Restore ──────────────────────────────────────────────────
def restore(backup_file: str) -> None:
    src = Path(backup_file)
    if not src.exists():
        src = BACKUP_DIR / backup_file
    if not src.exists():
        raise BackupError(f"Archivo no encontrado: {backup_file}")

    plain = src
    tmp = None
    if src.name.endswith(".enc"):
        fd, name = tempfile.mkstemp(prefix=".labx_restore_", dir=src.parent)
        os.close(fd)
        tmp = plain = Path(name)
        try:
            decrypt_file(src, plain)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    try:
        if DB_URL.startswith("sqlite"):
            dst = _sqlite_path()
            if not dst:
                raise BackupError("DB path no determinable")
            if plain.name.endswith((".sql", ".sql.gz")):
                raise BackupError("Este backup es PostgreSQL y DATABASE_URL es SQLite")
            chk = sqlite3.connect(str(plain))
            try:
                res = chk.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                chk.close()
            if res != "ok":
                raise BackupError(f"El backup no pasa integrity_check: {res}")
            if dst.exists():
                safety = dst.with_suffix(f".before_restore_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.db")
                s = sqlite3.connect(str(dst))
                d = sqlite3.connect(str(safety))
                try:
                    s.backup(d)
                finally:
                    d.close()
                    s.close()
                print(f"[INFO] Backup de seguridad: {safety}")
            # Un -wal/-shm viejo sobre la BD restaurada la corrompería
            for suf in ("-wal", "-shm"):
                Path(str(dst) + suf).unlink(missing_ok=True)
            shutil.copy2(plain, dst)
            print(f"[OK] Restaurado desde {src} → {dst}")
        else:
            out = Path(str(src)[:-4]) if src.name.endswith(".enc") else src
            if tmp is not None:
                shutil.copy2(plain, out)
                print(f"[INFO] Descifrado en {out}")
            cmd = f"gunzip -c {out} | psql $DATABASE_URL" if out.name.endswith(".gz") else f"psql $DATABASE_URL < {out}"
            print("[INFO] Para PostgreSQL: " + cmd)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def list_backups() -> None:
    if not BACKUP_DIR.exists():
        print("Sin backups todavía.")
        return
    files = sorted(BACKUP_DIR.glob("labx_*"), reverse=True)
    if not files:
        print("Sin backups todavía.")
        return
    print(f"{'Archivo':<44} {'Tamaño':>10}  {'Fecha'}")
    print("-" * 74)
    for f in files:
        size = f.stat().st_size // 1024
        ts = _file_ts(f)
        print(f"{f.name:<44} {size:>8} KB  {ts.strftime('%Y-%m-%d %H:%M:%S UTC') if ts else '?'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LabX Backup Manager")
    parser.add_argument("--restore", metavar="FILE", help="Restaurar desde backup")
    parser.add_argument("--list",    action="store_true", help="Listar backups")
    args = parser.parse_args()
    try:
        if args.restore:
            restore(args.restore)
        elif args.list:
            list_backups()
        else:
            backup()
    except BackupError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
