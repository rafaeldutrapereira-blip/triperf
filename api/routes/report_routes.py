"""
LabX — Exportación de reportes PDF semanales
Genera un resumen de entrenamiento semanal del atleta en PDF.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, date, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, GarminActivity, GarminTrainingLoad, AssignedWorkout
from ..auth import get_current_user, require_role
from ..permissions import assert_coach_owns_athlete

logger = logging.getLogger("labx.reports")
router = APIRouter(prefix="/coach/report", tags=["reports"])


def _sport_emoji(sport: str) -> str:
    s = (sport or "").lower()
    if "swim" in s or "nata" in s:  return "🏊"
    if "bike" in s or "cicl" in s or "cycling" in s: return "🚴"
    if "run"  in s or "carr" in s:  return "🏃"
    if "tri"  in s:                 return "🏅"
    return "⚡"


def _generate_pdf(athlete: User, activities: list, loads: list, week_str: str) -> bytes:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    except ImportError:
        raise HTTPException(503, "reportlab no instalado — pip install reportlab")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm
    )

    # Colores LabX
    ORANGE = colors.HexColor("#FF6535")
    DARK   = colors.HexColor("#08121E")
    GREY   = colors.HexColor("#4A7A96")
    LIGHT  = colors.HexColor("#E8F4F8")
    CYAN   = colors.HexColor("#0EA5E9")

    styles = getSampleStyleSheet()
    title_s = ParagraphStyle("title", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=22, textColor=ORANGE, spaceAfter=2)
    sub_s = ParagraphStyle("sub", parent=styles["Normal"],
        fontName="Helvetica", fontSize=10, textColor=GREY, spaceAfter=8)
    h2_s = ParagraphStyle("h2", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=12, textColor=CYAN, spaceBefore=14, spaceAfter=4)
    body_s = ParagraphStyle("body", parent=styles["Normal"],
        fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#1C3A50"), leading=14)
    small_s = ParagraphStyle("small", parent=styles["Normal"],
        fontName="Helvetica", fontSize=8, textColor=GREY)

    story = []

    # Header
    story.append(Paragraph("LabX · Reporte Semanal", title_s))
    story.append(Paragraph(f"Atleta: {athlete.nombre}  ·  Semana: {week_str}", sub_s))
    story.append(HRFlowable(width="100%", thickness=1, color=ORANGE, spaceAfter=10))

    # Métricas de carga (última disponible)
    if loads:
        latest = loads[-1]
        story.append(Paragraph("Carga de Entrenamiento", h2_s))
        load_data = [
            ["Métrica", "Valor", "Descripción"],
            ["ATL (Fatiga)", f"{latest.atl:.0f}" if latest.atl else "—", "Carga aguda últimos 7 días"],
            ["CTL (Fitness)", f"{latest.ctl:.0f}" if latest.ctl else "—", "Carga crónica últimos 42 días"],
            ["TSB (Forma)", f"{latest.tsb:.0f}" if latest.tsb else "—", "Forma actual (CTL - ATL)"],
            ["ACWR", f"{latest.acwr:.2f}" if latest.acwr else "—", "Ratio carga aguda/crónica (ideal: 0.8-1.3)"],
        ]
        load_table = Table(load_data, colWidths=[4*cm, 3*cm, 9.5*cm])
        load_table.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0), CYAN),
            ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,-1), 8.5),
            ("ALIGN",       (1,0), (1,-1), "CENTER"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#F7FBFE"), colors.white]),
            ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#C8DFE8")),
            ("PADDING",     (0,0), (-1,-1), 5),
        ]))
        story.append(load_table)
        story.append(Spacer(1, 8))

    # Actividades de la semana
    story.append(Paragraph("Actividades de la Semana", h2_s))
    if activities:
        acts_data = [["Deporte", "Fecha", "Distancia", "Duración", "FC Prom", "TSS"]]
        total_km = 0.0; total_min = 0; total_tss = 0.0
        for act in activities:
            dist_km = (act.distance_m or 0) / 1000
            dur_min = int((act.duration_s or 0) / 60)
            total_km  += dist_km
            total_min += dur_min
            total_tss += (act.tss or 0)
            acts_data.append([
                _sport_emoji(act.sport_type) + " " + (act.sport_type or "—"),
                str(act.start_time)[:10] if act.start_time else "—",
                f"{dist_km:.1f} km" if dist_km > 0 else "—",
                f"{dur_min} min",
                f"{act.avg_hr:.0f} bpm" if act.avg_hr else "—",
                f"{act.tss:.0f}" if act.tss else "—",
            ])
        # Fila totales
        acts_data.append([
            "TOTAL", "", f"{total_km:.1f} km", f"{total_min} min", "", f"{total_tss:.0f}"
        ])
        acts_table = Table(acts_data, colWidths=[4*cm, 2.5*cm, 3*cm, 2.5*cm, 2.5*cm, 2*cm])
        acts_table.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0), DARK),
            ("TEXTCOLOR",   (0,0), (-1,0), LIGHT),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTNAME",    (0,-1), (-1,-1), "Helvetica-Bold"),
            ("BACKGROUND",  (0,-1), (-1,-1), colors.HexColor("#EDF5FA")),
            ("FONTSIZE",    (0,0), (-1,-1), 8),
            ("ALIGN",       (2,0), (-1,-1), "CENTER"),
            ("ROWBACKGROUNDS", (0,1), (-1,-2), [colors.HexColor("#F7FBFE"), colors.white]),
            ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#C8DFE8")),
            ("PADDING",     (0,0), (-1,-1), 5),
        ]))
        story.append(acts_table)
    else:
        story.append(Paragraph("Sin actividades registradas esta semana.", body_s))

    # Perfil del atleta
    story.append(Spacer(1, 12))
    story.append(Paragraph("Perfil del Atleta", h2_s))
    profile_lines = []
    if athlete.weight_kg: profile_lines.append(f"Peso: {athlete.weight_kg} kg")
    if athlete.ftp:        profile_lines.append(f"FTP: {athlete.ftp} W")
    if athlete.fcmax:      profile_lines.append(f"FC Máxima: {athlete.fcmax} bpm")
    if athlete.vo2max:     profile_lines.append(f"VO2max: {athlete.vo2max}")
    if athlete.css:        profile_lines.append(f"CSS: {athlete.css}")
    if athlete.run_pace:   profile_lines.append(f"Ritmo umbral carrera: {athlete.run_pace}")
    if athlete.race_goal_name:
        profile_lines.append(f"Meta: {athlete.race_goal_name} ({athlete.race_goal_date or 'TBD'})")
    if profile_lines:
        story.append(Paragraph("  ·  ".join(profile_lines), body_s))
    else:
        story.append(Paragraph("Perfil no completado.", small_s))

    # Footer
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GREY))
    story.append(Paragraph(
        f"Generado por LabX Performance Platform · {datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M')} UTC",
        small_s
    ))

    doc.build(story)
    return buf.getvalue()


@router.get("/athlete/{athlete_id}/pdf")
def export_athlete_pdf(
    athlete_id: str,
    request: Request,
    db: Session = Depends(get_db),
    coach: User = Depends(require_role("coach", "admin")),
):
    """Genera PDF del reporte semanal de un atleta (coach/admin)."""
    athlete = assert_coach_owns_athlete(coach.id, athlete_id, db)

    # Semana actual
    today   = date.today()
    monday  = today - timedelta(days=today.weekday())
    sunday  = monday + timedelta(days=6)
    week_str = f"{monday.isoformat()} — {sunday.isoformat()}"

    activities = (
        db.query(GarminActivity)
        .filter(
            GarminActivity.user_id == athlete_id,
            GarminActivity.start_time >= monday.isoformat()
        )
        .order_by(GarminActivity.start_time)
        .all()
    )
    loads = (
        db.query(GarminTrainingLoad)
        .filter(
            GarminTrainingLoad.user_id == athlete_id,
            GarminTrainingLoad.date >= (monday - timedelta(days=7)).isoformat()
        )
        .order_by(GarminTrainingLoad.date)
        .all()
    )

    pdf_bytes = _generate_pdf(athlete, activities, loads, week_str)
    filename  = f"labx-reporte-{athlete.nombre.replace(' ', '_')}-{monday.isoformat()}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/me/pdf")
def export_my_pdf(
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Genera PDF del reporte semanal propio del atleta."""
    today   = date.today()
    monday  = today - timedelta(days=today.weekday())
    sunday  = monday + timedelta(days=6)
    week_str = f"{monday.isoformat()} — {sunday.isoformat()}"

    activities = (
        db.query(GarminActivity)
        .filter(GarminActivity.user_id == me.id, GarminActivity.start_time >= monday.isoformat())
        .order_by(GarminActivity.start_time)
        .all()
    )
    loads = (
        db.query(GarminTrainingLoad)
        .filter(GarminTrainingLoad.user_id == me.id,
                GarminTrainingLoad.date >= (monday - timedelta(days=7)).isoformat())
        .order_by(GarminTrainingLoad.date)
        .all()
    )

    pdf_bytes = _generate_pdf(me, activities, loads, week_str)
    filename  = f"labx-reporte-{me.nombre.replace(' ', '_')}-{monday.isoformat()}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
