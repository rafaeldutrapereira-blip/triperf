"""
Mailer centralizado — Resend.com.
Uso: from .mailer import send_email
Si RESEND_API_KEY no está configurada, loguea el email sin enviarlo (desarrollo).

Estándar visual de los correos (2026-08-22, pedido explícito del usuario):
  - Fuente: 'Calibri Light' con fallback seguro (Calibri no viene instalada
    en todos los sistemas -- Mac/Linux/webmail la sustituyen), tamaño 12pt.
  - Logo: PNG real ya existente (icon-192.png, el mismo ícono de la PWA/app
    -- incluye la flor 🌺 como parte del ícono oficial), embebido en base64.
    NO se intentó recrear el logo animado del login (anillos con CSS
    @keyframes) porque las animaciones CSS no funcionan de forma fiable en
    clientes de correo (Outlook de escritorio las ignora por completo) --
    se usa el activo estático real que ya existe en vez de fabricar uno nuevo.
  - Footer estándar: marca LabX + versión real (leída de sw.js, no
    hardcodeada, para no desincronizarse) + tagline + firma del equipo --
    mismo patrón que footer.js usa en el resto de las páginas de LabX.
  - Bug real corregido de paso: las plantillas anteriores usaban unidades
    `rem` (ej. font-size:2.5rem) -- Outlook de escritorio y varios clientes
    de correo ignoran rem (no hay contexto de raíz que puedan resolver).
    Todo convertido a px/pt.
"""
from __future__ import annotations
import base64
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("labx.mailer")

_FROM = os.getenv("EMAIL_FROM", "LabX <noreply@labx.app>")

_ROOT_DIR = Path(__file__).resolve().parent.parent
_FONT_STACK = "'Calibri Light', Calibri, 'Segoe UI', Tahoma, Geneva, sans-serif"


def _load_logo_b64() -> str:
    """PNG real del ícono de LabX (incluye la flor 🌺), leído una sola vez.
    Vacío si el archivo no está (no debería pasar en producción, pero un
    correo sin logo es mejor que un error 500 al enviar)."""
    try:
        data = (_ROOT_DIR / "icon-192.png").read_bytes()
        return base64.b64encode(data).decode()
    except Exception as e:
        logger.warning("No se pudo cargar icon-192.png para el email: %s", e)
        return ""


_LOGO_B64 = _load_logo_b64()


def _get_build_version() -> str:
    """Lee BUILD_VERSION real de sw.js -- mismo mecanismo que footer.js usa
    en las páginas web, para que el correo nunca muestre una versión vieja
    hardcodeada que se desincronice del deploy real."""
    try:
        content = (_ROOT_DIR / "sw.js").read_text(encoding="utf-8")
        m = re.search(r"BUILD_VERSION\s*=\s*'(\d+)'", content)
        if m:
            return m.group(1)
    except Exception as e:
        logger.warning("No se pudo leer BUILD_VERSION de sw.js: %s", e)
    return "?"


def _email_header_html() -> str:
    logo_img = (
        f'<img src="data:image/png;base64,{_LOGO_B64}" width="48" height="48" '
        'alt="LabX" style="border-radius:12px;vertical-align:middle;display:inline-block">'
        if _LOGO_B64 else ""
    )
    return f"""
    <div style="text-align:center;margin-bottom:24px">
      {logo_img}
      <span style="font-size:22px;font-weight:900;font-style:italic;letter-spacing:-.5px;vertical-align:middle;margin-left:10px;color:#F0F9FF">LAB<span style="color:#FF6535">X</span></span>
    </div>
    """


def _email_footer_html() -> str:
    version = _get_build_version()
    return f"""
    <div style="border-top:1px solid rgba(8,145,178,.15);margin-top:28px;padding-top:16px;text-align:center">
      <p style="margin:0 0 6px;font-size:12pt;color:#F0F9FF">Con cariño, <strong>El equipo LabX</strong> 🌺</p>
      <p style="margin:0 0 3px;font-size:10pt;color:#3D6880">LabX v{version} &middot; Plataforma privada de rendimiento atlético</p>
      <p style="margin:0;font-size:10pt;color:#3D6880">Soporte: <a href="mailto:partnerships@labxperformanceapp.com" style="color:#3D6880">partnerships@labxperformanceapp.com</a></p>
    </div>
    """


def _wrap_email_body(inner_html: str) -> str:
    """Envuelve el contenido propio de cada correo con el header/footer
    estándar + la tipografía base (Calibri Light 12pt) -- un solo lugar
    para el estándar visual, en vez de repetirlo en cada función de envío."""
    return f"""
    <div style="font-family:{_FONT_STACK};font-size:12pt;line-height:1.5;background:#04080F;color:#F0F9FF;padding:32px 24px;max-width:560px;margin:0 auto;border-radius:16px">
      {_email_header_html()}
      {inner_html}
      {_email_footer_html()}
    </div>
    """


def send_email(
    to: str,
    subject: str,
    html: str,
    *,
    tags: list[str] | None = None,
    attachments: list[dict] | None = None,   # [{"filename": "x.zwo", "content": bytes}]
) -> bool:
    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key or api_key.startswith("re_XXX"):
        logger.info("[DEV] Email NO enviado (configura RESEND_API_KEY) → to=%s subject=%s", to, subject)
        return False
    try:
        import resend
        resend.api_key = api_key
        payload: dict = {"from": _FROM, "to": [to], "subject": subject, "html": html}
        if tags:
            payload["tags"] = [{"name": t} for t in tags]
        if attachments:
            payload["attachments"] = [
                {"filename": a["filename"], "content": base64.b64encode(a["content"]).decode()}
                for a in attachments
            ]
        resend.Emails.send(payload)
        logger.info("Email enviado to=%s subject=%s attachments=%d", to, subject, len(attachments or []))
        return True
    except Exception as e:
        logger.error("Error enviando email to=%s: %s", to, e)
        return False


