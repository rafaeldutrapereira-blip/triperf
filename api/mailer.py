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

_FROM = os.getenv("EMAIL_FROM", "LabX <partnerships@labxperformanceapp.com>")

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


_WELCOME_TXT = {
    "es": dict(
        subject="Bienvenido a LabX — Su plataforma de rendimiento ya está lista",
        greeting="Estimado/a",
        intro1="En nombre de todo el equipo de <strong style=\"color:#F0F9FF\">LabX</strong>, le damos la más cordial bienvenida y le agradecemos la confianza depositada en nuestra plataforma.",
        intro2="LabX es una plataforma de entrenamiento diseñada para deportistas de resistencia — running, ciclismo, natación y triatlón. Sincronizamos sus datos reales de dispositivos como Garmin y Strava para calcular su carga de entrenamiento (CTL/ATL/TSB), su estado de recuperación diario, y ofrecerle herramientas como nuestro Predictor de Carrera y un Coach con inteligencia artificial, para acompañarle en cada etapa de su preparación.",
        access_title="Acceso a la plataforma",
        access_web_label="Plataforma web:",
        access_web="ingrese en",
        access_web_suffix="con su correo y contraseña registrados.",
        access_mobile_label="Aplicación móvil:",
        access_mobile="LabX está disponible como aplicación web progresiva — desde su celular, abra el sitio en su navegador y seleccione \"Agregar a pantalla de inicio\" para instalarla como una app.",
        steps_title="Primeros pasos recomendados",
        step1="Complete su perfil — datos personales, objetivos deportivos y parámetros de entrenamiento (FTP, umbrales).",
        step2="Conecte su dispositivo (Garmin o Strava) para que su carga de entrenamiento se calcule automáticamente con datos reales.",
        step3="Explore su Dashboard y defina su próximo objetivo de carrera en el Predictor.",
        cta="Acceder a mi cuenta →",
        help_title="¿Necesita ayuda?",
        help_body="Ante cualquier consulta, escríbanos a",
        help_suffix="— con gusto le asistiremos.",
        closing="Quedamos atentos a acompañarle en esta nueva etapa.",
    ),
    "pt": dict(
        subject="Bem-vindo ao LabX — Sua plataforma de performance já está pronta",
        greeting="Prezado(a)",
        intro1="Em nome de toda a equipe do <strong style=\"color:#F0F9FF\">LabX</strong>, damos as boas-vindas e agradecemos a confiança depositada em nossa plataforma.",
        intro2="O LabX é uma plataforma de treino desenhada para atletas de resistência — corrida, ciclismo, natação e triatlo. Sincronizamos seus dados reais de dispositivos como Garmin e Strava para calcular sua carga de treino (CTL/ATL/TSB), seu estado de recuperação diário, e oferecer ferramentas como nosso Preditor de Prova e um Coach com inteligência artificial, para acompanhá-lo em cada etapa da sua preparação.",
        access_title="Acesso à plataforma",
        access_web_label="Plataforma web:",
        access_web="acesse em",
        access_web_suffix="com seu email e senha cadastrados.",
        access_mobile_label="Aplicativo móvel:",
        access_mobile="O LabX está disponível como aplicativo web progressivo — pelo celular, abra o site no navegador e selecione \"Adicionar à tela inicial\" para instalá-lo como um app.",
        steps_title="Primeiros passos recomendados",
        step1="Complete seu perfil — dados pessoais, objetivos esportivos e parâmetros de treino (FTP, limiares).",
        step2="Conecte seu dispositivo (Garmin ou Strava) para que sua carga de treino seja calculada automaticamente com dados reais.",
        step3="Explore seu Dashboard e defina seu próximo objetivo de prova no Preditor.",
        cta="Acessar minha conta →",
        help_title="Precisa de ajuda?",
        help_body="Para qualquer dúvida, escreva para",
        help_suffix="— teremos prazer em ajudar.",
        closing="Estamos à disposição para acompanhá-lo nesta nova etapa.",
    ),
    "en": dict(
        subject="Welcome to LabX — Your performance platform is ready",
        greeting="Dear",
        intro1="On behalf of the entire <strong style=\"color:#F0F9FF\">LabX</strong> team, we warmly welcome you and thank you for your trust in our platform.",
        intro2="LabX is a training platform designed for endurance athletes — running, cycling, swimming and triathlon. We sync your real data from devices like Garmin and Strava to calculate your training load (CTL/ATL/TSB), your daily recovery status, and offer tools like our Race Predictor and an AI Coach, to support you at every stage of your preparation.",
        access_title="Accessing the platform",
        access_web_label="Web platform:",
        access_web="sign in at",
        access_web_suffix="with your registered email and password.",
        access_mobile_label="Mobile app:",
        access_mobile="LabX is available as a progressive web app — from your phone, open the site in your browser and select \"Add to Home Screen\" to install it as an app.",
        steps_title="Recommended first steps",
        step1="Complete your profile — personal data, sport goals and training parameters (FTP, thresholds).",
        step2="Connect your device (Garmin or Strava) so your training load is calculated automatically from real data.",
        step3="Explore your Dashboard and set your next race goal in the Predictor.",
        cta="Access my account →",
        help_title="Need help?",
        help_body="For any question, write to us at",
        help_suffix="— we'll be happy to help.",
        closing="We look forward to being part of this new stage with you.",
    ),
}


