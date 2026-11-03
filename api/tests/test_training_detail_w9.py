"""W9: training_detail.html - KPIs en capas y graficos 2 + "Mas graficos"."""
import re
from pathlib import Path

from .text_match import squash

ROOT = Path(__file__).resolve().parents[2]
SRC = (ROOT / "training_detail.html").read_text(encoding="utf-8")
S = squash(SRC)


def test_first_view_has_exactly_three_plain_kpis():
    m = re.search(r"var mainKpis = \[(.*?)\n\s*\];", SRC, re.S)
    assert m, "mainKpis no encontrado"
    body = m.group(1)
    assert len(re.findall(r"lbl:", body)) == 2  # duracion + distancia
    assert "effortKpi" in body  # + esfuerzo = 3
    assert "tdw_kpi_duration" in body and "tdw_kpi_distance" in body
    assert not re.search(r"\b(?:np|ifv)\b", body)
    assert 'document.getElementById("act-kpis").innerHTML=_kpiHtml(mainKpis)' in S


def test_effort_kpi_uses_real_power_or_hr():
    assert 'ACT.sport==="bike"&&ACT.avg_power' in S
    assert 'val:ACT.avg_hr||"—"' in S


def test_np_if_te_live_inside_more_data_details():
    d = re.search(r'<details class="ah-more" id="act-more">(.*?)</details>', SRC, re.S)
    assert d
    body = d.group(1)
    assert 'id="act-kpis-more"' in body and 'id="act-te"' in body
    assert 'id="act-kpis"' not in body
    assert "val: np || '???'" in SRC and "ifv" in SRC
    assert 'getElementById("act-kpis-more").innerHTML=_kpiHtml(kpis)' in S


def test_plain_names_keep_acronym():
    i18n = (ROOT / "i18n.js").read_text(encoding="utf-8")
    for frag in (
        "Potencia sostenida (NP)",
        "Intensidad vs. tu umbral (IF)",
        "Efecto del entrenamiento (TE)",
        "Ver más datos",
        "Más gráficos",
    ):
        assert frag in i18n
    for k in ("tdw_more_data", "tdw_more_charts", "tdw_kpi_distance", "tdw_kpi_power_avg"):
        assert i18n.count(k + ":") == 3


def test_no_duplicate_sport_badge_in_meta():
    meta = SRC[SRC.index("getElementById('act-meta').innerHTML") :]
    meta = meta[: meta.index("// KPI Cards")]
    assert 'class="badge' not in meta and "sp.badge" not in meta


def test_charts_default_two_rest_under_more_charts():
    assert 'id="charts-more"' in SRC and "tdw_more_charts" in SRC
    assert len(re.findall(r"var _pEnd = blocks\.length", SRC)) == 1
    hr = SRC.index("var _pEnd = blocks.length")
    assert hr < SRC.index("tdw_chart_name_cadence")
    sp = SRC.index("_pEnd = blocks.length; // carrera")
    assert SRC.index("tdw_chart_name_speed") < sp < SRC.index("tdw_chart_name_stride_length")