def send_welcome(email: str, nombre: str, app_url: str = "") -> None:
    app_url = app_url or os.getenv("APP_URL", "http://localhost:8000")
    inner = f"""
      <h1 style="font-size:18px;margin:0 0 8px">¡Bienvenido a LabX, {nombre}! 🏊🚴🏃</h1>
      <p style="color:#7FB3CC;margin:0 0 20px">Tu cuenta ya está lista. LabX es tu plataforma de entrenamiento para deportes de resistencia — running, ciclismo, natación y triatlón: sincroniza tus datos reales, calcula tu carga de entrenamiento y te ayuda a llegar a tu próxima carrera en tu mejor forma.</p>
      <ul style="padding-left:20px;color:#7FB3CC;margin:0 0 20px">
        <li style="margin-bottom:8px">🔄 Conecta Garmin o Strava — tu carga de entrenamiento (CTL/ATL/TSB) y tu Readiness diario se calculan solos, con tus datos reales, sea cual sea tu deporte</li>
        <li style="margin-bottom:8px">🤖 Hablá con tu AI Coach — te ayuda a ajustar el plan según cómo llegaste a entrenar</li>
        <li style="margin-bottom:8px">🏁 Usa el Predictor de Carrera — mirá si vas a llegar a tu objetivo (maratón, media maratón, o triatlón sprint/olímpico/70.3/Ironman) con tu forma actual</li>
        <li style="margin-bottom:8px">📲 Instalá LabX en tu celular — agregala a la pantalla de inicio desde el navegador, funciona como una app</li>
      </ul>
      <div style="text-align:center;margin-bottom:8px">
        <a href="{app_url}/onboarding.html" style="display:inline-block;background:linear-gradient(135deg,#FF6535,#E8490A);color:#fff;font-weight:800;font-size:13pt;letter-spacing:1px;text-transform:uppercase;text-decoration:none;padding:14px 32px;border-radius:10px">
          Empezar mi plan →
        </a>
      </div>
    """
    send_email(email, f"¡Bienvenido a LabX, {nombre}! 🌺", _wrap_email_body(inner), tags=["welcome"])


def send_day3_drip(email: str, nombre: str, app_url: str = "") -> None:
    app_url = app_url or os.getenv("APP_URL", "http://localhost:8000")
    inner = f"""
      <h1 style="font-size:17px;margin:0 0 8px">Hola {nombre}, ¿cómo va el entrenamiento? 💪</h1>
      <p style="color:#7FB3CC;margin:0 0 16px">Llevas 3 días con LabX. ¿Sabías que con el plan <strong style="color:#FF6535">Pro</strong> puedes:</p>
      <ul style="padding-left:20px;color:#7FB3CC;margin:0 0 20px">
        <li style="margin-bottom:8px">📈 Ver tu curva de fitness PMC (ATL / CTL / TSB) completa</li>
        <li style="margin-bottom:8px">🔄 Sync automático con Garmin Connect</li>
        <li style="margin-bottom:8px">🏁 Predecir tiempos en Ironman, 70.3 y Olímpico</li>
        <li style="margin-bottom:8px">🧬 Análisis de laboratorio y planes de nutrición</li>
      </ul>
      <div style="text-align:center;margin-bottom:8px">
        <a href="{app_url}/dashboard.html?upgrade=1" style="display:inline-block;background:linear-gradient(135deg,#A855F7,#7C3AED);color:#fff;font-weight:800;font-size:13pt;letter-spacing:1px;text-transform:uppercase;text-decoration:none;padding:14px 32px;border-radius:10px">
          Actualizar a Pro — $19/mes →
        </a>
      </div>
    """
    send_email(email, f"{nombre}, desbloquea tu potencial completo en LabX 🚀", _wrap_email_body(inner), tags=["drip", "day3"])


def send_day7_drip(email: str, nombre: str, app_url: str = "") -> None:
    app_url = app_url or os.getenv("APP_URL", "http://localhost:8000")
    inner = f"""
      <h1 style="font-size:17px;margin:0 0 8px">¡Una semana entrenando con LabX, {nombre}! 🎯</h1>
      <p style="color:#7FB3CC;margin:0 0 16px">¿Tienes un coach que te guía? Con LabX <strong style="color:#F0A500">Coach Platform</strong> puedes gestionar hasta 50+ atletas, asignar sesiones y ver reportes en tiempo real.</p>
      <p style="color:#7FB3CC;margin:0 0 20px">¿O prefieres tener un coach que te asesore? Contáctanos y te conectamos.</p>
      <div style="text-align:center;margin-bottom:8px">
        <a href="{app_url}/landing.html#contact" style="display:inline-block;background:linear-gradient(135deg,#F0A500,#FF6535);color:#000;font-weight:800;font-size:13pt;letter-spacing:1px;text-transform:uppercase;text-decoration:none;padding:14px 32px;border-radius:10px">
          Quiero saber más →
        </a>
      </div>
      <p style="text-align:center;margin:12px 0 0"><a href="{app_url}/unsubscribe" style="color:#3D6880;font-size:10pt">Cancelar suscripción a estos emails</a></p>
    """
    send_email(email, f"Una semana con LabX — ¿tienes coach, {nombre}? 🧑‍💼", _wrap_email_body(inner), tags=["drip", "day7"])