def send_welcome(email: str, nombre: str, app_url: str = "", lang: str = "es") -> None:
    """Correo de bienvenida institucional (2026-08-22, pedido explícito del
    usuario -- tono formal/corporativo en vez del casual con emojis que
    tenía antes). No se linkea a App Store/Google Play: la app nativa
    (Capacitor, Sprint 55) todavía no está compilada ni publicada en
    ninguna tienda -- se indica instalación PWA real, que sí funciona hoy."""
    app_url = app_url or os.getenv("APP_URL", "http://localhost:8000")
    t = _WELCOME_TXT.get(lang, _WELCOME_TXT["es"])
    inner = f"""
      <p style="margin:0 0 16px">{t['greeting']} <strong>{nombre}</strong>,</p>
      <p style="color:#7FB3CC;margin:0 0 16px">{t['intro1']}</p>
      <p style="color:#7FB3CC;margin:0 0 20px">{t['intro2']}</p>

      <p style="margin:0 0 6px"><strong>{t['access_title']}</strong></p>
      <ul style="padding-left:20px;color:#7FB3CC;margin:0 0 20px">
        <li style="margin-bottom:8px"><strong style="color:#F0F9FF">{t['access_web_label']}</strong> {t['access_web']} <a href="{app_url}" style="color:#0EA5E9">{app_url}</a> {t['access_web_suffix']}</li>
        <li style="margin-bottom:8px"><strong style="color:#F0F9FF">{t['access_mobile_label']}</strong> {t['access_mobile']}</li>
      </ul>

      <p style="margin:0 0 6px"><strong>{t['steps_title']}</strong></p>
      <ol style="padding-left:20px;color:#7FB3CC;margin:0 0 20px">
        <li style="margin-bottom:8px">{t['step1']}</li>
        <li style="margin-bottom:8px">{t['step2']}</li>
        <li style="margin-bottom:8px">{t['step3']}</li>
      </ol>

      <div style="text-align:center;margin-bottom:20px">
        <a href="{app_url}/onboarding.html" style="display:inline-block;background:linear-gradient(135deg,#FF6535,#E8490A);color:#fff;font-weight:800;font-size:13pt;letter-spacing:1px;text-transform:uppercase;text-decoration:none;padding:14px 32px;border-radius:10px">
          {t['cta']}
        </a>
      </div>

      <p style="margin:0 0 6px"><strong>{t['help_title']}</strong></p>
      <p style="color:#7FB3CC;margin:0 0 16px">{t['help_body']} <a href="mailto:partnerships@labxperformanceapp.com" style="color:#0EA5E9">partnerships@labxperformanceapp.com</a> {t['help_suffix']}</p>

      <p style="color:#7FB3CC;margin:0">{t['closing']}</p>
    """
    send_email(email, t["subject"], _wrap_email_body(inner), tags=["welcome"])


