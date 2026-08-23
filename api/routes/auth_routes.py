from __future__ import annotations

import hashlib
import json
import os
import secrets
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, CoachAthlete, GroupMember
from ..schemas import LoginRequest, TokenResponse, UserCreate, UserOut
from ..auth import (
    hash_password, verify_password, create_token, get_current_user,
    revoke_token, _extract_token, TOKEN_HOURS, IS_PROD
)

from ..mailer import send_welcome, send_login_alert
from ..garmin_pull_service import background_sync_user, dispatch_garmin_sync
from ..audit import audit, ip_from_request, Action
from ..redis_client import check_rate_limit_redis, redis_delete

logger = logging.getLogger("labx.auth")
router = APIRouter(prefix="/auth", tags=["auth"])

_MAX_ATTEMPTS   = 10
_WINDOW_SECONDS = 3600

# Límites para registro y reset (más permisivos que login)
_MAX_REGISTER_PER_IP = 5    # registros por hora por IP
_MAX_RESET_PER_IP    = 3    # resets por hora por IP


def _check_rate_limit(ip: str, db: Session, max_attempts: int = _MAX_ATTEMPTS,
                      action: str = "login") -> None:
    """
    Rate limit en dos capas:
    1. Redis (fast, no-op si no disponible)
    2. DB LoginAttempt (fallback siempre activo)
    I-10: Raises HTTPException con headers X-RateLimit-* estándar.
    """
    # Capa 1: Redis (O(1), sin tocar DB)
    redis_key = f"rl:{action}:{ip}"
    allowed, count = check_rate_limit_redis(redis_key, max_attempts, _WINDOW_SECONDS)
    rl_hdrs = {
        "Retry-After":           str(_WINDOW_SECONDS),
        "X-RateLimit-Limit":     str(max_attempts),
        "X-RateLimit-Remaining": str(max(0, max_attempts - count)),
        "X-RateLimit-Window":    str(_WINDOW_SECONDS),
    }
    if not allowed:
        logger.warning("Rate limit Redis excedido ip=%s action=%s count=%d", ip, action, count)
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos. Espera 1 hora antes de reintentar.",
            headers=rl_hdrs,
        )

    # Capa 2: DB (siempre — fuente de verdad persistente)
    from ..models import LoginAttempt
    window_start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=_WINDOW_SECONDS)
    db_count = db.query(LoginAttempt).filter(
        LoginAttempt.ip == ip,
        LoginAttempt.attempted_at >= window_start,
    ).count()
    rl_hdrs["X-RateLimit-Remaining"] = str(max(0, max_attempts - db_count))
    if db_count >= max_attempts:
        logger.warning("Rate limit DB excedido ip=%s action=%s count=%d", ip, action, db_count)
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos. Espera 1 hora antes de reintentar.",
            headers=rl_hdrs,
        )


def _record_failed(ip: str, db: Session) -> None:
    from ..models import LoginAttempt
    db.add(LoginAttempt(ip=ip))
    db.commit()
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
    db.query(LoginAttempt).filter(LoginAttempt.attempted_at < cutoff).delete()
    db.commit()


def _clear_attempts(ip: str, db: Session) -> None:
    from ..models import LoginAttempt
    db.query(LoginAttempt).filter(LoginAttempt.ip == ip).delete()
    db.commit()
    # Limpiar también contador Redis al hacer login exitoso
    redis_delete(f"rl:login:{ip}")


def _prt_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _validate_password_strength(password: str) -> None:
    """
    S5: Política de contraseñas robusta.
    Mínimo 8 chars, una mayúscula, una minúscula, un número.
    """
    import re
    if len(password) < 8:
        raise HTTPException(422, "La contraseña debe tener al menos 8 caracteres.")
    if not re.search(r"[A-Z]", password):
        raise HTTPException(422, "La contraseña debe incluir al menos una letra mayúscula.")
    if not re.search(r"[a-z]", password):
        raise HTTPException(422, "La contraseña debe incluir al menos una letra minúscula.")
    if not re.search(r"[0-9]", password):
        raise HTTPException(422, "La contraseña debe incluir al menos un número.")


