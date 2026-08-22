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
      <p style="margin:0 0 6px;font-size:12pt;color:#F0F9FF">Saludos cordiales, <strong>El equipo LabX</strong> 🌺</p>
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
    """Correo de bienvenida institucional (2026-08-22, pedido explícito del
    usuario -- tono formal/corporativo en vez del casual con emojis que
    tenía antes). No se linkea a App Store/Google Play: la app nativa
    (Capacitor, Sprint 55) todavía no está compilada ni publicada en
    ninguna tienda -- se indica instalación PWA real, que sí funciona hoy."""
    app_url = app_url or os.getenv("APP_URL", "http://localhost:8000")
    inner = f"""
      <p style="margin:0 0 16px">Estimado/a <strong>{nombre}</strong>,</p>
      <p style="color:#7FB3CC;margin:0 0 16px">En nombre de todo el equipo de <strong style="color:#F0F9FF">LabX</strong>, le damos la más cordial bienvenida y le agradecemos la confianza depositada en nuestra plataforma.</p>
      <p style="color:#7FB3CC;margin:0 0 20px">LabX es una plataforma de entrenamiento diseñada para deportistas de resistencia — running, ciclismo, natación y triatlón. Sincronizamos sus datos reales de dispositivos como Garmin y Strava para calcular su carga de entrenamiento (CTL/ATL/TSB), su estado de recuperación diario, y ofrecerle herramientas como nuestro Predictor de Carrera y un Coach con inteligencia artificial, para acompañarle en cada etapa de su preparación.</p>

      <p style="margin:0 0 6px"><strong>Acceso a la plataforma</strong></p>
      <ul style="padding-left:20px;color:#7FB3CC;margin:0 0 20px">
        <li style="margin-bottom:8px"><strong style="color:#F0F9FF">Plataforma web:</strong> ingrese en <a href="{app_url}" style="color:#0EA5E9">{app_url}</a> con su correo y contraseña registrados.</li>
        <li style="margin-bottom:8px"><strong style="color:#F0F9FF">Aplicación móvil:</strong> LabX está disponible como aplicación web progresiva — desde su celular, abra el sitio en su navegador y seleccione "Agregar a pantalla de inicio" para instalarla como una app.</li>
      </ul>

      <p style="margin:0 0 6px"><strong>Primeros pasos recomendados</strong></p>
      <ol style="padding-left:20px;color:#7FB3CC;margin:0 0 20px">
        <li style="margin-bottom:8px">Complete su perfil — datos personales, objetivos deportivos y parámetros de entrenamiento (FTP, umbrales).</li>
        <li style="margin-bottom:8px">Conecte su dispositivo (Garmin o Strava) para que su carga de entrenamiento se calcule automáticamente con datos reales.</li>
        <li style="margin-bottom:8px">Explore su Dashboard y defina su próximo objetivo de carrera en el Predictor.</li>
      </ol>

      <div style="text-align:center;margin-bottom:20px">
        <a href="{app_url}/onboarding.html" style="display:inline-block;background:linear-gradient(135deg,#FF6535,#E8490A);color:#fff;font-weight:800;font-size:13pt;letter-spacing:1px;text-transform:uppercase;text-decoration:none;padding:14px 32px;border-radius:10px">
          Acceder a mi cuenta →
        </a>
      </div>

      <p style="margin:0 0 6px"><strong>¿Necesita ayuda?</strong></p>
      <p style="color:#7FB3CC;margin:0 0 16px">Ante cualquier consulta, escríbanos a <a href="mailto:partnerships@labxperformanceapp.com" style="color:#0EA5E9">partnerships@labxperformanceapp.com</a> — con gusto le asistiremos.</p>

      <p style="color:#7FB3CC;margin:0">Quedamos atentos a acompañarle en esta nueva etapa.</p>
    """
    send_email(email, f"Bienvenido a LabX — Su plataforma de rendimiento ya está lista", _wrap_email_body(inner), tags=["welcome"])


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


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICACIÓN DE INICIO DE SESIÓN (I-04, rediseñado 2026-08-22)
# ─────────────────────────────────────────────────────────────────────────────
# Reemplaza el _alert_new_device() que vivía inline en auth_routes.py con HTML
# ad-hoc (sin el estándar de marca) -- movido acá para que use el mismo
# header/footer/tipografía que el resto de los correos, y con datos reales
# de dispositivo/ubicación en vez de solo el user-agent crudo sin parsear.

_UA_BROWSERS = [
    ("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"),
    ("Chrome/", "Chrome"), ("Safari/", "Safari"),
]
_UA_OS = [
    # iPhone/iPad ANTES que Mac OS X -- el user-agent de iOS Safari siempre
    # incluye la cadena literal "like Mac OS X" (por compatibilidad historica
    # de Apple), asi que si "Mac OS X" se revisa primero, un iPhone se
    # detecta erroneamente como "macOS". Bug real encontrado probando con
    # un UA de iPhone antes de dar esto por terminado.
    ("iPhone", "iOS"), ("iPad", "iOS"), ("Android", "Android"),
    ("Windows NT", "Windows"), ("Mac OS X", "macOS"), ("Linux", "Linux"),
]


