"""W6 - race_day.html: una sola pantalla util (2 pestanas, auto-plan sin formulario)."""
import os
import re
from html.parser import HTMLParser

from api.tests.text_match import squash

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


SRC = _read("race_day.html")


def test_exactamente_dos_pestanas():
    assert len(re.findall(r'class="tab-btn[ "]', SRC)) == 2
    assert len(re.findall(r'class="tab-panel[ "]', SRC)) == 2
    assert "switchTab('main')" in SRC and "switchTab('races')" in SRC


def test_sin_pestana_nutricion_pero_enlace_contextual():
    assert 'id="tab-nutrition"' not in SRC
    assert "switchTab('nutrition')" not in SRC
    assert "rd_tab_nutrition" not in SRC
    assert 'id="nutrition-link"' in SRC and 'href="nutrition.html' in SRC
    # el enlace vive dentro del detalle del plan generado
    assert SRC.index('id="plan-results"') < SRC.index('id="nutrition-link"') < SRC.index('id="tab-races"')


def test_boton_principal_llama_auto_plan_sin_formulario():
    s = squash(SRC)
    assert 'id="btn-auto-plan"onclick="generatePlan(false)"' in s
    i = SRC.index("function generatePlan(")
    body = squash(SRC[i:SRC.index("function buildAdvancedPayload(")])
    assert "advanced?buildAdvancedPayload():{}" in body
    assert "/races/auto-plan" in SRC
    assert "generatePlan(true)" in SRC  # el avanzado sigue mandando parametros


def test_ajustes_avanzados_nacen_plegados_y_contienen_el_formulario():
    m = re.search(r'<details[^>]*id="rd-advanced"[^>]*>', SRC)
    assert m and " open" not in m.group(0)
    det = SRC[m.start():SRC.index("</details>", m.start())]
    for fid in ("plan-race-type", "plan-ftp", "plan-weight", "plan-sweat", "plan-if-bike",
                "plan-if-run", "plan-gpx-bike", "plan-gpx-run", "plan-wind", "plan-altitude",
                "plan-temp", "plan-surface", "plan-water", "plan-goal"):
        assert 'id="%s"' % fid in det, fid
    assert "/races/parse-gpx" in SRC


def test_sin_chips_de_fitness_ni_ultimas_carreras():
    for k in ("dash-ctl", "dash-tsb", "dash-atl", "dash-rec", "dash-history-list"):
        assert k not in SRC, k


def test_estado_vacio_un_solo_cta_al_perfil():
    assert 'id="rd-empty"' in SRC
    assert re.search(r'id="rd-empty-cta"[^>]*href="athlete_profile.html"', SRC)
    s = squash(SRC)
    assert "if(!nr.id)return;" in s


def test_mis_carreras_agrupa_historial_y_resultado():
    t = SRC[SRC.index('id="tab-races"'):]
    assert 'id="history-list"' in t and "saveResult()" in t and 'id="res-analysis-box"' in t


def test_html_balanceado():
    class P(HTMLParser):
        VOID = {"input", "br", "meta", "link", "img", "hr"}

        def __init__(self):
            super().__init__()
            self.stack, self.bad = [], []

        def handle_starttag(self, tag, attrs):
            if tag not in self.VOID:
                self.stack.append(tag)

        def handle_endtag(self, tag):
            if tag in self.VOID:
                return
            if not self.stack or self.stack[-1] != tag:
                self.bad.append((tag, self.getpos()))
            else:
                self.stack.pop()

    p = P()
    p.feed(SRC)
    assert not p.bad, p.bad[:3]
    assert p.stack == [], p.stack


def test_i18n_tres_idiomas_y_build():
    i18n = _read("i18n.js")
    for k in ("rd_tab_main", "rd_tab_races", "rd_btn_generate_update", "rd_advanced",
              "rd_btn_generate_adjusted", "rd_link_nutrition_plan", "rd_empty_title",
              "rd_empty_desc", "rd_empty_cta"):
        assert len(re.findall(r"\b%s:" % k, i18n)) == 3, k
    m = re.search(r"BUILD_VERSION = '(\d+)'", _read("sw.js"))
    assert m and int(m.group(1)) >= 270