# ── Endpoints ─────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    ip = ip_from_request(request)  # I-03: X-Forwarded-For via ip_from_request
    _check_rate_limit(ip, db)

    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        _record_failed(ip, db)
        logger.info("Login fallido para email=%s ip=%s", body.email, ip)
        audit(db, Action.LOGIN_FAIL, ip=ip,
              user_agent=request.headers.get("user-agent"),
              detail={"email": body.email}, success=False)
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    if not user.activo:
        audit(db, Action.LOGIN_FAIL, user_id=user.id, ip=ip, success=False,
              detail={"reason": "account_inactive"})
        raise HTTPException(status_code=403, detail="Cuenta desactivada. Contacta al soporte.")

    _clear_attempts(ip, db)

    # Si tiene 2FA activo, NO emitir token — pedir código TOTP primero
    if user.totp_enabled and user.totp_secret:
        totp_code = (body.totp_code if hasattr(body, 'totp_code') else None) or body.__dict__.get('totp_code')
        if not totp_code:
            return TokenResponse(
                access_token = "",
                rol          = user.rol,
                nombre       = user.nombre,
                user_id      = user.id,
                plan_nivel   = user.plan_nivel or "basico",
                needs_2fa    = True,
            )
        try:
            import pyotp
            from ..crypto import decrypt as _dec_totp, is_encrypted as _is_enc
            # I-08: descifrar secret antes de verificar
            raw_secret = _dec_totp(user.totp_secret) if _is_enc(user.totp_secret) else user.totp_secret
            code_str = str(totp_code).strip()
            totp_ok  = pyotp.TOTP(raw_secret).verify(code_str, valid_window=1)

            # I-01: si TOTP falla, intentar backup code
            if not totp_ok and user.totp_backup_hash:
                import json as _json
                code_hash   = hashlib.sha256(code_str.upper().encode()).hexdigest()
                backup_list = _json.loads(user.totp_backup_hash)
                if code_hash in backup_list:
                    backup_list.remove(code_hash)  # usar backup code solo una vez
                    user.totp_backup_hash = _json.dumps(backup_list)
                    db.commit()
                    totp_ok = True
                    logger.warning("Backup code usado user_id=%s restantes=%d", user.id, len(backup_list))

            if not totp_ok:
                _record_failed(ip, db)
                raise HTTPException(401, "Código 2FA incorrecto")
        except ImportError:
            logger.critical("pyotp no instalado — 2FA DESACTIVADO. Instalar: pip install pyotp")
            raise HTTPException(503, "Servicio 2FA no disponible — contacta soporte")

    # I-04: Detectar dispositivo nuevo -- cookie persistente por navegador,
    # NO por IP+user-agent. La IP sola cambia todo el tiempo en redes
    # móviles (NAT de carrier) y sería un falso "dispositivo nuevo" en
    # CADA login desde el celular; el user-agent tampoco alcanza porque
    # dos dispositivos distintos pueden compartir el mismo. Se guarda una
    # lista corta de los últimos dispositivos conocidos (cookie válida por
    # navegador) en vez de un solo valor, para que alternar entre celu y
    # notebook no dispare la alerta en cada cambio.
    ua = request.headers.get("user-agent", "")
    known_devices = json.loads(user.last_device_hash) if user.last_device_hash else []
    device_cookie = request.cookies.get("lx_device_id")

    if device_cookie and device_cookie in known_devices:
        is_new_device = False
        device_id = device_cookie
    else:
        is_new_device = bool(known_devices)  # primer login del usuario nunca alerta
        device_id = secrets.token_urlsafe(24)
        known_devices.append(device_id)
        known_devices = known_devices[-5:]  # tope de 5 dispositivos conocidos
        user.last_device_hash = json.dumps(known_devices)

    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    remember = getattr(body, "remember_me", False)
    token = create_token(user.id, user.rol, user.nombre, user.token_gen or 1, remember=remember)
    cookie_max_age = (30 * 24 * 3600) if remember else (TOKEN_HOURS * 3600)

    logger.info("Login exitoso user_id=%s rol=%s ip=%s remember=%s", user.id, user.rol, ip, remember)
    audit(db, Action.LOGIN_OK, user_id=user.id, ip=ip, user_agent=ua)

    # I-04: Enviar alerta de login desde dispositivo nuevo (best-effort)
    if is_new_device:
        background_tasks.add_task(send_login_alert, user.email, user.nombre, ip, ua)

    # Setear HttpOnly cookie (más segura que localStorage)
    response.set_cookie(
        key      = "lx_access_token",
        value    = token,
        httponly = True,
        secure   = IS_PROD,
        samesite = "lax",
        max_age  = cookie_max_age,
        path     = "/",
    )
    response.set_cookie(
        key      = "lx_device_id",
        value    = device_id,
        httponly = True,
        secure   = IS_PROD,
        samesite = "lax",
        max_age  = 365 * 24 * 3600,
        path     = "/",
    )

    # Sync Garmin en background si el usuario tiene credenciales configuradas
    if user.garmin_email:
        method = dispatch_garmin_sync(user.id, background_tasks)
        logger.info("Garmin sync encolado user_id=%s method=%s", user.id, method)

    return TokenResponse(
        access_token = token,
        rol          = user.rol,
        nombre       = user.nombre,
        user_id      = user.id,
        plan_nivel   = user.plan_nivel or "basico",
        onboarding_done = (user.rol != "atleta") or (user.onboarding_completed_at is not None),
    )


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db),
           me: User = Depends(get_current_user)):
    """Invalida el token actual y limpia la cookie. Token queda en blacklist persistente."""
    token = _extract_token(request)
    if token:
        revoke_token(token, db=db)
    response.delete_cookie("lx_access_token", path="/")
    audit(db, Action.LOGOUT, user_id=me.id, ip=ip_from_request(request))
    return {"ok": True}


