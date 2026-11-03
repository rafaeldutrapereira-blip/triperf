"""W8: Nutricion directa (3 KPIs, Gasto semanal al final, Intensidad en 2 capas)."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def test_tres_kpis_principales_y_sin_chips():
    src = _read("nutrition.html")
    grid = src[src.index('id="kpi-grid"'):src.index('id="kpi-more"')]
    assert grid.count('class="kpi"') == 3
    for i in ("kpi-time", "kpi-cho-hr", "kpi-fluid-hr"):
        assert 'id="%s"' % i in grid
    assert 'class="ph-chips"' not in src and 'class="chip ' not in src
    for i in ("ch-time", "ch-energy", "ch-cph", "ch-ratio"):
        assert 'id="%s"' % i not in src
    # el resto de cifras sigue existiendo, pero plegado
    more = src[src.index('id="kpi-more"'):src.index("<!-- Tabs -->")]
    assert "<details" in src[src.index('id="kpi-more"') - 40:src.index('id="kpi-more"') + 40]
    for i in ("kpi-kcal", "kpi-cho", "kpi-fluid", "kpi-na", "kpi-ratio"):
        assert 'id="%s"' % i in more


def test_gasto_semanal_ya_no_es_primero():
    src = _read("nutrition.html")
    assert src.index('id="race-src-card-host"') < src.index('id="kpi-grid"')
    assert src.index('id="kpi-grid"') < src.index('id="ch-weekly"')
    assert src.index('id="tab-post"') < src.index('id="ch-weekly"')
    assert src.index('id="plan-tbody"') < src.index('id="sec-my-week"')


def test_sliders_finos_nacen_plegados():
    src = _read("nutrition.html")
    m = re.search(r'<details[^>]*id="if-fine"[^>]*>', src)
    assert m and " open" not in m.group(0).replace("onchange", "")
    fine = src[m.start():src.index("</details>", m.start())]
    for i in ("if-bike-slider", "if-run-slider", "if-elev-bike-slider", "if-elev-run-slider",
              "if-wind-slider", "if-alt-slider", "if-temp-slider", "if-surface", "sel-sweat"):
        assert 'id="%s"' % i in fine, i
    # capa 1 visible (fuera del details): terreno y calor
    assert m.start() > src.index('id="if-terrain-quick"') > 0
    assert src.index('id="if-heat-quick"') < m.start()
    assert 'id="if-terrain-quick"' not in fine


def test_perfil_incompleto_w2_sigue_y_calculo_intacto():
    src = _read("nutrition.html")
    assert "nutProfileReady" in src and "nutRenderIncomplete" in src
    assert "athlete_profile.html" in src
    assert "window.print()" in src
    assert "precise-splits" in src and 'id="plan-table"' in src


def test_i18n_claves_w8_en_tres_idiomas():
    i18n = _read("i18n.js")
    src = _read("nutrition.html")
    keys = ("nut_kpi_cho_hr", "nut_kpi_fluid_hr", "nut_more_figures", "nut_terrain",
            "nut_terrain_flat", "nut_terrain_rolling", "nut_terrain_hilly", "nut_heat",
            "nut_heat_normal", "nut_heat_high", "nut_fine_tune", "nut_th_cho",
            "nut_kpi_time", "nut_kpi_cho_total", "nut_kpi_fluid", "nut_kpi_sodium",
            "nut_kpi_ratio", "nut_if_btn")
    for k in keys:
        assert len(re.findall(r"^\s*%s:" % k, i18n, re.M)) == 3, k
    for k in set(re.findall(r'data-i18n="(nut_(?:kpi|terrain|heat|fine|more|th_cho)[a-z_]*)"', src)):
        assert len(re.findall(r"^\s*%s:" % k, i18n, re.M)) == 3, k
    assert "CHO/h" not in src