_DAY3_TXT = {
    "es": dict(
        subject_fmt="{nombre}, desbloquea tu potencial completo en LabX 🚀",
        title_fmt="Hola {nombre}, ¿cómo va el entrenamiento? 💪",
        intro="Llevas 3 días con LabX. ¿Sabías que con el plan <strong style=\"color:#FF6535\">Pro</strong> puedes:",
        f1="📈 Ver tu curva de fitness PMC (ATL / CTL / TSB) completa",
        f2="🔄 Sync automático con Garmin Connect",
        f3="🏁 Predecir tiempos en Ironman, 70.3 y Olímpico",
        f4="🧬 Análisis de laboratorio y planes de nutrición",
        cta="Actualizar a Pro — $19/mes →",
    ),
    "pt": dict(
        subject_fmt="{nombre}, desbloqueie todo o seu potencial no LabX 🚀",
        title_fmt="Olá {nombre}, como está indo o treino? 💪",
        intro="Você já tem 3 dias com o LabX. Sabia que com o plano <strong style=\"color:#FF6535\">Pro</strong> você pode:",
        f1="📈 Ver sua curva de fitness PMC (ATL / CTL / TSB) completa",
        f2="🔄 Sincronização automática com Garmin Connect",
        f3="🏁 Prever tempos no Ironman, 70.3 e Olímpico",
        f4="🧬 Análises laboratoriais e planos de nutrição",
        cta="Fazer upgrade para Pro — $19/mês →",
    ),
    "en": dict(
        subject_fmt="{nombre}, unlock your full potential on LabX 🚀",
        title_fmt="Hi {nombre}, how's training going? 💪",
        intro="You've been with LabX for 3 days. Did you know that with the <strong style=\"color:#FF6535\">Pro</strong> plan you can:",
        f1="📈 See your full PMC fitness curve (ATL / CTL / TSB)",
        f2="🔄 Automatic sync with Garmin Connect",
        f3="🏁 Predict times for Ironman, 70.3 and Olympic distance",
        f4="🧬 Lab analysis and nutrition plans",
        cta="Upgrade to Pro — $19/mo →",
    ),
}


def send_day3_drip(email: str, nombre: str, app_url: str = "", lang: str = "es") -> None:
    app_url = app_url or os.getenv("APP_URL", "http://localhost:8000")
    t = _DAY3_TXT.get(lang, _DAY3_TXT["es"])
    inner = f"""
      <h1 style="font-size:17px;margin:0 0 8px">{t['title_fmt'].format(nombre=nombre)}</h1>
      <p style="color:#7FB3CC;margin:0 0 16px">{t['intro']}</p>
      <ul style="padding-left:20px;color:#7FB3CC;margin:0 0 20px">
        <li style="margin-bottom:8px">{t['f1']}</li>
        <li style="margin-bottom:8px">{t['f2']}</li>
        <li style="margin-bottom:8px">{t['f3']}</li>
        <li style="margin-bottom:8px">{t['f4']}</li>
      </ul>
      <div style="text-align:center;margin-bottom:8px">
        <a href="{app_url}/dashboard.html?upgrade=1" style="display:inline-block;background:linear-gradient(135deg,#A855F7,#7C3AED);color:#fff;font-weight:800;font-size:13pt;letter-spacing:1px;text-transform:uppercase;text-decoration:none;padding:14px 32px;border-radius:10px">
          {t['cta']}
        </a>
      </div>
    """
    send_email(email, t["subject_fmt"].format(nombre=nombre), _wrap_email_body(inner), tags=["drip", "day3"])


