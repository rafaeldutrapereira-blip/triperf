"""C3 — Race Day de la app = 1 vista (dashboard) + enlace al plan completo en la web."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HTML = open(os.path.join(ROOT, "athlete-app.html"), encoding="utf-8").read()
I18N = open(os.path.join(ROOT, "i18n.js"), encoding="utf-8").read()


def _screen():
    a = HTML.index('id="screen-raceday"')
    return HTML[a:HTML.index('id="screen-progress"', a)]


def test_sin_pestanas_ni_plan_ni_nutricion():
    s = _screen()
    for gone in ("rd-tab-", "rd-nutrition-content", "rd-plan-content", "cm-tabs"):
        assert gone not in s
    for gone in ("rdBuildPlan", "loadRaceDayPlan", "loadRaceDayNutrition", "RD_NUT_GUIDELINES"):
        assert gone not in HTML


def test_boton_ver_plan_completo_usa_puente_p0():
    s = _screen()
    assert "abrirEnWeb('race_day')" in s
    assert "rd-dash-card" in s
    assert "function loadRaceDayDashboard" in HTML
    assert I18N.count("app_raceday_full_plan") == 3