def _parse_device(ua: str) -> str:
    """Parseo liviano por substring (sin agregar dependencia nueva tipo
    user-agents/ua-parser) -- cubre los casos reales más comunes. No es
    exhaustivo (no distingue versiones ni dispositivos exóticos), pero es
    honesto: si no reconoce el patrón, dice 'Navegador desconocido' en vez
    de inventar un dato."""
    if not ua:
        return "Dispositivo desconocido"
    browser = next((name for key, name in _UA_BROWSERS if key in ua), None)
    os_name = next((name for key, name in _UA_OS if key in ua), None)
    if browser and os_name:
        return f"{browser} en {os_name}"
    if browser:
        return browser
    if os_name:
        return os_name
    return "Navegador desconocido"


def _geolocate_ip(ip: str) -> str | None:
    """Ubicación estimada real vía ip-api.com (gratis, sin API key,
    pedido explícito del usuario tras confirmar el trade-off: manda la IP
    a un tercero, agrega latencia solo en logins de dispositivo nuevo --no
    en cada login normal--, y no funciona para IPs privadas/localhost
    (127.0.0.1, 192.168.x.x, etc., que devuelven None a propósito, nunca
    una ubicación inventada)."""
    if not ip or ip.startswith(("127.", "192.168.", "10.", "::1")):
        return None
    try:
        import httpx
        r = httpx.get(f"http://ip-api.com/json/{ip}", params={"fields": "status,city,country"}, timeout=3)
        data = r.json()
        if data.get("status") == "success":
            city = data.get("city")
            country = data.get("country")
            if city and country:
                return f"{city}, {country}"
            return country or city
    except Exception as e:
        logger.warning("Geolocalización de IP falló para %s: %s", ip, e)
    return None


def send_login_alert(email: str, nombre: str, ip: str, ua: str) -> None:
    """Notifica un login desde un dispositivo/IP no reconocido previamente
    (disparado por auth_routes.py::login solo cuando is_new_device es True,
    no en cada inicio de sesión)."""
    from datetime import datetime as _dt
    from urllib.parse import quote as _urlquote
    when = _dt.now().strftime("%d/%m/%Y %H:%M")
    device = _parse_device(ua)
    location = _geolocate_ip(ip) or "No disponible"
    # Los valores interpolados (when/device/ip) pueden traer espacios y
    # acentos -- deben ir URL-encoded o el body del mailto se corta/rompe
    # en varios clientes de correo apenas encuentran el primer espacio sin codificar.
    report_body = _urlquote(
        f"Detecté un inicio de sesión que no reconozco:\n"
        f"Fecha: {when}\nDispositivo: {device}\nIP: {ip}"
    )
    report_url = (
        "mailto:partnerships@labxperformanceapp.com"
        f"?subject={_urlquote('Acceso no autorizado a mi cuenta LabX')}"
        f"&body={report_body}"
    )
    inner = f"""
      <p style="margin:0 0 16px">Hola <strong>{nombre}</strong>,</p>
      <p style="color:#7FB3CC;margin:0 0 16px">Se registró un nuevo acceso a su cuenta en <strong style="color:#F0F9FF">LabX</strong> desde un dispositivo o ubicación que no reconocíamos.</p>

      <table style="width:100%;border-collapse:collapse;font-size:11pt;color:#7FB3CC;margin:0 0 20px;background:#060E1C;border-radius:8px;overflow:hidden">
        <tr><td style="padding:10px 14px;color:#F0F9FF;border-bottom:1px solid rgba(8,145,178,.15)">Fecha y hora</td><td style="padding:10px 14px;border-bottom:1px solid rgba(8,145,178,.15)">{when}</td></tr>
        <tr><td style="padding:10px 14px;color:#F0F9FF;border-bottom:1px solid rgba(8,145,178,.15)">Dispositivo</td><td style="padding:10px 14px;border-bottom:1px solid rgba(8,145,178,.15)">{device}</td></tr>
        <tr><td style="padding:10px 14px;color:#F0F9FF;border-bottom:1px solid rgba(8,145,178,.15)">Dirección IP</td><td style="padding:10px 14px;border-bottom:1px solid rgba(8,145,178,.15)">{ip}</td></tr>
        <tr><td style="padding:10px 14px;color:#F0F9FF">Ubicación estimada</td><td style="padding:10px 14px">{location}</td></tr>
      </table>

      <p style="color:#7FB3CC;margin:0 0 16px">Si fue usted quien inició esta sesión, puede ignorar este mensaje.</p>

      <div style="background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.3);border-radius:10px;padding:16px;text-align:center;margin-bottom:8px">
        <p style="color:#EF4444;font-weight:700;margin:0 0 12px">¿No fue usted?</p>
        <a href="{report_url}" style="display:inline-block;background:#EF4444;color:#fff;font-weight:800;font-size:12pt;text-decoration:none;padding:12px 28px;border-radius:10px">
          Reportar acceso no autorizado
        </a>
      </div>
    """
    send_email(email, "LabX — Nuevo inicio de sesión detectado en su cuenta", _wrap_email_body(inner), tags=["security", "login-alert"])
