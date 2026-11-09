"""SEGURIDAD-VERIFICADA (BUILD 368): afirmaciones técnicas de privacy.html contra el código."""
import importlib.util
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[2]


def _load_backup():
    spec = importlib.util.spec_from_file_location("labx_backup_t", ROOT / "backup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── bcrypt factor 12 ─────────────────────────────────────────
def test_bcrypt_factor_12_explicito():
    from api import auth
    assert auth.BCRYPT_ROUNDS == 12
    h = auth.hash_password("Clave-Segura-1")
    assert h.startswith("$2b$12$")
    assert auth.verify_password("Clave-Segura-1", h)
    assert not auth.verify_password("otra", h)


# ── JWT con expiración ───────────────────────────────────────
def test_jwt_expira_y_trae_claims():
    from api import auth
    t = auth.create_token("u1", "athlete", "N")
    p = jwt.decode(t, auth.SECRET_KEY, algorithms=[auth.ALGORITHM], audience=auth._AUDIENCE)
    assert p["exp"] - time.time() <= auth.TOKEN_HOURS * 3600 + 5
    assert p["iss"] == "labx" and p["aud"] == auth._AUDIENCE
    r = auth.create_token("u1", "athlete", "N", remember=True)
    pr = jwt.decode(r, auth.SECRET_KEY, algorithms=[auth.ALGORITHM], audience=auth._AUDIENCE)
    assert 29 * 86400 < pr["exp"] - time.time() <= 30 * 86400 + 5


def test_jwt_vencido_se_rechaza():
    from fastapi import HTTPException
    from api import auth
    old = jwt.encode({"sub": "u", "exp": datetime.now(timezone.utc) - timedelta(seconds=5),
                      "aud": auth._AUDIENCE}, auth.SECRET_KEY, algorithm=auth.ALGORITHM)
    with pytest.raises(HTTPException) as e:
        auth.decode_token(old)
    assert e.value.status_code == 401


# ── Fernet para credenciales ─────────────────────────────────
def test_credenciales_se_cifran_con_fernet():
    from api import crypto
    c = crypto.encrypt("mi-clave-garmin")
    assert c != "mi-clave-garmin" and crypto.is_encrypted(c)
    assert crypto.decrypt(c) == "mi-clave-garmin"


# ── Backups cifrados ─────────────────────────────────────────
@pytest.fixture
def bk(tmp_path, monkeypatch):
    mod = _load_backup()
    db = tmp_path / "live.db"
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t(v TEXT)")
    con.execute("INSERT INTO t VALUES ('SECRETO-DE-PRUEBA-12345')")
    con.commit()          # queda en el -wal: shutil.copy2 del .db NO lo vería
    monkeypatch.setattr(mod, "DB_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch.setattr(mod, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(mod, "KEEP_DAYS", 30)
    monkeypatch.delenv("BACKUP_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("FERNET_KEY_OLD", raising=False)
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("APP_ENV", "test")
    yield mod, db, con
    con.close()


def test_backup_cifrado_no_contiene_texto_plano(bk):
    mod, db, con = bk
    out = mod.backup()
    assert out.name.endswith(".db.enc")
    raw = out.read_bytes()
    assert raw.startswith(mod.MAGIC)
    assert b"SECRETO-DE-PRUEBA" not in raw and b"SQLite format" not in raw
    assert not list(out.parent.glob(".labx_tmp_*")), "no debe quedar el temporal en claro"
    assert [p.name for p in out.parent.iterdir() if not p.name.endswith(".enc")] == []


def test_backup_incluye_datos_en_wal_y_restaura(bk):
    mod, db, con = bk
    out = mod.backup()
    con.execute("DELETE FROM t")
    con.commit()
    con.close()
    mod.restore(str(out))
    chk = sqlite3.connect(db)
    try:
        assert chk.execute("SELECT v FROM t").fetchone()[0] == "SECRETO-DE-PRUEBA-12345"
    finally:
        chk.close()
    assert list(db.parent.glob("live.before_restore_*.db")), "debe dejar copia de seguridad previa"


def test_backup_clave_incorrecta_no_restaura(bk, monkeypatch):
    mod, db, con = bk
    out = mod.backup()
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())
    with pytest.raises(mod.BackupError):
        mod.restore(str(out))


def test_backup_restaura_tras_rotar_clave_con_key_old(bk, monkeypatch):
    mod, db, con = bk
    old = __import__("os").environ["FERNET_KEY"]
    out = mod.backup()
    con.close()   # Windows: no se puede sobrescribir una BD abierta
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("FERNET_KEY_OLD", old)
    mod.restore(str(out))   # no lanza


def test_backup_sin_clave_falla_y_no_deja_archivos(bk, monkeypatch):
    mod, db, con = bk
    monkeypatch.delenv("FERNET_KEY", raising=False)
    with pytest.raises(mod.BackupError):
        mod.backup()
    assert not list(mod.BACKUP_DIR.glob("labx_*"))
    assert not list(mod.BACKUP_DIR.glob(".labx_tmp_*"))


def test_backup_sin_clave_en_produccion_no_permite_claro(bk, monkeypatch):
    mod, db, con = bk
    monkeypatch.delenv("FERNET_KEY", raising=False)
    monkeypatch.setenv("BACKUP_ALLOW_PLAINTEXT", "1")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(mod.BackupError):
        mod.backup()


def test_backup_retencion_30_dias(bk):
    mod, db, con = bk
    mod.BACKUP_DIR.mkdir(exist_ok=True)
    viejo = mod.BACKUP_DIR / "labx_20200101_000000.db.enc"
    reciente_ts = (datetime.now(timezone.utc) - timedelta(days=29)).strftime("%Y%m%d_%H%M%S")
    reciente = mod.BACKUP_DIR / f"labx_{reciente_ts}.db.enc"
    pg_viejo = mod.BACKUP_DIR / "labx_20200101_000000.sql.gz.enc"
    for f in (viejo, reciente, pg_viejo):
        f.write_bytes(b"x")
    mod.backup()
    assert not viejo.exists() and not pg_viejo.exists()
    assert reciente.exists()


def test_scheduler_registra_backup_diario():
    src = (ROOT / "api" / "scheduler.py").read_text(encoding="utf-8")
    assert 'id="daily_encrypted_backup"' in src and "_daily_encrypted_backup," in src
