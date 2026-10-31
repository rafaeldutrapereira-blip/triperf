# -*- coding: utf-8 -*-
"""Genera el one-pager A4 de LabX (estilo consulting / McKinsey)."""

from pptx import Presentation
from pptx.util import Cm, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
import os

HERE = os.path.dirname(os.path.abspath(__file__))

NAVY = "0B1F33"
NAVY2 = "16344F"
GREY = "5E6F7E"
GREY_L = "8DA0AE"
RULE = "DCE3E8"
TINT = "F3F6F8"
ORANGE = "DF4E1A"
ORANGE_T = "FBEEE7"
WHITE = "FFFFFF"

FONT = "Arial"

prs = Presentation()
prs.slide_width = Cm(21)
prs.slide_height = Cm(29.7)
slide = prs.slides.add_slide(prs.slide_layouts[6])


def rect(x, y, w, h, fill=None, line=None, lw=0.6):
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(x), Cm(y), Cm(w), Cm(h))
    s.shadow.inherit = False
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = RGBColor.from_string(fill)
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = RGBColor.from_string(line)
        s.line.width = Pt(lw)
    return s


def dot(cx, cy, d, fill, line=None):
    s = slide.shapes.add_shape(MSO_SHAPE.OVAL, Cm(cx - d / 2), Cm(cy - d / 2), Cm(d), Cm(d))
    s.shadow.inherit = False
    s.fill.solid()
    s.fill.fore_color.rgb = RGBColor.from_string(fill)
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = RGBColor.from_string(line)
        s.line.width = Pt(0.5)
    return s


def hline(x, y, w, color=RULE, lw=0.6):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Cm(x), Cm(y), Cm(x + w), Cm(y))
    c.line.color.rgb = RGBColor.from_string(color)
    c.line.width = Pt(lw)
    return c


def vline(x, y, h, color=RULE, lw=0.6):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Cm(x), Cm(y), Cm(x), Cm(y + h))
    c.line.color.rgb = RGBColor.from_string(color)
    c.line.width = Pt(lw)
    return c


