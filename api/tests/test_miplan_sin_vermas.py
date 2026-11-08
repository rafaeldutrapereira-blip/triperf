"""MIPLAN-SIN-VERMAS (BUILD 356): Mi Plan sin «Ver más»; el resumen es la superficie de trabajo."""
import re

import pytest

from .test_miplan_resumen import HTML, I18N, NODE, SW, _plan, _run


def test_desaparece_ver_mas_completo():
    for frag in ('tp-more', 'cal-area', 'id="s-cal"', 'cal-panel-title', 'tp_more_toggle',
                 'data-view="week"', 'data-view="month"', 'data-view="period"',
                 'renderWeekCal', 'renderMonthCal', 'renderPeriodCal', 'applyPeriod',
                 'id="period-inputs"'):
        assert frag not in HTML, frag
    # el enlace a Ajustes adaptativos y el builder (desde el detalle) se conservan
    assert 'id="s-adaptive-link"' in HTML and 'href="adaptive.html"' in HTML
    assert 'indoor_workout.html?date=' in HTML


@pytest.mark.skipif(not NODE, reason="node no disponible")
def test_chips_abren_el_modal_de_detalle_existente():
    h = _run([_plan("a", "2026-11-03", "bike", "Rodaje", 60)])
    assert 'onclick="showDetail(&quot;a&quot;)"' in h or "showDetail(" in h
    assert 'draggable="true"' in h and 'data-sess-id="a"' in h  # arrastrar para mover
    # externas / del coach: no arrastrables
    h2 = _run([_plan("c", "2026-11-03", "bike", "Coach", 60, editable=False)])
    assert 'draggable' not in h2
    # sin logica duplicada: un unico showDetail / saveSession
    assert HTML.count("window.showDetail = function") == 1
    assert HTML.count("window.saveSession = function") == 1


@pytest.mark.skipif(not NODE, reason="node no disponible")
def test_agregar_sesion_desde_cada_dia():
    h = _run([])
    adds = re.findall(r'class="tp-day-add"[^>]*onclick="openModal\((.*?)\)"', h)
    assert len(adds) >= 7  # los 7 dias de la semana + semanas futuras
    assert "2026-11-04" in "".join(adds)
    assert "window.openModal = function (defaultDate)" in HTML


def test_selector_de_mes_hoy_y_flechas():
    assert 'id="nav-month"' in HTML and 'type="month"' in HTML
    assert 'id="btn-today"' in HTML and 'id="btn-prev"' in HTML and 'id="btn-next"' in HTML
    assert "addDays(S.ref, -7)" in HTML and "addDays(S.ref, 7)" in HTML


def test_filtros_por_deporte_como_chips_en_el_encabezado():
    i = HTML.index('id="sport-filters"')
    row = HTML[i:HTML.index("</div>", i)]
    for sp in ('data-sport=""', 'data-sport="swim"', 'data-sport="bike"',
               'data-sport="run"', 'data-sport="str"'):
        assert sp in row, sp
    # el filtro vive antes del contenido principal (encabezado), no dentro de nada plegable
    assert i < HTML.index('<div class="main">')
    assert "S.filters = sport === '' ? [] : [sport];" in HTML


def test_i18n_trilingue_y_build_356():
    for k in ("tp_today_btn", "tp_goto_month", "tp_add_session_day"):
        assert I18N.count("    " + k + ":") == 3, k
    assert re.search(r"BUILD_VERSION = '(35[6-9]|3[6-9]\d|[4-9]\d\d)'", SW)
