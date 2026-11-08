"""MIPLAN-INTEGRA (BUILD 345): la franja semanal S3 se mueve al resumen de entrada."""
import re

import pytest

from .test_miplan_resumen import HTML, SW, NODE, _plan, _run

MON = "2026-11-02"


def _week(wellness=True, summary=True, with_acts=True):
    days = []
    for i in range(7):
        d = "2026-11-%02d" % (2 + i)
        w = {"sleep_h": 6.6, "hrv": 57, "rhr": 55} if (wellness and i == 1) else {}
        days.append({"date_iso": d, "wellness": w,
                     "done": [{"name": "x", "dur_min": 30}] if (with_acts and i == 0) else [],
                     "planned": []})
    s = ({"tss": 312.4, "ctl": 41.2, "tsb": -3.5, "atl": 44.7, "ramp": 2.1,
          "pmc_date": "2026-11-04"} if summary else {})
    return {MON: {"days": days, "summary": s}}


SESS = [_plan("a", "2026-11-03", "bike", "Rodaje", 60)]


@pytest.mark.skipif(not NODE, reason="node no disponible")
def test_bienestar_en_la_tarjeta_del_dia():
    h = _run(SESS, week=_week())
    assert h.count('class="tp-well"') == 1
    assert "Sueño 6.6h · HRV 57 · FC reposo 55" in h


@pytest.mark.skipif(not NODE, reason="node no disponible")
def test_sin_bienestar_no_hay_linea():
    assert "tp-well" not in _run(SESS, week=_week(wellness=False))
    assert "tp-well" not in _run(SESS)  # sin cache aun


@pytest.mark.skipif(not NODE, reason="node no disponible")
def test_cinco_metricas_en_la_entrada():
    h = _run(SESS, week=_week())
    for lbl, v in (("Carga (TSS)", "312"), ("Fitness (CTL)", "41.2"), ("Forma (TSB)", "-3.5"),
                   ("Fatiga (ATL)", "44.7"), ("Ramp rate", "+2.1")):
        assert "%s<b>%s</b>" % (lbl, v) in h, lbl
    assert "al 2026-11-04" in h
    assert h.count('id="tp-ov-line"') == 1 and "1 sesión · 1h planificadas" in h


@pytest.mark.skipif(not NODE, reason="node no disponible")
def test_semana_vacia_oculta_el_bloque():
    h = _run([], week=_week(with_acts=False))
    assert "tp-met" not in h and "Sin plan esta semana" in h


@pytest.mark.skipif(not NODE, reason="node no disponible")
def test_metricas_ausentes_no_se_inventan():
    assert "tp-met" not in _run(SESS, week=_week(summary=False))


def test_franja_fuera_de_ver_mas():
    assert "renderWeekStrip" not in HTML and "wk-strip" not in HTML
    i = HTML.index('<details class="tp-more"')
    more = HTML[i:HTML.index("</details>", i)]
    assert "tp-met" not in more and "tp-well" not in more
    assert 'data-view="month"' in more and 'data-view="period"' in more
    assert 'id="sport-filters"' in more and "adaptive.html" in more
    assert "loadWeekSummary(iso(mon))" in HTML  # la fuente de datos se conserva


def test_build_345():
    assert re.search(r"BUILD_VERSION = '(34[5-9]|3[5-9]\d|[4-9]\d\d)'", SW)