@router.delete("/account")
def delete_account(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Elimina la cuenta del usuario y todos sus datos (GDPR Art. 17)."""
    from ..models import (
        WorkoutLog, AssignedWorkout, GarminActivity,
        GarminTrainingLoad, GarminSyncStatus
    )
    # Revocar token y limpiar cookie
    token = _extract_token(request)
    if token:
        revoke_token(token, db=db)
    response.delete_cookie("lx_access_token", path="/")

    user_id = me.id
    # Borrar datos relacionados
    db.query(WorkoutLog).filter(WorkoutLog.user_id == user_id).delete()
    db.query(AssignedWorkout).filter(AssignedWorkout.athlete_id == user_id).delete()
    db.query(GarminActivity).filter(GarminActivity.user_id == user_id).delete()
    db.query(GarminTrainingLoad).filter(GarminTrainingLoad.user_id == user_id).delete()
    db.query(GarminSyncStatus).filter(GarminSyncStatus.user_id == user_id).delete()
    db.delete(me)
    db.commit()
    logger.info("Cuenta eliminada user_id=%s", user_id)
    return {"ok": True, "message": "Cuenta eliminada permanentemente"}


@router.get("/sessions")
def list_sessions(
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """
    I-06: Información de la sesión activa del usuario.
    LabX usa JWT stateless — no hay historial multi-sesión en DB,
    pero sí el dispositivo del último login y cuántas generaciones se han revocado.
    """
    ua = request.headers.get("user-agent", "unknown")
    return {
        "current_session": {
            "token_gen":        me.token_gen or 1,
            "last_device_hash": me.last_device_hash,
            "current_user_agent": ua[:120],
            "ip":               ip_from_request(request),
        },
        "note": "LabX usa JWT stateless. Usa /auth/revoke-all para cerrar todas las sesiones activas.",
    }


@router.post("/revoke-all")
def revoke_all_sessions(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Invalida TODAS las sesiones activas incrementando la generación del token."""
    me.token_gen = (me.token_gen or 1) + 1
    db.commit()
    # El token actual también queda inválido — emitir uno nuevo
    new_token = create_token(me.id, me.rol, me.nombre, me.token_gen)
    response.set_cookie(
        key="lx_access_token", value=new_token, httponly=True,
        secure=IS_PROD, samesite="lax", max_age=TOKEN_HOURS * 3600, path="/"
    )
    logger.info("Todas las sesiones revocadas user_id=%s gen=%s", me.id, me.token_gen)
    audit(db, Action.REVOKE_ALL, user_id=me.id, ip=ip_from_request(request),
          detail={"new_gen": me.token_gen})
    return {"ok": True, "access_token": new_token}


@router.post("/change-password")
def change_password(
    body: dict,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    old_pw = body.get("old_password", "")
    new_pw = body.get("new_password", "")
    if not old_pw or not new_pw:
        raise HTTPException(422, "Campos requeridos")
    if not verify_password(old_pw, me.password_hash):
        raise HTTPException(400, "Contraseña actual incorrecta")
    _validate_password_strength(new_pw)
    me.password_hash = hash_password(new_pw)
    db.commit()
    logger.info("Password cambiada user_id=%s", me.id)
    return {"ok": True}


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: UserCreate, request: Request, db: Session = Depends(get_db)):
    """Auto-registro público — crea una cuenta 'atleta' con plan 'basico'.

    Si el email ya existe pero es una invitación pendiente de un coach
    (pending_invite=True, creada por /coach/athletes sin contraseña real),
    en vez de rechazar por "email ya registrado" se RECLAMA: el atleta fija
    su propia contraseña acá, la cuenta se activa, y las relaciones
    CoachAthlete asociadas pasan de 'pending' a 'active' automáticamente
    (sin correo, sin token de invitación — la coincidencia de email + este
    registro normal es la "aceptación").
    """
    ip = ip_from_request(request)
    _check_rate_limit(ip, db, max_attempts=_MAX_REGISTER_PER_IP)

    email    = body.email.lower().strip()
    existing = db.query(User).filter(User.email == email).first()

    if existing and not existing.pending_invite:
        _record_failed(ip, db)
        raise HTTPException(status_code=409, detail="Este email ya está registrado.")
    _validate_password_strength(body.password)

    if existing:
        # Reclamar invitación pendiente: la cuenta ya existe (la creó un
        # coach), acá el atleta fija su propia contraseña por primera vez.
        user = existing
        user.nombre         = body.nombre.strip() or user.nombre
        user.password_hash  = hash_password(body.password)
        user.activo         = True
        user.pending_invite = False
        db.commit()

        links = db.query(CoachAthlete).filter(
            CoachAthlete.athlete_id == user.id, CoachAthlete.status == "pending"
        ).all()
        for link in links:
            link.status = "active"
            if link.group_id:
                already = db.query(GroupMember).filter(
                    GroupMember.group_id == link.group_id, GroupMember.athlete_id == user.id
                ).first()
                if not already:
                    db.add(GroupMember(group_id=link.group_id, athlete_id=user.id))
        db.commit()
        logger.info("Invitación reclamada user_id=%s email=%s coaches=%d", user.id, email, len(links))
    else:
        user = User(
            email         = email,
            nombre        = body.nombre.strip(),
            password_hash = hash_password(body.password),
            rol           = "atleta",
            plan_nivel    = "basico",
            activo        = True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("Nuevo registro user_id=%s email=%s", user.id, email)

    # Enviar email de bienvenida (best-effort, no bloquea)
    try:
        send_welcome(email, user.nombre)
    except Exception as e:
        logger.warning("Email bienvenida falló para %s: %s", email, e)

    token = create_token(user.id, user.rol, user.nombre)
    return TokenResponse(
        access_token = token,
        rol          = user.rol,
        nombre       = user.nombre,
        user_id      = user.id,
        plan_nivel   = user.plan_nivel,
        onboarding_done = user.rol != "atleta",
    )


@router.post("/2fa/setup")
def totp_setup(
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Genera un nuevo secreto TOTP y devuelve el QR URI para el autenticador."""
    try:
        import pyotp
        import qrcode
        import qrcode.image.svg
        import io, base64
    except ImportError:
        raise HTTPException(503, "pyotp o qrcode no instalados — pip install pyotp qrcode[pil]")

    if me.totp_enabled:
        raise HTTPException(400, "2FA ya está activo. Desactívalo primero.")

    secret = pyotp.random_base32()

    # I-08: Cifrar secreto TOTP antes de guardar en DB
    from ..crypto import encrypt as _encrypt_secret
    me.totp_secret  = _encrypt_secret(secret)
    me.totp_enabled = False  # no se activa hasta verificar
    db.commit()

    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=me.email, issuer_name="LabX"
    )
    # QR en SVG (sin dependencias PNG)
    try:
        img = qrcode.make(totp_uri, image_factory=qrcode.image.svg.SvgImage)
        buf = io.BytesIO()
        img.save(buf)
        qr_svg = base64.b64encode(buf.getvalue()).decode()
    except Exception:
        qr_svg = None

    # I-01: Generar 8 backup codes de recuperación
    import json as _json
    backup_codes = [secrets.token_hex(4).upper() for _ in range(8)]  # ej. "A3F7B2C1"
    backup_hashes = [hashlib.sha256(c.encode()).hexdigest() for c in backup_codes]
    me.totp_backup_hash = _json.dumps(backup_hashes)
    db.commit()

    return {
        "ok":          True,
        "secret":      secret,
        "totp_uri":    totp_uri,
        "qr_svg_b64":  qr_svg,
        "backup_codes": backup_codes,  # mostrar UNA SOLA VEZ al usuario
    }


@router.post("/2fa/verify")
def totp_verify(
    body: dict,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """
    Verifica el código TOTP y activa el 2FA.
    C-12: Rate limit — 5 intentos máx por usuario, bloqueo 30 min.
    """
    try:
        import pyotp
    except ImportError:
        raise HTTPException(503, "pyotp no instalado — contacta soporte")

    # C-12: rate limit por user_id (no IP, para no afectar usuarios detrás de NAT)
    rl_key = f"rl:2fa_verify:{me.id}"
    allowed, count = check_rate_limit_redis(rl_key, max_count=5, window_seconds=1800)
    _2fa_rl_hdrs = {
        "Retry-After":           "1800",
        "X-RateLimit-Limit":     "5",
        "X-RateLimit-Remaining": str(max(0, 5 - count)),
        "X-RateLimit-Window":    "1800",
    }
    if not allowed:
        logger.warning("2FA bruteforce bloqueado user_id=%s intentos=%d", me.id, count)
        raise HTTPException(
            429,
            "Demasiados intentos de código. Bloqueado 30 minutos.",
            headers=_2fa_rl_hdrs,
        )

    code = str(body.get("code", "")).strip()
    if not me.totp_secret:
        raise HTTPException(400, "Primero llama a /2fa/setup")

    # Descifrar secret si está cifrado (I-08)
    from ..crypto import decrypt as _decrypt
    try:
        secret = _decrypt(me.totp_secret) if me.totp_secret.startswith("gAA") else me.totp_secret
    except Exception:
        secret = me.totp_secret

    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=1):
        raise HTTPException(400, "Código incorrecto o expirado")

    # Limpiar contador de intentos al éxito
    redis_delete(rl_key)
    me.totp_enabled = True
    db.commit()
    audit(db, action=Action.TOTP_ENABLE, user_id=me.id, request=request, success=True)
    logger.info("2FA activado user_id=%s", me.id)
    return {"ok": True, "message": "2FA activado correctamente"}


@router.post("/2fa/disable")
def totp_disable(
    body: dict,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """
    Desactiva el 2FA.
    I-02: Requiere contraseña + código TOTP actual (previene desactivación por cuenta comprometida).
    """
    try:
        import pyotp
    except ImportError:
        raise HTTPException(503, "pyotp no instalado")

    if not me.totp_enabled:
        raise HTTPException(400, "El 2FA no está activo")

    # Verificar contraseña
    if not verify_password(body.get("password", ""), me.password_hash):
        raise HTTPException(400, "Contraseña incorrecta")

    # I-02: Verificar código TOTP actual
    totp_code = str(body.get("totp_code", "")).strip()
    if not totp_code:
        raise HTTPException(422, "Se requiere el código TOTP actual para desactivar el 2FA")

    from ..crypto import decrypt as _decrypt
    try:
        secret = _decrypt(me.totp_secret) if me.totp_secret and me.totp_secret.startswith("gAA") else me.totp_secret
    except Exception:
        secret = me.totp_secret

    totp = pyotp.TOTP(secret)
    if not totp.verify(totp_code, valid_window=1):
        raise HTTPException(400, "Código TOTP incorrecto")

    me.totp_secret  = None
    me.totp_enabled = False
    db.commit()
    audit(db, action=Action.TOTP_DISABLE, user_id=me.id, request=request, success=True)
    logger.info("2FA desactivado user_id=%s ip=%s", me.id, ip_from_request(request))
    return {"ok": True, "message": "2FA desactivado correctamente"}


@router.post("/forgot-password")
def forgot_password(body: dict, request: Request, db: Session = Depends(get_db)):
    """Solicita un link de reset. Siempre responde OK para no revelar si el email existe."""
    from ..models import PasswordResetToken

    ip = ip_from_request(request)
    _check_rate_limit(ip, db, max_attempts=_MAX_RESET_PER_IP)

    email = (body.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(422, "Email requerido")

    user = db.query(User).filter(User.email == email, User.activo == True).first()
    if user:
        raw_token = secrets.token_urlsafe(32)
        h = _prt_hash(raw_token)
        # Invalidar tokens previos del mismo usuario (solo 1 activo a la vez)
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at == None,
        ).delete()
        db.add(PasswordResetToken(
            token_hash = h,
            user_id    = user.id,
            expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
        ))
        db.commit()
        _send_reset_email(email, user.nombre, raw_token)
        logger.info("Reset solicitado para user_id=%s ip=%s", user.id, ip)
    _record_failed(ip, db)  # contar para rate-limit aunque no haya usuario
    return {"ok": True, "message": "Si el email existe, recibirás un link en breve."}


@router.post("/reset-password")
def reset_password(body: dict, db: Session = Depends(get_db)):
    from ..models import PasswordResetToken

    raw_token = (body.get("token") or "").strip()
    password  = body.get("password") or ""

    if not raw_token:
        raise HTTPException(400, "Token requerido")
    if len(password) < 8:
        raise HTTPException(422, "La contraseña debe tener al menos 8 caracteres.")

    h = _prt_hash(raw_token)
    entry = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == h,
        PasswordResetToken.used_at == None,
        PasswordResetToken.expires_at > datetime.now(timezone.utc).replace(tzinfo=None),
    ).first()

    if not entry:
        raise HTTPException(400, "Link inválido o expirado. Solicita uno nuevo.")

    user = db.query(User).filter(User.id == entry.user_id).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    user.password_hash = hash_password(password)
    entry.used_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    logger.info("Password reseteada user_id=%s", user.id)
    return {"ok": True, "message": "Contraseña actualizada. Ya puedes iniciar sesión."}


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)):
    return current


# ── S11: GDPR — Consentimiento de términos ─────────────────────

@router.post("/consent")
def record_consent(
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """
    S11: GDPR Art.7 — Registra el consentimiento explícito del usuario a los
    Términos de Servicio y Política de Privacidad. Guarda IP y timestamp.
    Llamar una vez al primer login o cuando se acepten nuevos términos.
    """
    from ..audit import ip_from_request
    me.gdpr_consent_at = datetime.now(timezone.utc).replace(tzinfo=None)
    me.gdpr_consent_ip = ip_from_request(request)
    db.commit()
    logger.info("GDPR consent registrado user_id=%s ip=%s", me.id, me.gdpr_consent_ip)
    return {
        "ok":         True,
        "consent_at": me.gdpr_consent_at.isoformat(),
        "message":    "Consentimiento registrado correctamente.",
    }


@router.get("/consent/status")
def consent_status(me: User = Depends(get_current_user)):
    """Devuelve si el usuario ya dio su consentimiento GDPR."""
    return {
        "has_consent": me.gdpr_consent_at is not None,
        "consent_at":  me.gdpr_consent_at.isoformat() if me.gdpr_consent_at else None,
    }


# ── S14: Preferencias de notificación ─────────────────────────

@router.get("/notification-prefs")
def get_notification_prefs(me: User = Depends(get_current_user)):
    """S14: Devuelve preferencias de notificación del usuario."""
    return {
        "email_weekly":  me.notif_email_weekly  if me.notif_email_weekly  is not None else True,
        "email_workout": me.notif_email_workout if me.notif_email_workout is not None else True,
        "push_wellness": me.notif_push_wellness if me.notif_push_wellness is not None else True,
    }


@router.patch("/notification-prefs")
def update_notification_prefs(
    body: dict,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """S14: Actualiza preferencias de notificación del usuario."""
    if "email_weekly"  in body: me.notif_email_weekly  = bool(body["email_weekly"])
    if "email_workout" in body: me.notif_email_workout = bool(body["email_workout"])
    if "push_wellness" in body: me.notif_push_wellness = bool(body["push_wellness"])
    db.commit()
    return {"ok": True, "message": "Preferencias actualizadas."}


# ── Email helpers ──────────────────────────────────────────────

def _get_app_url() -> str:
    return os.getenv("APP_URL", "http://localhost:8000")


def _send_reset_email(email: str, nombre: str, token: str) -> None:
    from ..mailer import send_email
    app_url    = _get_app_url()
    reset_link = f"{app_url}/reset-password.html?token={token}"
    html = f"""
    <div style="font-family:Inter,sans-serif;background:#04080F;color:#F0F9FF;padding:40px 24px;max-width:560px;margin:0 auto;border-radius:16px">
      <h2>Hola {nombre},</h2>
      <p style="color:#7FB3CC;margin:16px 0">Recibimos una solicitud para restablecer tu contraseña en LabX.</p>
      <div style="text-align:center;margin:28px 0">
        <a href="{reset_link}" style="display:inline-block;background:linear-gradient(135deg,#0EA5E9,#0284C7);color:#fff;font-weight:800;text-decoration:none;padding:14px 32px;border-radius:10px;font-size:1rem;text-transform:uppercase;letter-spacing:.06em">
          Restablecer contraseña →
        </a>
      </div>
      <p style="color:#3D6880;font-size:.8rem">Este link expira en 1 hora. Si no solicitaste este cambio, ignora este email.</p>
    </div>
    """
    if not send_email(email, "LabX — Restablecer contraseña", html):
        logger.info("Reset link (dev, email no enviado): %s", reset_link)
