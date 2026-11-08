"""LABS-CAPAS (BUILD 352) — Laboratorio en capas; nada desaparece."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(name):
    return (ROOT / name).read_text(encoding="utf-8")


# ids/controles del inventario del Paso 0 (ninguno puede desaparecer)
IDS = [
    "sel-exam", "sel-comp", "comp-label", "exam-ctx-lbl", "btn-delete-exam",
    "chip-score", "chip-alerts", "chip-alert-n", "chip-exams", "bl-disclaimer",
    "bl-plain", "alerts-container", "clinical-summary", "bl-ver-todo",
    "kpi-trs", "kpi-markers", "kpi-next", "ch-radar", "btn-ai-analyze",
    "ai-interpretation-box", "bm-table-container",
    "tab-resumen", "tab-trends", "tab-garmin", "tab-import",
    "trend-content", "corr-table", "inp-file", "btn-review-exam", "btn-save-exam",
]


def test_ningun_id_ni_control_desaparece():
    h = _read("blood_labs.html")
    for i in IDS:
        assert 'id="%s"' % i in h, i
    for tab in ("resumen", "trends", "garmin", "import"):
        assert 'data-tab="%s"' % tab in h


def test_disclaimer_visible_en_nivel_1():
    h = _read("blood_labs.html")
    assert h.index('id="bl-disclaimer"') < h.index('id="bl-l1-title"')
    i_all = h.index('<details class="bl-all')
    assert h.index('id="bl-disclaimer"') < i_all


def test_orden_de_capas():
    h = _read("blood_labs.html")
    i1 = h.index('id="bl-l1-title"')
    i2 = h.index('id="bl-systems"')
    i3 = h.index('<details class="bl-all')
    assert i1 < h.index('id="bl-plain"') < h.index('id="alerts-container"') < i2 < i3
    # nivel 2 fuera del plegable; tabla completa dentro
    assert h.index('id="bm-table-container"') > i3


def test_agrupacion_por_sistema_y_otros():
    h = re.sub(r"\s+", " ", _read("blood_labs.html"))
    assert "function renderSystemGroups(cur)" in h
    assert "renderSystemGroups(cur);" in h
    for c in ("hematologico", "hormonal", "inflamacion", "vitaminas", "metabolico", "renal", "hepatico"):
        assert "'%s'" % c in h
    assert "bl_sys_otros" in h
    # sin rangos inventados: el estado sale de zone del servidor
    assert "case 'very_high'" in h


def test_i18n_tres_idiomas():
    i = _read("i18n.js")
    for k in ("bl_l1_title", "bl_l2_title", "bl_sys_energia", "bl_sys_otros",
              "bl_zone_optimal", "bl_zone_very_low", "bl_zone_none"):
        assert i.count(k + ":") == 3, k


def test_build_352():
    assert "BUILD_VERSION = '352'" in _read("sw.js")
