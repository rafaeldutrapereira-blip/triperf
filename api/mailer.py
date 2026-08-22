"""
Mailer centralizado — Resend.com.
Uso: from .mailer import send_email
Si RESEND_API_KEY no está configurada, loguea el email sin enviarlo (desarrollo).
"""
from __future__ import annotations
import logging
import os

logger = logging.getLogger("labx.mailer")

_FROM = os.getenv("EMAIL_FROM", "LabX <noreply@labx.app>")


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
        import resend, base64
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
    html = f"""
    <div style="font-family:Inter,sans-serif;background:#04080F;color:#F0F9FF;padding:40px 24px;max-width:560px;margin:0 auto;border-radius:16px">
      <div style="text-align:center;margin-bottom:28px">
        <span style="font-size:2.5rem;font-weight:900;font-style:italic;letter-spacing:-.02em">
          <span style="color:#F0F9FF">LAB</span><span style="background:linear-gradient(125deg,#F0A500,#FF6535);-webkit-background-clip:text;-webkit-text-fill-color:transparent">X</span>
        </span>🌺
      </div>
      <h1 style="font-size:1.4rem;margin-bottom:8px">¡Bienvenido, {nombre}! 🏊🚴🏃</h1>
      <p style="color:#7FB3CC;margin-bottom:24px">Tu cuenta LabX está lista. Aquí puedes empezar:</p>
      <ul style="padding-left:20px;color:#7FB3CC;margin-bottom:24px">
        <li style="margin-bottom:8px">📊 Registra tu primer entrenamiento en el Dashboard</li>
        <li style="margin-bottom:8px">🔄 Conecta Garmin para sync automático</li>
        <li style="margin-bottom:8px">🏁 Usa el Predictor de carrera para tu próximo objetivo</li>
        <li style="margin-bottom:8px">🧬 Registra tus análisis de sangre y nutrición</li>
      </ul>
      <div style="text-align:center;margin-bottom:28px">
        <a href="{app_url}/onboarding.html" style="display:inline-block;background:linear-gradient(135deg,#FF6535,#E8490A);color:#fff;font-weight:800;font-size:1rem;letter-spacing:.06em;text-transform:uppercase;text-decoration:none;padding:14px 32px;border-radius:10px;box-shadow:0 4px 24px rgba(255,101,53,.3)">
          Configurar mi cuenta →
        </a>
      </div>
      <p style="color:#3D6880;font-size:.8rem;text-align:center">El equipo LabX &nbsp;·&nbsp; Soporte: partnerships@labxperformanceapp.com</p>
    </div>
    """
    send_email(email, f"¡Bienvenido a LabX, {nombre}! 🌺", html, tags=["welcome"])


def send_day3_drip(email: str, nombre: str, app_url: str = "") -> None:
    app_url = app_url or os.getenv("APP_URL", "http://localhost:8000")
    html = f"""
    <div style="font-family:Inter,sans-serif;background:#04080F;color:#F0F9FF;padding:40px 24px;max-width:560px;margin:0 auto;border-radius:16px">
      <h1 style="font-size:1.3rem;margin-bottom:8px">Hola {nombre}, ¿cómo va el entrenamiento? 💪</h1>
      <p style="color:#7FB3CC;margin-bottom:20px">Llevas 3 días con LabX. ¿Sabías que con el plan <strong style="color:#FF6535">Pro</strong> puedes:</p>
      <ul style="padding-left:20px;color:#7FB3CC;margin-bottom:24px">
        <li style="margin-bottom:8px">📈 Ver tu curva de fitness PMC (ATL / CTL / TSB) completa</li>
        <li style="margin-bottom:8px">🔄 Sync automático con Garmin Connect</li>
        <li style="margin-bottom:8px">🏁 Predecir tiempos en Ironman, 70.3 y Olímpico</li>
        <li style="margin-bottom:8px">🧬 Análisis de laboratorio y planes de nutrición</li>
      </ul>
      <div style="text-align:center;margin-bottom:28px">
        <a href="{app_url}/dashboard.html?upgrade=1" style="display:inline-block;background:linear-gradient(135deg,#A855F7,#7C3AED);color:#fff;font-weight:800;font-size:1rem;letter-spacing:.06em;text-transform:uppercase;text-decoration:none;padding:14px 32px;border-radius:10px">
          Actualizar a Pro — $19/mes →
        </a>
      </div>
      <p style="color:#3D6880;font-size:.8rem;text-align:center">LabX · Si no quieres recibir más emails, <a href="{app_url}/unsubscribe" style="color:#3D6880">cancela aquí</a></p>
    </div>
    """
    send_email(email, f"{nombre}, desbloquea tu potencial completo en LabX 🚀", html, tags=["drip", "day3"])


def send_day7_drip(email: str, nombre: str, app_url: str = "") -> None:
    app_url = app_url or os.getenv("APP_URL", "http://localhost:8000")
    html = f"""
    <div style="font-family:Inter,sans-serif;background:#04080F;color:#F0F9FF;padding:40px 24px;max-width:560px;margin:0 auto;border-radius:16px">
      <h1 style="font-size:1.3rem;margin-bottom:8px">¡Una semana entrenando con LabX, {nombre}! 🎯</h1>
      <p style="color:#7FB3CC;margin-bottom:20px">¿Tienes un coach que te guía? Con LabX <strong style="color:#F0A500">Coach Platform</strong> puedes gestionar hasta 50+ atletas, asignar sesiones y ver reportes en tiempo real.</p>
      <p style="color:#7FB3CC;margin-bottom:24px">¿O prefieres tener un coach que te asesore? Contáctanos y te conectamos.</p>
      <div style="text-align:center;margin-bottom:28px">
        <a href="{app_url}/landing.html#contact" style="display:inline-block;background:linear-gradient(135deg,#F0A500,#FF6535);color:#000;font-weight:800;font-size:1rem;letter-spacing:.06em;text-transform:uppercase;text-decoration:none;padding:14px 32px;border-radius:10px">
          Quiero saber más →
        </a>
      </div>
      <p style="color:#3D6880;font-size:.8rem;text-align:center">LabX · <a href="{app_url}/unsubscribe" style="color:#3D6880">Cancelar suscripción a emails</a></p>
    </div>
    """
    send_email(email, f"Una semana con LabX — ¿tienes coach, {nombre}? 🧑‍💼", html, tags=["drip", "day7"])