_DAY7_TXT = {
    "es": dict(
        subject_fmt="Una semana con LabX — ¿tienes coach, {nombre}? 🧑‍💼",
        title_fmt="¡Una semana entrenando con LabX, {nombre}! 🎯",
        intro1="¿Tienes un coach que te guía? Con LabX <strong style=\"color:#F0A500\">Coach Platform</strong> puedes gestionar hasta 50+ atletas, asignar sesiones y ver reportes en tiempo real.",
        intro2="¿O prefieres tener un coach que te asesore? Contáctanos y te conectamos.",
        cta="Quiero saber más →",
        unsub="Cancelar suscripción a estos emails",
    ),
    "pt": dict(
        subject_fmt="Uma semana com o LabX — você tem coach, {nombre}? 🧑‍💼",
        title_fmt="Uma semana treinando com o LabX, {nombre}! 🎯",
        intro1="Você tem um coach que te orienta? Com o LabX <strong style=\"color:#F0A500\">Coach Platform</strong> você pode gerenciar até 50+ atletas, atribuir sessões e ver relatórios em tempo real.",
        intro2="Ou prefere ter um coach que te oriente? Entre em contato e nós te conectamos.",
        cta="Quero saber mais →",
        unsub="Cancelar inscrição nestes emails",
    ),
    "en": dict(
        subject_fmt="One week with LabX — do you have a coach, {nombre}? 🧑‍💼",
        title_fmt="One week training with LabX, {nombre}! 🎯",
        intro1="Do you have a coach guiding you? With LabX <strong style=\"color:#F0A500\">Coach Platform</strong> you can manage up to 50+ athletes, assign sessions and see real-time reports.",
        intro2="Or would you rather have a coach advising you? Contact us and we'll connect you.",
        cta="I want to know more →",
        unsub="Unsubscribe from these emails",
    ),
}


def send_day7_drip(email: str, nombre: str, app_url: str = "", lang: str = "es") -> None:
    app_url = app_url or os.getenv("APP_URL", "http://localhost:8000")
    t = _DAY7_TXT.get(lang, _DAY7_TXT["es"])
    inner = f"""
      <h1 style="font-size:17px;margin:0 0 8px">{t['title_fmt'].format(nombre=nombre)}</h1>
      <p style="color:#7FB3CC;margin:0 0 16px">{t['intro1']}</p>
      <p style="color:#7FB3CC;margin:0 0 20px">{t['intro2']}</p>
      <div style="text-align:center;margin-bottom:8px">
        <a href="{app_url}/landing.html#contact" style="display:inline-block;background:linear-gradient(135deg,#F0A500,#FF6535);color:#000;font-weight:800;font-size:13pt;letter-spacing:1px;text-transform:uppercase;text-decoration:none;padding:14px 32px;border-radius:10px">
          {t['cta']}
        </a>
      </div>
      <p style="text-align:center;margin:12px 0 0"><a href="{app_url}/unsubscribe" style="color:#3D6880;font-size:10pt">{t['unsub']}</a></p>
    """
    send_email(email, t["subject_fmt"].format(nombre=nombre), _wrap_email_body(inner), tags=["drip", "day7"])


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


