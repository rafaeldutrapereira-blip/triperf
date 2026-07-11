"""
LabX — Importación de archivos .fit y .tcx
Permite cargar actividades manualmente sin Garmin Connect.
"""
from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, GarminActivity
from ..auth import get_current_user

logger = logging.getLogger("labx.import")
router = APIRouter(prefix="/import", tags=["import"])

_MAX_FILE_MB = 10
_MAX_FILE_BYTES = _MAX_FILE_MB * 1024 * 1024


def _parse_tcx(content: bytes) -> dict:
    """Parsea un archivo TCX y extrae métricas básicas."""
    import xml.etree.ElementTree as ET
    ns = {"t": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}
    root = ET.fromstring(content)

    activity = root.find(".//t:Activity", ns)
    if activity is None:
        raise ValueError("Archivo TCX sin actividad")

    sport = activity.get("Sport", "Other")

    # Tiempo inicio
    start_el = activity.find(".//t:Id", ns)
    start_time = None
    if start_el is not None and start_el.text:
        try:
            start_time = datetime.fromisoformat(start_el.text.replace("Z", "+00:00"))
        except Exception:
            pass

    # Trackpoints: distancia, FC, tiempo total
    trackpoints = activity.findall(".//t:Trackpoint", ns)
    distances = []
    hr_values = []
    times     = []

    for tp in trackpoints:
        dist_el = tp.find("t:DistanceMeters", ns)
        hr_el   = tp.find(".//t:Value", ns)
        time_el = tp.find("t:Time", ns)
        if dist_el is not None and dist_el.text:
            try: distances.append(float(dist_el.text))
            except: pass
        if hr_el is not None and hr_el.text:
            try: hr_values.append(float(hr_el.text))
            except: pass
        if time_el is not None and time_el.text:
            try: times.append(datetime.fromisoformat(time_el.text.replace("Z", "+00:00")))
            except: pass

    distance_m = max(distances) if distances else None
    avg_hr     = sum(hr_values) / len(hr_values) if hr_values else None
    duration_s = None
    if len(times) >= 2:
        duration_s = (times[-1] - times[0]).total_seconds()

    return {
        "sport_type":  sport,
        "start_time":  start_time,
        "distance_m":  distance_m,
        "duration_s":  duration_s,
        "avg_hr":      avg_hr,
        "source":      "tcx_import",
    }


def _parse_fit(content: bytes) -> dict:
    """Parsea un archivo FIT y extrae métricas básicas."""
    try:
        from fitparse import FitFile
    except ImportError:
        raise HTTPException(503, "fitparse no instalado — pip install fitparse")

    fitfile    = FitFile(io.BytesIO(content))
    sport      = "Other"
    start_time = None
    distance_m = None
    duration_s = None
    avg_hr     = None

    for msg in fitfile.get_messages("session"):
        for data in msg:
            if data.name == "sport":      sport      = str(data.value)
            if data.name == "start_time": start_time = data.value
            if data.name == "total_distance": distance_m = data.value
            if data.name == "total_elapsed_time": duration_s = data.value
            if data.name == "avg_heart_rate": avg_hr = data.value

    return {
        "sport_type":  sport,
        "start_time":  start_time,
        "distance_m":  distance_m,
        "duration_s":  duration_s,
        "avg_hr":      float(avg_hr) if avg_hr else None,
        "source":      "fit_import",
    }


@router.post("/import-activity")
async def import_activity(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Importa una actividad desde archivo .fit o .tcx."""
    filename = (file.filename or "").lower()
    if not (filename.endswith(".fit") or filename.endswith(".tcx")):
        raise HTTPException(400, "Solo se aceptan archivos .fit o .tcx")

    content = await file.read()
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(400, f"Archivo demasiado grande (máx {_MAX_FILE_MB} MB)")
    if len(content) == 0:
        raise HTTPException(400, "Archivo vacío")

    try:
        if filename.endswith(".tcx"):
            data = _parse_tcx(content)
        else:
            data = _parse_fit(content)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Error al parsear %s: %s", filename, e)
        raise HTTPException(400, f"No se pudo leer el archivo: {e}")

    # Verificar si ya existe una actividad con el mismo start_time
    if data.get("start_time"):
        existing = db.query(GarminActivity).filter(
            GarminActivity.user_id   == me.id,
            GarminActivity.start_time == str(data["start_time"])[:19]
        ).first()
        if existing:
            return {"ok": True, "activity_id": existing.id, "duplicate": True,
                    "message": "Esta actividad ya existe en LabX"}

    activity = GarminActivity(
        id          = str(uuid.uuid4()),
        user_id     = me.id,
        activity_id = f"import_{uuid.uuid4().hex[:12]}",
        sport_type  = data.get("sport_type"),
        start_time  = str(data["start_time"])[:19] if data.get("start_time") else None,
        distance_m  = data.get("distance_m"),
        duration_s  = data.get("duration_s"),
        avg_hr      = data.get("avg_hr"),
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)

    logger.info("Actividad importada user_id=%s sport=%s source=%s",
                me.id, data.get("sport_type"), data.get("source"))
    return {
        "ok":          True,
        "activity_id": activity.id,
        "duplicate":   False,
        "sport_type":  data.get("sport_type"),
        "distance_km": round((data.get("distance_m") or 0) / 1000, 2),
        "duration_min": round((data.get("duration_s") or 0) / 60, 1),
        "message":     "Actividad importada correctamente",
    }
