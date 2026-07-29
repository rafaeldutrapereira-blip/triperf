"""
workout_delivery.py — Entrega automática de workouts a Garmin y Zwift.

Llamado desde assign_workout() al asignar un template de bicicleta con bloques.
No lanza excepciones hacia el caller — loguea errores y continúa.
"""
from __future__ import annotations
import json
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import AssignedWorkout, User, WorkoutTemplate

logger = logging.getLogger("labx.delivery")

APP_URL = os.getenv("APP_URL", "http://localhost:8000")

# Module-level imports so they can be patched in tests
from .mailer import send_email          # noqa: E402
from .crypto import decrypt_credential  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# ZWO GENERATION
# ─────────────────────────────────────────────────────────────────

def generate_zwo_bytes(blocks_json: str, name: str, date_iso: str = "") -> bytes:
    """Genera un archivo Zwift Workout (.zwo) a partir de blocks_json."""
    try:
        blocks = json.loads(blocks_json)
    except Exception:
        return b""

    def x(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        "<workout_file>",
        f"  <author>LabX Coach</author>",
        f"  <name>{x(name)}</name>",
        f"  <description>{x(date_iso)}</description>",
        "  <sportType>bike</sportType>",
        "  <tags/>",
        "  <workout>",
    ]

    for b in blocks:
        t = b.get("type", "steady")
        d = int(b.get("duration", 300))
        if t == "warmup":
            pl = float(b.get("power_low", 0.50))
            ph = float(b.get("power_high", 0.75))
            lines.append(f'    <Warmup Duration="{d}" PowerLow="{pl:.2f}" PowerHigh="{ph:.2f}"/>')
        elif t == "cooldown":
            pl = float(b.get("power_low", 0.40))
            ph = float(b.get("power_high", 0.75))
            lines.append(f'    <Cooldown Duration="{d}" PowerLow="{ph:.2f}" PowerHigh="{pl:.2f}"/>')
        elif t == "steady":
            pw = float(b.get("power", 0.75))
            lines.append(f'    <SteadyState Duration="{d}" Power="{pw:.2f}"/>')
        elif t == "intervals":
            rep   = int(b.get("repeat", 1))
            on_d  = int(b.get("on_duration", 240))
            off_d = int(b.get("off_duration", 120))
            on_p  = float(b.get("on_power", 0.95))
            off_p = float(b.get("off_power", 0.55))
            lines.append(
                f'    <IntervalsT Repeat="{rep}" OnDuration="{on_d}" OffDuration="{off_d}"'
                f' OnPower="{on_p:.2f}" OffPower="{off_p:.2f}" pace="0"/>'
            )
        elif t == "ramp":
            pl = float(b.get("power_low", 0.60))
            ph = float(b.get("power_high", 1.00))
            lines.append(f'    <Ramp Duration="{d}" PowerLow="{pl:.2f}" PowerHigh="{ph:.2f}"/>')
        elif t == "freeride":
            lines.append(f'    <FreeRide Duration="{d}" FlatRoad="0"/>')

    lines += ["  </workout>", "</workout_file>"]
    return "\n".join(lines).encode("utf-8")


def _safe_filename(name: str) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name or "workout").strip("_") or "workout"


# ─────────────────────────────────────────────────────────────────
# EMAIL DELIVERY (.zwo adjunto)
# ─────────────────────────────────────────────────────────────────