_LOGIN_ALERT_TXT = {
    "es": dict(
        subject="LabX — Nuevo inicio de sesión detectado en su cuenta",
        greeting="Hola",
        intro="Se registró un nuevo acceso a su cuenta en <strong style=\"color:#F0F9FF\">LabX</strong> desde un dispositivo o ubicación que no reconocíamos.",
        row_datetime="Fecha y hora", row_device="Dispositivo", row_ip="Dirección IP", row_location="Ubicación estimada",
        no_data="No disponible",
        was_you="Si fue usted quien inició esta sesión, puede ignorar este mensaje.",
        not_you_title="¿No fue usted?",
        report_btn="Reportar acceso no autorizado",
        report_subject="Acceso no autorizado a mi cuenta LabX",
        report_body="Detecté un inicio de sesión que no reconozco:\nFecha: {when}\nDispositivo: {device}\nIP: {ip}",
    ),
    "pt": dict(
        subject="LabX — Novo login detectado na sua conta",
        greeting="Olá",
        intro="Foi registrado um novo acesso à sua conta no <strong style=\"color:#F0F9FF\">LabX</strong> a partir de um dispositivo ou local que não reconhecíamos.",
        row_datetime="Data e hora", row_device="Dispositivo", row_ip="Endereço IP", row_location="Localização estimada",
        no_data="Não disponível",
        was_you="Se foi você quem iniciou esta sessão, pode ignorar esta mensagem.",
        not_you_title="Não foi você?",
        report_btn="Reportar acesso não autorizado",
        report_subject="Acesso não autorizado à minha conta LabX",
        report_body="Detectei um login que não reconheço:\nData: {when}\nDispositivo: {device}\nIP: {ip}",
    ),
    "en": dict(
        subject="LabX — New sign-in detected on your account",
        greeting="Hi",
        intro="A new sign-in to your <strong style=\"color:#F0F9FF\">LabX</strong> account was detected from a device or location we didn't recognize.",
        row_datetime="Date and time", row_device="Device", row_ip="IP address", row_location="Estimated location",
        no_data="Not available",
        was_you="If this was you, you can ignore this message.",
        not_you_title="Wasn't you?",
        report_btn="Report unauthorized access",
        report_subject="Unauthorized access to my LabX account",
        report_body="I detected a sign-in I don't recognize:\nDate: {when}\nDevice: {device}\nIP: {ip}",
    ),
}


def send_login_alert(email: str, nombre: str, ip: str, ua: str, lang: str = "es") -> None:
    """Notifica un login desde un dispositivo/IP no reconocido previamente
    (disparado por auth_routes.py::login solo cuando is_new_device es True,
    no en cada inicio de sesión)."""
    from datetime import datetime as _dt
    from urllib.parse import quote as _urlquote
    t = _LOGIN_ALERT_TXT.get(lang, _LOGIN_ALERT_TXT["es"])
    when = _dt.now().strftime("%d/%m/%Y %H:%M")
    device = _parse_device(ua)
    location = _geolocate_ip(ip) or t["no_data"]
    # Los valores interpolados (when/device/ip) pueden traer espacios y
    # acentos -- deben ir URL-encoded o el body del mailto se corta/rompe
    # en varios clientes de correo apenas encuentran el primer espacio sin codificar.
    report_body = _urlquote(t["report_body"].format(when=when, device=device, ip=ip))
    report_url = (
        "mailto:partnerships@labxperformanceapp.com"
        f"?subject={_urlquote(t['report_subject'])}"
        f"&body={report_body}"
    )
    inner = f"""
      <p style="margin:0 0 16px">{t['greeting']} <strong>{nombre}</strong>,</p>
      <p style="color:#7FB3CC;margin:0 0 16px">{t['intro']}</p>

      <table style="width:100%;border-collapse:collapse;font-size:11pt;color:#7FB3CC;margin:0 0 20px;background:#060E1C;border-radius:8px;overflow:hidden">
        <tr><td style="padding:10px 14px;color:#F0F9FF;border-bottom:1px solid rgba(8,145,178,.15)">{t['row_datetime']}</td><td style="padding:10px 14px;border-bottom:1px solid rgba(8,145,178,.15)">{when}</td></tr>
        <tr><td style="padding:10px 14px;color:#F0F9FF;border-bottom:1px solid rgba(8,145,178,.15)">{t['row_device']}</td><td style="padding:10px 14px;border-bottom:1px solid rgba(8,145,178,.15)">{device}</td></tr>
        <tr><td style="padding:10px 14px;color:#F0F9FF;border-bottom:1px solid rgba(8,145,178,.15)">{t['row_ip']}</td><td style="padding:10px 14px;border-bottom:1px solid rgba(8,145,178,.15)">{ip}</td></tr>
        <tr><td style="padding:10px 14px;color:#F0F9FF">{t['row_location']}</td><td style="padding:10px 14px">{location}</td></tr>
      </table>

      <p style="color:#7FB3CC;margin:0 0 16px">{t['was_you']}</p>

      <div style="background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.3);border-radius:10px;padding:16px;text-align:center;margin-bottom:8px">
        <p style="color:#EF4444;font-weight:700;margin:0 0 12px">{t['not_you_title']}</p>
        <a href="{report_url}" style="display:inline-block;background:#EF4444;color:#fff;font-weight:800;font-size:12pt;text-decoration:none;padding:12px 28px;border-radius:10px">
          {t['report_btn']}
        </a>
      </div>
    """
    send_email(email, t["subject"], _wrap_email_body(inner), tags=["security", "login-alert"])