def tx(x, y, w, h, paras, anchor="t"):
    box = slide.shapes.add_textbox(Cm(x), Cm(y), Cm(w), Cm(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[anchor]
    first = True
    for p in paras:
        para = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        para.alignment = p.get("align", PP_ALIGN.LEFT)
        para.space_before = Pt(p.get("before", 0))
        para.space_after = Pt(p.get("after", 0))
        para.line_spacing = p.get("line", 1.0)
        for r in p["runs"]:
            run = para.add_run()
            run.text = r["t"]
            f = run.font
            f.name = FONT
            f.size = Pt(r.get("size", p.get("size", 9)))
            f.bold = r.get("bold", p.get("bold", False))
            f.italic = r.get("italic", p.get("italic", False))
            f.color.rgb = RGBColor.from_string(r.get("color", p.get("color", NAVY)))
            spc = r.get("spc", p.get("spc", 0))
            if spc:
                run.font._element.set("spc", str(int(spc * 100)))
    return box


def P(text, size=8.4, color=NAVY, bold=False, italic=False, spc=0, align=PP_ALIGN.LEFT,
      before=0, after=0, line=1.0):
    return {"runs": [{"t": text, "size": size, "color": color, "bold": bold,
                      "italic": italic, "spc": spc}], "align": align,
            "before": before, "after": after, "line": line}


# ---------------------------------------------------------------- header
rect(0, 0, 21, 1.55, fill=NAVY)
rect(0, 1.55, 21, 0.13, fill=ORANGE)

tx(1.4, 0.34, 4.6, 0.9, [{"runs": [
    {"t": "LAB", "size": 17, "bold": True, "color": WHITE, "spc": 1.2},
    {"t": "X", "size": 17, "bold": True, "color": ORANGE, "spc": 1.2},
]}], anchor="m")

vline(3.95, 0.48, 0.6, color="2C445C", lw=0.8)

tx(4.22, 0.34, 7.0, 0.9, [P("PLATAFORMA DE RENDIMIENTO PARA RESISTENCIA",
                            size=5.8, color="9FB4C4", spc=0.7)], anchor="m")

tx(12.4, 0.34, 7.2, 0.9, [P("DOCUMENTO PARA COMPARTIR  ·  OCTUBRE 2026",
                            size=5.9, color="9FB4C4", spc=0.7, align=PP_ALIGN.RIGHT)], anchor="m")

# ---------------------------------------------------------------- title block
tx(1.4, 1.95, 12.0, 0.4, [P("LA IDEA EN UNA LÍNEA", size=6.6, color=ORANGE, bold=True, spc=1.6)])

tx(1.4, 2.3, 18.2, 2.0, [
    P("Tu Garmin ya registra todo.", size=21, bold=True, color=NAVY, line=1.02),
    P("LabX lo convierte en una decisión diaria.", size=21, bold=True, color=ORANGE, line=1.02),
])

tx(1.4, 4.55, 16.4, 1.7, [P(
    "Cada sesión queda en el reloj, pero la decisión de qué hacer mañana sigue repartida entre una planilla, "
    "un PDF de laboratorio, una app de nutrición y la memoria del entrenador. LabX integra carga, recuperación, "
    "sangre y nutrición en un solo lugar, y devuelve la única salida que sirve: qué entrenar hoy, a qué intensidad "
    "y cuándo frenar.",
    size=8.4, color=GREY, line=1.18)])

hline(1.4, 6.65, 18.2, color=NAVY, lw=0.9)

# ---------------------------------------------------------------- 01 diagnóstico (left)
LX, LW = 1.4, 10.4

tx(LX, 6.95, LW, 0.35, [{"runs": [
    {"t": "01", "size": 7.4, "bold": True, "color": ORANGE, "spc": 1.0},
    {"t": "   EL DIAGNÓSTICO", "size": 7.4, "bold": True, "color": NAVY, "spc": 1.4},
]}])

tx(LX, 7.33, LW, 1.9, [P(
    "El deportista de resistencia promedio acumula datos en seis herramientas que no se hablan entre sí. "
    "Cada una responde una pregunta distinta y ninguna responde la que importa el domingo a la noche: "
    "qué hago mañana.",
    size=8.2, color=NAVY2, line=1.2)])

# Exhibit 1
tx(LX, 9.28, LW, 0.3, [P("EXHIBIT 1", size=6.2, color=ORANGE, bold=True, spc=1.4)])
tx(LX, 9.55, LW, 0.4, [P("Ninguna herramienta cubre las cinco decisiones del entrenamiento",
                         size=8.6, bold=True, color=NAVY)])

COLS = ["MEDIR", "ENTENDER", "DECIDIR", "EJECUTAR", "AJUSTAR"]
LABEL_W = 3.35
COL_W = (LW - LABEL_W) / 5.0
HDR_Y = 10.02
ROW_Y = 10.42
ROW_H = 0.62
ROWS = [
    ("Garmin Connect",      [2, 1, 0, 0, 0]),
    ("Strava",              [2, 0, 0, 1, 0]),
    ("TrainingPeaks / WKO", [2, 2, 1, 2, 0]),
    ("Planilla propia",     [0, 1, 1, 0, 0]),
    ("PDF del laboratorio", [1, 0, 0, 0, 0]),
    ("Chat del entrenador", [0, 0, 1, 2, 1]),
    ("LabX",                [2, 2, 2, 2, 2]),
]
FILL = {2: NAVY, 1: "A9BFCE", 0: "E8EEF2"}

for i, c in enumerate(COLS):
    cx = LX + LABEL_W + COL_W * (i + 0.5)
    tx(cx - 0.7, HDR_Y, 1.4, 0.3, [P(c, size=5.4, color=GREY, bold=True, spc=0.2, align=PP_ALIGN.CENTER)])
hline(LX, ROW_Y - 0.04, LW, color=NAVY, lw=0.8)

for r, (label, vals) in enumerate(ROWS):
    y = ROW_Y + r * ROW_H
    is_labx = label == "LabX"
    if is_labx:
        rect(LX, y, LW, ROW_H, fill=ORANGE_T)
    elif r % 2 == 1:
        rect(LX, y, LW, ROW_H, fill=TINT)
    tx(LX + 0.06, y, LABEL_W - 0.1, ROW_H,
       [P(label, size=7.2, bold=is_labx, color=(ORANGE if is_labx else NAVY2))], anchor="m")
    for i, v in enumerate(vals):
        cx = LX + LABEL_W + COL_W * (i + 0.5)
        dot(cx, y + ROW_H / 2, 0.235, ORANGE if is_labx else FILL[v])
    if r < len(ROWS) - 1:
        hline(LX, y + ROW_H, LW, color=RULE, lw=0.45)

MATRIX_END = ROW_Y + len(ROWS) * ROW_H
hline(LX, MATRIX_END, LW, color=NAVY, lw=0.8)

# legend
ly = MATRIX_END + 0.22
dot(LX + 0.12, ly, 0.2, NAVY)
tx(LX + 0.3, ly - 0.15, 1.9, 0.3, [P("cubierto", size=5.8, color=GREY)])
dot(LX + 2.15, ly, 0.2, "A9BFCE")
tx(LX + 2.33, ly - 0.15, 2.0, 0.3, [P("parcial", size=5.8, color=GREY)])
dot(LX + 3.85, ly, 0.2, "E8EEF2")
tx(LX + 4.03, ly - 0.15, 2.1, 0.3, [P("no cubierto", size=5.8, color=GREY)])
tx(LX + 5.7, ly - 0.15, LW - 5.7, 0.3,
   [P("Evaluación cualitativa · octubre 2026", size=5.4, color=GREY_L,
      align=PP_ALIGN.RIGHT, italic=True)])

# callout
CY = MATRIX_END + 0.66
rect(LX, CY, 0.09, 1.1, fill=ORANGE)
tx(LX + 0.28, CY - 0.04, LW - 0.3, 1.2, [P(
    "La diferencia no es tener más datos: es cerrar el circuito entre medir y ajustar. "
    "Ese circuito, hoy, está partido en seis lugares.",
    size=8.2, color=NAVY, italic=True, line=1.2)])

# ---------------------------------------------------------------- 02 qué incluye (right)
RX, RW = 12.5, 7.1

tx(RX, 6.95, RW, 0.35, [{"runs": [
    {"t": "02", "size": 7.4, "bold": True, "color": ORANGE, "spc": 1.0},
    {"t": "   QUÉ INCLUYE", "size": 7.4, "bold": True, "color": NAVY, "spc": 1.4},
]}])

ITEMS = [
    ("Carga y forma (PMC)", "CTL, ATL y TSB recalculados con cada actividad, no una vez por semana."),
    ("Sync Garmin automático", "Nado, bici, running y fuerza con potencia, FC, ritmo y GPS."),
    ("ACWR por disciplina", "El riesgo de lesión se mide por deporte, no en promedio."),
    ("Blood Labs", "Biomarcadores correlacionados con tu carga real de entrenamiento."),
    ("Plan adaptativo + Race Day", "Se reajusta con tu fatiga; pacing y nutrición hora a hora el día de la carrera."),
    ("Asistente IA", "Forecast de CTL, prescripción de sesiones y alerta temprana de riesgo."),
    ("Recuperación y mente", "Readiness diario con HRV, sueño y fatiga neurocognitiva."),
    ("App instalable + Coach", "Todo en el celular, sin tienda. Panel para gestionar 50+ atletas."),
]

paras = []
for name, desc in ITEMS:
    paras.append({"runs": [
        {"t": "\u25aa  ", "size": 6.6, "color": ORANGE},
        {"t": name + "  ", "size": 7.3, "bold": True, "color": NAVY},
        {"t": desc, "size": 7.3, "color": GREY},
    ], "after": 2.6, "line": 1.08})
tx(RX, 7.35, RW, 6.2, paras)

# 03 para quién
tx(RX, 14.15, RW, 0.35, [{"runs": [
    {"t": "03", "size": 7.4, "bold": True, "color": ORANGE, "spc": 1.0},
    {"t": "   PARA QUIÉN", "size": 7.4, "bold": True, "color": NAVY, "spc": 1.4},
]}])
tx(RX, 14.52, RW, 1.0, [P(
    "Triatletas y corredores que ya entrenan con datos y coaches que hoy gestionan su squad "
    "con planillas y WhatsApp.",
    size=7.6, color=NAVY2, line=1.2)])

# pull quote
rect(RX, 15.78, 0.09, 0.85, fill=NAVY)
tx(RX + 0.28, 15.74, RW - 0.3, 0.95, [P(
    "\u00abEl Strava te dice lo que hiciste. LabX te dice qué hacer mañana.\u00bb",
    size=8.0, color=NAVY, italic=True, line=1.15)])

hline(1.4, 16.95, 18.2, color=RULE, lw=0.7)

# ---------------------------------------------------------------- exhibit 2 (chart)
tx(1.4, 17.12, 10.5, 0.3, [P("EXHIBIT 2", size=6.2, color=ORANGE, bold=True, spc=1.4)])
tx(1.4, 17.39, 10.6, 0.35, [P("Cómo se ve la carga cuando el plan se ajusta solo",
                              size=8.6, bold=True, color=NAVY)])

CTL = [42, 46, 50, 54, 57, 60, 62, 65, 68, 70, 72, 74, 76, 77, 78, 79, 79, 78, 78, 78]
ATL = [55, 63, 58, 72, 76, 66, 82, 90, 74, 94, 86, 78, 98, 104, 88, 82, 96, 112, 76, 64]

PX0, PX1 = 2.3, 11.15
PY0, PY1 = 22.5, 18.0
VMAX = 120


def xp(i):
    return PX0 + (PX1 - PX0) * i / (len(CTL) - 1)


def yp(v):
    return PY0 + (PY1 - PY0) * (v / VMAX)


# taper band
rect(xp(16), PY1 - 0.04, PX1 - xp(16), PY0 - PY1 + 0.04, fill="EDF1F4")
tx(xp(16) + 0.06, PY1 + 0.03, 2.4, 0.25, [P("DESCARGA", size=5.0, color=GREY_L, spc=0.9)])

for gv in (0, 40, 80, 120):
    yy = yp(gv)
    hline(PX0, yy, PX1 - PX0, color=RULE if gv else "C3CED6", lw=0.5)
    tx(PX0 - 0.78, yy - 0.13, 0.68, 0.25, [P(str(gv), size=5.4, color=GREY_L, align=PP_ALIGN.RIGHT)])

for i in range(0, len(CTL), 4):
    tx(xp(i) - 0.4, PY0 + 0.1, 0.8, 0.25,
       [P("S%d" % (i + 1), size=5.4, color=GREY_L, align=PP_ALIGN.CENTER)])


def polyline(vals, color, width):
    SCALE = Cm(1) / 1000.0
    pts = [(xp(i) * 1000, yp(v) * 1000) for i, v in enumerate(vals)]
    ff = slide.shapes.build_freeform(pts[0][0], pts[0][1], scale=SCALE)
    ff.add_line_segments(pts[1:], close=False)
    s = ff.convert_to_shape()
    s.shadow.inherit = False
    s.fill.background()
    s.line.color.rgb = RGBColor.from_string(color)
    s.line.width = Pt(width)
    return s


polyline(CTL, NAVY, 1.5)
polyline(ATL, ORANGE, 1.3)

# end labels
tx(PX1 + 0.05, yp(CTL[-1]) - 0.28, 1.2, 0.25, [P("CTL 78", size=5.6, color=NAVY, bold=True)])
tx(PX1 + 0.05, yp(ATL[-1]) + 0.12, 1.2, 0.25, [P("ATL 64", size=5.6, color=ORANGE, bold=True)])

# legend (horizontal)
def chart_legend(x, label, color):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Cm(x), Cm(23.02), Cm(x + 0.6), Cm(23.02))
    c.line.color.rgb = RGBColor.from_string(color)
    c.line.width = Pt(1.6)
    tx(x + 0.7, 22.88, 2.5, 0.28, [P(label, size=5.8, color=GREY)])


chart_legend(PX0, "Carga crónica (CTL)", NAVY)
chart_legend(PX0 + 3.3, "Carga aguda (ATL)", ORANGE)

tx(PX0, 23.42, PX1 - PX0 + 0.3, 0.4, [P(
    "Serie simulada con la metodología CTL/ATL/TSB (Banister) que LabX calcula sobre tu historial real de Garmin.",
    size=5.2, color=GREY_L, italic=True, line=1.1)])

# ---------------------------------------------------------------- exhibit 2 stats (right)
SX, SW = 12.5, 7.1
stats = [
    ("78", "CTL al final de la preparación", "20 semanas de carga sostenida, sin picos aislados."),
    ("1,4\u00d7", "pico de carga aguda vs. crónica", "La alerta de ACWR se dispara acá, antes de la lesión."),
    ("+14", "TSB el día de la carrera", "Llega descansado porque el plan bajó la carga aguda."),
]
sy = 17.9
for big, cap, note in stats:
    tx(SX, sy, 1.75, 0.7, [P(big, size=17.5, bold=True, color=NAVY)])
    tx(SX + 1.8, sy + 0.02, SW - 1.8, 0.72, [
        P(cap, size=6.8, color=NAVY2, bold=True, line=1.05),
        P(note, size=6.3, color=GREY, line=1.1),
    ])
    sy += 1.42

hline(SX, sy - 0.08, SW, color=RULE, lw=0.6)
tx(SX, sy + 0.06, SW, 0.7, [P(
    "Con tu Garmin conectado, este gráfico deja de ser un ejemplo y pasa a ser tu curva real.",
    size=6.8, color=GREY, italic=True, line=1.15)])

# ---------------------------------------------------------------- CTA band
BY = 24.95
rect(0, BY, 21, 3.05, fill=NAVY)
rect(0, BY, 21, 0.09, fill=ORANGE)

tx(1.4, BY + 0.4, 11.0, 0.3, [P("ACCESO BETA  ·  GRATIS PARA AMIGOS", size=6.4, color=ORANGE,
                                bold=True, spc=1.4)])
tx(1.4, BY + 0.72, 11.2, 0.6, [P("Probalo con tu propia data esta semana.", size=13, bold=True, color=WHITE)])
tx(1.4, BY + 1.38, 11.2, 1.3, [P(
    "Conectás el Garmin una vez y en minutos tenés tu carga, tu recuperación y el plan del día. "
    "Si te sirve, se lo pasás al que entrena con vos. Si no, me lo decís y listo.",
    size=7.6, color="C6D4DF", line=1.2)])

# QR
QR_X, QR_Y, QR_S = 16.55, BY + 0.42, 2.25
rect(QR_X - 0.12, QR_Y - 0.12, QR_S + 0.24, QR_S + 0.24, fill=WHITE)
slide.shapes.add_picture(os.path.join(HERE, "qr.png"), Cm(QR_X), Cm(QR_Y), Cm(QR_S), Cm(QR_S))

tx(13.2, QR_Y + 0.28, 3.1, 0.8, [
    P("Escaneá y entrá", size=6.6, color="9FB4C4", align=PP_ALIGN.RIGHT),
    P("labxperformanceapp.com", size=6.8, color=WHITE, bold=True, align=PP_ALIGN.RIGHT),
])

# ---------------------------------------------------------------- footer
tx(1.4, 28.2, 14.6, 1.1, [P(
    "Notas: métricas de producto al cierre de octubre 2026 (13 módulos activos, 500+ atletas en beta privada, "
    "4.132 actividades sincronizadas). Exhibit 2 ilustra la metodología con una serie simulada; Exhibit 1 es una "
    "comparación cualitativa y no exhaustiva de herramientas.",
    size=5.4, color=GREY_L, line=1.15)])

tx(16.2, 28.2, 3.4, 0.4, [P("labxperformanceapp.com", size=5.6, color=GREY, align=PP_ALIGN.RIGHT)])

out = os.path.join(HERE, "LabX-one-pager.pptx")
prs.save(out)
print("saved", out)