def send_zwo_email(athlete_email: str, athlete_name: str,
                   workout_name: str, date_iso: str,
                   zwo_bytes: bytes) -> bool:
    """Envía email al atleta con el .zwo adjunto."""

    fname    = f"{_safe_filename(workout_name)}_{date_iso}.zwo"
    app_url  = APP_URL

    # Calcular duración estimada del workout desde bytes
    dur_hint = ""
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(zwo_bytes.decode())
        total = 0
        workout_node = root.find("workout")
        for el in (workout_node if workout_node is not None else []):
            dur = int(el.get("Duration", 0) or 0)
            on  = int(el.get("OnDuration", 0) or 0)
            off = int(el.get("OffDuration", 0) or 0)
            rep = int(el.get("Repeat", 1) or 1)
            total += dur + (on + off) * rep
        if total:
            m = total // 60
            dur_hint = f" · {m} min"
    except Exception:
        pass

    html = f"""
    <div style="font-family:Inter,sans-serif;background:#04080F;color:#F0F9FF;
                padding:36px 24px;max-width:580px;margin:0 auto;border-radius:16px">
      <div style="text-align:center;margin-bottom:24px">
        <span style="font-size:2.2rem;font-weight:900;letter-spacing:-.02em">
          <span style="color:#F0F9FF">LAB</span><span style="color:#FF6535">X</span>
        </span>
      </div>

      <h1 style="font-size:1.25rem;font-weight:700;margin-bottom:4px">
        🚴 Entrenamiento indoor listo para Zwift
      </h1>
      <p style="color:#7FB3CC;margin-bottom:20px;font-size:.9rem">
        Hola <strong style="color:#F0F9FF">{athlete_name}</strong>, tu coach ha programado
        un entrenamiento estructurado para el <strong style="color:#FF6535">{date_iso}</strong>.
      </p>

      <div style="background:#08121E;border:1px solid rgba(255,101,53,.25);border-radius:12px;
                  padding:18px 20px;margin-bottom:24px">
        <div style="font-family:'Oswald',sans-serif;font-size:1.1rem;font-weight:700;
                    color:#FF6535;margin-bottom:4px">{workout_name}{dur_hint}</div>
        <div style="font-size:.8rem;color:#7FB3CC">Archivo adjunto: <code style="color:#22D3EE">{fname}</code></div>
      </div>

      <p style="font-size:.9rem;font-weight:600;color:#F0F9FF;margin-bottom:12px">
        Cómo cargar en Zwift (2 pasos):
      </p>
      <ol style="padding-left:20px;color:#7FB3CC;font-size:.85rem;margin-bottom:24px">
        <li style="margin-bottom:10px">
          <strong style="color:#F0F9FF">Guarda el archivo adjunto</strong> ({fname})
          en tu computador en:<br>
          <code style="background:#08121E;color:#22D3EE;padding:3px 8px;border-radius:4px;
                       font-size:.78rem;display:inline-block;margin-top:4px">
            Documentos\\Zwift\\Workouts\\
          </code>
        </li>
        <li style="margin-bottom:10px">
          <strong style="color:#F0F9FF">Abre Zwift</strong> → Training → My Workouts<br>
          <span style="font-size:.78rem">El workout aparece automáticamente. No necesitas reiniciar Zwift.</span>
        </li>
      </ol>

      <div style="text-align:center;margin-bottom:24px">
        <a href="{app_url}/training_plan.html"
           style="display:inline-block;background:#FF6535;color:#fff;font-weight:700;
                  font-size:.85rem;letter-spacing:.06em;text-transform:uppercase;
                  text-decoration:none;padding:12px 28px;border-radius:8px">
          Ver mi plan de entrenamiento →
        </a>
      </div>

      <p style="color:#3D6880;font-size:.72rem;text-align:center">
        LabX Coach Platform · Este mensaje fue generado automáticamente al asignar tu entrenamiento.
      </p>
    </div>
    """

    return send_email(
        to          = athlete_email,
        subject     = f"🚴 Zwift workout {date_iso}: {workout_name}",
        html        = html,
        tags        = ["workout", "zwift"],
        attachments = [{"filename": fname, "content": zwo_bytes}],
    )


# ─────────────────────────────────────────────────────────────────
# GARMIN AUTO-SYNC
# ─────────────────────────────────────────────────────────────────

def auto_garmin_sync(assignment, athlete: "User", tpl: "WorkoutTemplate") -> dict:
    """
    Sincroniza automáticamente a Garmin Connect si el atleta tiene credenciales.
    Retorna {"ok": bool, "skipped": bool, "error": str|None}
    """
    if not athlete.garmin_email or not athlete.garmin_password:
        logger.debug("Garmin skip: atleta %s sin credenciales", athlete.id)
        return {"ok": False, "skipped": True, "error": None}

    session_dict = {
        "name":    tpl.nombre,
        "sport":   tpl.sport,
        "dur_min": tpl.dur_min,
        "dist_km": tpl.dist_km,
        "notes":   tpl.notas or (assignment.notas or ""),
    }
    try:
        from garmin_connector import schedule_workout_for_athlete
        result = schedule_workout_for_athlete(
            session          = session_dict,
            target_date      = assignment.date_iso,
            athlete_id       = athlete.id,
            athlete_email    = athlete.garmin_email,
            athlete_password = decrypt_credential(athlete.garmin_password),
        )
        logger.info("Garmin auto-sync OK: atleta=%s date=%s workout_id=%s",
                    athlete.id, assignment.date_iso, result.get("workoutId"))
        return {"ok": True, "skipped": False, "error": None}
    except Exception as e:
        logger.warning("Garmin auto-sync FAIL: atleta=%s error=%s", athlete.id, e)
        return {"ok": False, "skipped": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT — llamado desde assign_workout()
# ─────────────────────────────────────────────────────────────────

def deliver_bike_workout(assignment, athlete: "User", tpl: "WorkoutTemplate") -> dict:
    """
    Entrega automática completa para un workout de bicicleta con bloques.
    Ejecutar en background (threading) para no bloquear la respuesta HTTP.

    Retorna resumen {"email_sent": bool, "garmin_ok": bool, "garmin_skipped": bool}
    """
    result = {"email_sent": False, "garmin_ok": False, "garmin_skipped": False}

    # 1. Zwift email
    if tpl.blocks_json and athlete.email:
        try:
            zwo = generate_zwo_bytes(tpl.blocks_json, tpl.nombre, assignment.date_iso)
            if zwo:
                result["email_sent"] = send_zwo_email(
                    athlete_email  = athlete.email,
                    athlete_name   = athlete.nombre,
                    workout_name   = tpl.nombre,
                    date_iso       = assignment.date_iso,
                    zwo_bytes      = zwo,
                )
        except Exception as e:
            logger.error("deliver_bike_workout email error: %s", e)

    # 2. Garmin sync
    try:
        g = auto_garmin_sync(assignment, athlete, tpl)
        result["garmin_ok"]      = g["ok"]
        result["garmin_skipped"] = g.get("skipped", False)
    except Exception as e:
        logger.error("deliver_bike_workout garmin error: %s", e)

    logger.info(
        "deliver_bike_workout done: athlete=%s date=%s email=%s garmin_ok=%s garmin_skip=%s",
        athlete.id, assignment.date_iso,
        result["email_sent"], result["garmin_ok"], result["garmin_skipped"],
    )
    return result
