"""DRAGDROP-INFORME: PDF real del informe de atleta (reportlab, solo servidor).

Imprime EXACTAMENTE los campos de `AthleteReport` (mismos numeros que la vista y
el JSON): nada se recalcula ni se inventa. Un campo sin dato se rotula "sin dato".
"""
from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

NO_DATA = "sin dato"

SPORT_LABEL = {"run": "Correr", "bike": "Ciclismo", "swim": "Natación", "str": "Fuerza", "tri": "Triatlón"}

DEFAULT_NOTICE = (
    "Este PDF contiene los datos del informe (totales, deporte, semana, carga y objetivo). "
    "Bienestar, exámenes de sangre y plan de nutrición no se incluyen en el PDF."
)


def _v(x, suffix="") -> str:
    return NO_DATA if x is None else f"{x}{suffix}"


def _table(rows):
    t = Table(rows, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9ca3af")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ]))
    return t


def build_report_pdf(report, notice: str | None = None) -> bytes:
    """`report` = AthleteReport (o dict equivalente). Devuelve los bytes del PDF."""
    r = report.model_dump() if hasattr(report, "model_dump") else dict(report)
    st = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=st["Heading1"], fontSize=17, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=st["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("b", parent=st["BodyText"], fontSize=9.5)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=colors.HexColor("#6b7280"))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                            topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            title=f"Informe {r['athlete_nombre']}", author="LabX")
    el = [
        Paragraph(f"Informe de {escape(str(r['athlete_nombre']))}", h1),
        Paragraph(f"Período: {escape(r['period_start'])} → {escape(r['period_end'])}", body),
    ]
    if r.get("race_goal_name") or r.get("race_goal_date"):
        el.append(Paragraph(
            f"Objetivo de carrera: {escape(_v(r.get('race_goal_name')))} · {escape(_v(r.get('race_goal_date')))}", body))

    el.append(Paragraph("Totales: planificado vs ejecutado", h2))
    el.append(_table([
        ["Ses. plan.", "Ses. hechas", "Cumplimiento", "TSS plan.", "TSS real", "Dist. km", "Dur. min"],
        [r["sessions_total"], r["sessions_done"], f"{r['compliance_pct']}%", r["tss_planned"],
         r["tss_actual"], r["dist_total_km"], r["dur_total_min"]],
    ]))

    el.append(Paragraph("Forma y carga (CTL / ATL / TSB / ACWR)", h2))
    el.append(_table([
        ["Fitness (CTL)", "Fatiga (ATL)", "Balance (TSB)", "Carga aguda/crónica (ACWR)"],
        [_v(r.get("ctl")), _v(r.get("atl")), _v(r.get("tsb")), _v(r.get("acwr"))],
    ]))

    el.append(Paragraph("Por deporte", h2))
    if r["by_sport"]:
        rows = [["Deporte", "Ses. plan.", "Ses. hechas", "Dist. plan. km", "Dist. real km",
                 "Dur. plan. min", "Dur. real min", "TSS plan.", "TSS real"]]
        for s in r["by_sport"]:
            rows.append([SPORT_LABEL.get(s["sport"], s["sport"]), s["sessions_planned"], s["sessions_done"],
                         round(s["dist_planned_km"], 1), round(s["dist_actual_km"], 1),
                         s["dur_planned_min"], s["dur_actual_min"], s["tss_planned"], s["tss_actual"]])
        el.append(_table(rows))
    else:
        el.append(Paragraph("Sin sesiones planificadas en el período.", body))

    el.append(Paragraph("Por semana", h2))
    if r["weeks"]:
        rows = [["Semana (lunes)", "Ses. plan.", "Ses. hechas", "TSS plan.", "TSS real", "Dist. real km"]]
        for w in r["weeks"]:
            rows.append([w["week_start"], w["sessions_planned"], w["sessions_done"],
                         w["tss_planned"], w["tss_actual"], round(w["dist_actual_km"], 1)])
        el.append(_table(rows))
    else:
        el.append(Paragraph("Sin semanas con sesiones en el período.", body))

    el.append(Spacer(1, 10))
    el.append(Paragraph(escape(notice or DEFAULT_NOTICE), small))
    el.append(Paragraph("Generado por LabX", small))
    doc.build(el)
    return buf.getvalue()
