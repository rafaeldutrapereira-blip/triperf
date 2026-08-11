#!/usr/bin/env python3
"""
LabX — Script de backup automático
====================================
Uso:
    python backup.py                    # Backup de SQLite a backups/
    python backup.py --restore <file>   # Restaurar desde un backup
    python backup.py --list             # Listar backups disponibles

Configurar en cron (diariamente a las 2am):
    0 2 * * * cd /ruta/labx && python backup.py >> logs/backup.log 2>&1

Para PostgreSQL en producción, usar pg_dump en lugar de shutil.copy.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
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


def _sqlite_path() -> Path | None:
    if not DB_URL.startswith("sqlite"):
        return None
    path = DB_URL.replace("sqlite:///", "").replace("sqlite://", "")
    p = Path(path)
    if not p.is_absolute():
        p = Path(__file__).parent / p
    return p


def backup() -> Path:
    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if DB_URL.startswith("sqlite"):
        src = _sqlite_path()
        if not src or not src.exists():
            print(f"[ERROR] DB no encontrada: {src}", file=sys.stderr)
            sys.exit(1)
        dst = BACKUP_DIR / f"labx_{ts}.db"
        shutil.copy2(src, dst)
        size_kb = dst.stat().st_size // 1024
        print(f"[OK] Backup SQLite: {dst} ({size_kb} KB)")

    else:
        # PostgreSQL: usar pg_dump via subprocess (evita shell injection)
        import subprocess
        dst = BACKUP_DIR / f"labx_{ts}.sql.gz"
        try:
            with open(dst, "wb") as f_out:
                dump = subprocess.Popen(
                    ["pg_dump", "--no-password", DB_URL],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                gzip_proc = subprocess.Popen(
                    ["gzip", "-c"],
                    stdin=dump.stdout,
                    stdout=f_out,
                    stderr=subprocess.PIPE,
                )
                dump.stdout.close()
                gzip_proc.communicate()
                dump.wait()
            if dump.returncode != 0:
                _, err = dump.communicate()
                print(f"[ERROR] pg_dump falló: {err.decode()}", file=sys.stderr)
                dst.unlink(missing_ok=True)
                sys.exit(1)
        except FileNotFoundError:
            # gzip no disponible — dump sin comprimir
            dst = BACKUP_DIR / f"labx_{ts}.sql"
            with open(dst, "wb") as f_out:
                result = subprocess.run(
                    ["pg_dump", "--no-password", DB_URL],
                    stdout=f_out,
                    stderr=subprocess.PIPE,
                )
            if result.returncode != 0:
                print(f"[ERROR] pg_dump falló: {result.stderr.decode()}", file=sys.stderr)
                dst.unlink(missing_ok=True)
                sys.exit(1)
        size_kb = dst.stat().st_size // 1024
        print(f"[OK] Backup PostgreSQL: {dst} ({size_kb} KB)")

    _cleanup_old()
    return dst


def _cleanup_old() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    for f in BACKUP_DIR.glob("labx_*.db"):
        try:
            ts_str = f.stem.replace("labx_", "")
            fts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
            if fts < cutoff:
                f.unlink()
                print(f"[LIMPIEZA] Eliminado backup antiguo: {f.name}")
        except (ValueError, OSError):
            pass
    for f in list(BACKUP_DIR.glob("labx_*.sql")) + list(BACKUP_DIR.glob("labx_*.sql.gz")):
        try:
            ts_str = f.stem.replace("labx_", "")
            fts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
            if fts < cutoff:
                f.unlink()
                print(f"[LIMPIEZA] Eliminado backup antiguo: {f.name}")
        except (ValueError, OSError):
            pass


def restore(backup_file: str) -> None:
    src = Path(backup_file)
    if not src.exists():
        src = BACKUP_DIR / backup_file
    if not src.exists():
        print(f"[ERROR] Archivo no encontrado: {backup_file}", file=sys.stderr)
        sys.exit(1)

    if DB_URL.startswith("sqlite"):
        dst = _sqlite_path()
        if not dst:
            print("[ERROR] DB path no determinable", file=sys.stderr)
            sys.exit(1)
        # Backup de seguridad antes de restaurar
        safety = dst.with_suffix(f".before_restore_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.db")
        if dst.exists():
            shutil.copy2(dst, safety)
            print(f"[INFO] Backup de seguridad: {safety}")
        shutil.copy2(src, dst)
        print(f"[OK] Restaurado desde {src} → {dst}")
    else:
        print("[INFO] Para PostgreSQL: psql $DATABASE_URL < " + str(src))


def list_backups() -> None:
    if not BACKUP_DIR.exists():
        print("Sin backups todavía.")
        return
    files = sorted(BACKUP_DIR.glob("labx_*"), reverse=True)
    if not files:
        print("Sin backups todavía.")
        return
    print(f"{'Archivo':<40} {'Tamaño':>10}  {'Fecha'}")
    print("-" * 70)
    for f in files:
        size = f.stat().st_size // 1024
        ts_str = f.stem.replace("labx_", "")
        try:
            ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S UTC")
        except ValueError:
            ts = "?"
        print(f"{f.name:<40} {size:>8} KB  {ts}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LabX Backup Manager")
    parser.add_argument("--restore", metavar="FILE", help="Restaurar desde backup")
    parser.add_argument("--list",    action="store_true", help="Listar backups")
    args = parser.parse_args()

    if args.restore:
        restore(args.restore)
    elif args.list:
        list_backups()
    else:
        backup()