# ─────────────────────────────────────────────────────────────────────────────
# ALERTA DE VIDA ÚTIL DE EQUIPAMIENTO (Sprint 4 — Gestión de Equipamiento)
# ─────────────────────────────────────────────────────────────────────────────

_GEAR_ALERT_TXT = {
    "es": dict(
        title_100="{icon} {label} llegó al 100% de su vida útil",
        title_pct="{icon} {label} está al {pct:.0f}% de su vida útil",
        msg_100="Ya cumplió el kilometraje recomendado por el fabricante. Seguir usándolo aumenta el riesgo de lesión o falla del componente.",
        msg_pct="Se acerca al kilometraje recomendado por el fabricante. Es un buen momento para planear su reemplazo.",
        greeting_fmt="Hola {nombre},",
        cta="Ver mi equipo",
    ),
    "pt": dict(
        title_100="{icon} {label} chegou a 100% da sua vida útil",
        title_pct="{icon} {label} está em {pct:.0f}% da sua vida útil",
        msg_100="Já atingiu a quilometragem recomendada pelo fabricante. Continuar usando aumenta o risco de lesão ou falha do componente.",
        msg_pct="Está se aproximando da quilometragem recomendada pelo fabricante. É um bom momento para planejar a substituição.",
        greeting_fmt="Olá {nombre},",
        cta="Ver meu equipamento",
    ),
    "en": dict(
        title_100="{icon} {label} reached 100% of its useful life",
        title_pct="{icon} {label} is at {pct:.0f}% of its useful life",
        msg_100="It has already reached the mileage recommended by the manufacturer. Continuing to use it increases the risk of injury or component failure.",
        msg_pct="It's approaching the mileage recommended by the manufacturer. A good time to plan its replacement.",
        greeting_fmt="Hi {nombre},",
        cta="View my gear",
    ),
}


def send_gear_alert(email: str, nombre: str, gear_label: str, gear_kind: str,
                     life_pct: float, threshold: int, app_url: str = "", lang: str = "es") -> None:
    """gear_kind: 'shoe' | 'component'. threshold: 80 o 100 (% de vida útil)."""
    app_url = app_url or os.getenv("APP_URL", "http://localhost:8000")
    t = _GEAR_ALERT_TXT.get(lang, _GEAR_ALERT_TXT["es"])
    icon = "👟" if gear_kind == "shoe" else "🚲"
    if threshold >= 100:
        color = "#EF4444"
        title = t["title_100"].format(icon=icon, label=gear_label)
        message = t["msg_100"]
    else:
        color = "#F0A500"
        title = t["title_pct"].format(icon=icon, label=gear_label, pct=life_pct)
        message = t["msg_pct"]
    inner = f"""
      <h1 style="font-size:16px;margin:0 0 8px;color:{color}">{title}</h1>
      <p style="color:#7FB3CC;margin:0 0 20px">{t['greeting_fmt'].format(nombre=nombre)} {message}</p>
      <a href="{app_url}/gear.html" style="display:inline-block;background:{color};color:#fff;font-weight:800;font-size:12pt;text-decoration:none;padding:12px 28px;border-radius:10px">
        {t['cta']}
      </a>
    """
    send_email(email, title, _wrap_email_body(inner), tags=["gear", f"threshold-{threshold}"])
