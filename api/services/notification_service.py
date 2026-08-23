"""
S14 — Notification Service: email templates + push unificado.
Centraliza el envío de notificaciones para evitar duplicación en rutas.
"""
from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger("labx.notifications")


# ─── Email Templates ──────────────────────────────────────────

def _base_email(content_html: str) -> str:
    """Wrapper HTML base para todos los emails de LabX."""
    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LabX</title></head>
<body style="margin:0;padding:0;background:#04080F;font-family:Inter,Arial,sans-serif">
  <div style="max-width:560px;margin:0 auto;padding:40px 24px">
    <div style="text-align:center;margin-bottom:32px">
      <span style="font-size:28px;font-weight:800;letter-spacing:-1px;color:#F0F9FF">Lab</span>
      <span style="font-size:28px;font-weight:800;color:#FF6535">X</span>
    </div>
    {content_html}
    <div style="margin-top:40px;text-align:center;color:#3D6880;font-size:.75rem">
      © {date.today().year} LabX ·
      <a href="{{{{APP_URL}}}}/privacy.html" style="color:#3D6880">Privacidad</a> ·
      <a href="{{{{APP_URL}}}}/unsubscribe.html" style="color:#3D6880">Cancelar suscripción</a>
    </div>
  </div>
</body>
</html>"""


def email_workout_assigned(athlete_name: str, workout_name: str, date_iso: str,
                           coach_name: str, notas: str = "") -> tuple[str, str]:
    """Subject + HTML para notificación de entrenamiento asignado."""
    subject = f"Nuevo entrenamiento: {workout_name}"
    body = f"""
    <div style="background:#08121E;border-radius:16px;padding:32px;border:1px solid rgba(14,165,233,.12)">
      <h2 style="color:#F0F9FF;margin:0 0 8px">Tienes un nuevo entrenamiento 🏋️</h2>
      <p style="color:#7FB3CC;margin:0 0 24px">Hola <strong>{athlete_name}</strong>,
        tu coach <strong>{coach_name}</strong> te asignó:</p>
      <div style="background:#0A1929;border-radius:12px;padding:20px;margin-bottom:20px">
        <div style="color:#FF6535;font-size:1.1rem;font-weight:700;margin-bottom:8px">{workout_name}</div>
        <div style="color:#7FB3CC;font-size:.9rem">📅 Fecha: <strong style="color:#F0F9FF">{date_iso}</strong></div>
        {f'<div style="color:#7FB3CC;font-size:.9rem;margin-top:8px">📝 {notas}</div>' if notas else ''}
      </div>
      <a href="{{{{APP_URL}}}}/dashboard.html" style="display:inline-block;background:#FF6535;color:white;
         padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600">Ver entrenamiento</a>
    </div>
    """
    return subject, _base_email(body)


def email_weekly_summary(athlete_name: str, week_data: dict) -> tuple[str, str]:
    """Resumen semanal de entrenamiento para el atleta."""
    subject = f"Tu resumen semanal LabX — {date.today().strftime('%d %b %Y')}"
    swim = week_data.get("swim_km", 0)
    bike = week_data.get("bike_km", 0)
    run  = week_data.get("run_km",  0)
    tss  = week_data.get("tss_week", 0)
    ctl  = week_data.get("ctl", 0)

    body = f"""
    <div style="background:#08121E;border-radius:16px;padding:32px;border:1px solid rgba(14,165,233,.12)">
      <h2 style="color:#F0F9FF;margin:0 0 8px">Tu semana en LabX 📊</h2>
      <p style="color:#7FB3CC">Hola <strong>{athlete_name}</strong>, así fue tu semana:</p>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:20px 0">
        <div style="background:#0A1929;border-radius:10px;padding:16px;text-align:center">
          <div style="font-size:1.4rem">🏊</div>
          <div style="color:#F0F9FF;font-size:1.1rem;font-weight:700">{swim:.1f} km</div>
          <div style="color:#3D6880;font-size:.75rem">Natación</div>
        </div>
        <div style="background:#0A1929;border-radius:10px;padding:16px;text-align:center">
          <div style="font-size:1.4rem">🚴</div>
          <div style="color:#F0F9FF;font-size:1.1rem;font-weight:700">{bike:.1f} km</div>
          <div style="color:#3D6880;font-size:.75rem">Ciclismo</div>
        </div>
        <div style="background:#0A1929;border-radius:10px;padding:16px;text-align:center">
          <div style="font-size:1.4rem">🏃</div>
          <div style="color:#F0F9FF;font-size:1.1rem;font-weight:700">{run:.1f} km</div>
          <div style="color:#3D6880;font-size:.75rem">Carrera</div>
        </div>
        <div style="background:#0A1929;border-radius:10px;padding:16px;text-align:center">
          <div style="font-size:1.4rem">⚡</div>
          <div style="color:#F0F9FF;font-size:1.1rem;font-weight:700">{tss:.0f} TSS</div>
          <div style="color:#3D6880;font-size:.75rem">Carga (CTL: {ctl:.0f})</div>
        </div>
      </div>
      <a href="{{{{APP_URL}}}}/dashboard.html" style="display:inline-block;background:#FF6535;color:white;
         padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600">Ver dashboard</a>
    </div>
    """
    return subject, _base_email(body)


def email_wellness_reminder(athlete_name: str) -> tuple[str, str]:
    """Recordatorio diario para registrar wellness."""
    subject = "Registra tu bienestar de hoy 💤"
    body = f"""
    <div style="background:#08121E;border-radius:16px;padding:32px;border:1px solid rgba(14,165,233,.12)">
      <h2 style="color:#F0F9FF;margin:0 0 8px">¿Cómo te sientes hoy?</h2>
      <p style="color:#7FB3CC">Hola <strong>{athlete_name}</strong>, tomarte 30 segundos para registrar
        tu bienestar ayuda a tu coach a optimizar tu plan de entrenamiento.</p>
      <p style="color:#7FB3CC">Registra: fatiga, sueño, dolor muscular y estado de ánimo.</p>
      <a href="{{{{APP_URL}}}}/dashboard.html#wellness" style="display:inline-block;background:#0EA5E9;
         color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600">
        Registrar ahora</a>
    </div>
    """
    return subject, _base_email(body)


def email_overtraining_alert(athlete_name: str, tsb: float, acwr: float,
                              coach_name: str = None) -> tuple[str, str]:
    """Alerta de sobreentrenamiento."""
    subject = "⚠️ Alerta de carga excesiva — LabX"
    coach_note = f"Tu coach <strong>{coach_name}</strong> ha sido notificado." if coach_name else ""
    body = f"""
    <div style="background:#08121E;border-radius:16px;padding:32px;border:1px solid rgba(239,68,68,.3)">
      <h2 style="color:#EF4444;margin:0 0 8px">⚠️ Carga de entrenamiento elevada</h2>
      <p style="color:#7FB3CC">Hola <strong>{athlete_name}</strong>, tus métricas indican riesgo:</p>
      <div style="background:#0A1929;border-radius:10px;padding:16px;margin:16px 0">
        <div style="color:#EF4444;font-size:.9rem">TSB: <strong>{tsb:.0f}</strong>
          (recomendado: > -15)</div>
        <div style="color:#F0A500;font-size:.9rem;margin-top:8px">ACWR: <strong>{acwr:.2f}</strong>
          (zona segura: 0.8–1.3)</div>
      </div>
      <p style="color:#7FB3CC">Recomendación: reduce volumen e intensidad esta semana. {coach_note}</p>
      <a href="{{{{APP_URL}}}}/dashboard.html" style="display:inline-block;background:#EF4444;color:white;
         padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600">Ver dashboard</a>
    </div>
    """
    return subject, _base_email(body)


# ─── Push notification payloads ───────────────────────────────

def push_workout_assigned(workout_name: str, date_iso: str) -> dict:
    return {
        "type":  "workout_assigned",
        "title": "Nuevo entrenamiento asignado",
        "body":  f"{workout_name} · {date_iso}",
        "url":   "/dashboard.html#plan",
        "icon":  "/icons/icon-192.png",
        "badge": "/icons/badge-72.png",
    }


def push_garmin_sync_done(activities: int) -> dict:
    return {
        "type":  "garmin_sync_done",
        "title": "Sincronización Garmin completada",
        "body":  f"{activities} actividades importadas.",
        "url":   "/dashboard.html",
        "icon":  "/icons/icon-192.png",
    }


def push_wellness_reminder() -> dict:
    return {
        "type":  "wellness_reminder",
        "title": "Registra tu bienestar de hoy",
        "body":  "Fatiga, sueño, dolor y estado de ánimo — 30 segundos.",
        "url":   "/dashboard.html#wellness",
        "icon":  "/icons/icon-192.png",
        "tag":   "wellness-daily",  # reemplaza notif anterior del mismo día
    }


def push_overtraining_alert(tsb: float) -> dict:
    return {
        "type":  "overtraining_alert",
        "title": "⚠️ Carga elevada detectada",
        "body":  f"TSB {tsb:.0f} — considera reducir volumen.",
        "url":   "/dashboard.html",
        "icon":  "/icons/icon-192.png",
        "requireInteraction": True,
    }


def push_gear_alert(gear_label: str, gear_kind: str, life_pct: float, threshold: int) -> dict:
    icon = "👟" if gear_kind == "shoe" else "🚲"
    if threshold >= 100:
        title = f"{icon} {gear_label} llegó al 100%"
        body  = "Cumplió su vida útil recomendada — es momento de reemplazarlo."
    else:
        title = f"{icon} {gear_label} al {life_pct:.0f}%"
        body  = "Se acerca a su vida útil recomendada."
    return {
        "type":  "gear_alert",
        "title": title,
        "body":  body,
        "url":   "/gear.html",
        "icon":  "/icons/icon-192.png",
        "tag":   f"gear-{gear_kind}-{threshold}",
    }
