"""
W5 - detalle.html: heroe en lenguaje llano (P11) y recortes.

Pruebas estaticas (tolerantes al formato con squash).
"""
import os
import re

from api.tests.text_match import squash

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


HTML = _read("detalle.html")


def _pmc_hero_block():
    i = HTML.index("if (metric === 'pmc') {\r\n          // W5") if "\r\n" in HTML else HTML.index("if (metric === 'pmc') {\n          // W5")
    j = HTML.index("heroPmcExtras(pAll);", i)
    return HTML[i:j]


def test_heroe_muestra_titular_llano_y_una_sola_cifra():
    sq = squash(HTML)
    assert squash("function pmcHeadline(tsb)") in sq
    assert squash("Estás en forma para entrenar fuerte") in sq
    assert squash("Estás acumulando fatiga") in sq
    blk = squash(_pmc_hero_block())
    # una sola cifra principal (condicion fisica) rotulada en llano, con variacion
    assert blk.count('getElementById("hero-val").textContent') == 1
    assert squash("dtw_hero_fitness_label") in blk
    assert squash("ctlDelta") in blk


def test_siglas_no_aparecen_en_el_texto_principal_del_heroe():
    blk = re.sub(r"//[^\n]*", "", _pmc_hero_block())
    for sigla in ("CTL", "ATL", "TSB"):
        assert sigla not in blk, sigla
    # el unit del heroe ya no es ' CTL'
    assert "' CTL'" not in HTML
    # las siglas viven en la capa 2 (details "Ver detalle") con su nombre llano
    assert 'id="hero-detail"' in HTML
    assert squash("dtw_mc_atl_name") in squash(HTML[HTML.index("function heroPmcExtras"):])
    # sin linea de promedio redundante en el heroe
    assert "heroAvgLine" not in HTML
    assert "hero-avg" not in HTML


def test_comparar_ciclos_nace_plegado():
    m = re.search(r'<details class="cc-fold" id="cc-fold"([^>]*)>', HTML)
    assert m, "Comparar Ciclos debe estar en un <details>"
    assert "open" not in m.group(1)
    assert "dtw_cc_fold_title" in HTML
    # el cierre esta dentro del contenedor y los controles siguen presentes
    assert HTML.index("</details>", HTML.index('id="cc-fold"')) > HTML.index('id="cc-empty"')
    assert "initCycleCompare" in HTML


def test_cuatro_botones_de_periodo_principales():
    bar = HTML[HTML.index('class="period-tabs"'):HTML.index("<!-- CONTENT -->")]
    # quitar la seccion secundaria "Mas" y el rango personalizado
    main = re.sub(r'<details class="period-more".*?</details>', "", bar, flags=re.S)
    ps = re.findall(r'<button[^>]*data-p="(\d+)"', main)
    assert ps == ["90", "180", "365", "0"]
    # Semana/Mes siguen soportados como opcion secundaria
    sec = re.search(r'<details class="period-more".*?</details>', bar, flags=re.S).group(0)
    assert 'data-p="7"' in sec and 'data-p="30"' in sec


def test_pmc_sin_progreso_semanal_ni_otras_metricas():
    assert squash("var WP_LOAD_METRICS = ['ctl', 'atl', 'tsb', 'tss', 'acwr']") in squash(HTML)
    assert "'pmc'];" not in re.search(r"var WP_LOAD_METRICS.*", HTML).group(0)
    assert squash("rw.style.display = metric === 'pmc' ? 'none' : ''") in squash(HTML)


def test_insights_pmc_en_llano_y_sin_meta_generica():
    sq = squash(HTML)
    assert squash("'CTL <em>'") not in sq
    assert squash("'Ratio ATL/CTL actual: <em>'") not in sq
    assert "dtw_race_target'" not in HTML  # solo existe la variante con carrera real
    assert squash("dtwRaceTargetInsight()") in sq


def test_i18n_claves_nuevas_en_los_tres_idiomas():
    i18n = _read("i18n.js")
    for key in ("dtw_hero_h_ready", "dtw_hero_h_build", "dtw_hero_fitness_label",
                "dtw_hero_see_detail", "dtw_cc_fold_title", "dtw_period_more"):
        assert len(re.findall(r"\b%s:" % key, i18n)) == 3, key


def test_sw_build_269():
    m = re.search(r"var BUILD_VERSION = '(\d+)'", _read("sw.js"))
    assert m and int(m.group(1)) >= 269
