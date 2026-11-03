"""W10: integridad restante - sin cifras a mano, sin claims de IA al atleta,
registro solo atleta, dashboard sin datos ajenos, onboarding con error visible."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _src(name):
    return (ROOT / name).read_text(encoding="utf-8")


def _body(name):
    return re.sub(r"<script.*?</script>|<style.*?</style>", "", _src(name), flags=re.S)


def test_landing_login_sin_cifras_a_mano():
    for f in ("landing.html", "login.html"):
        b = _body(f)
        assert "4132" not in b
        assert "500<span" not in b
        assert not re.search(r">\s*10<span", b)
        assert 'class="hero-stats"' not in b and 'class="bp-kpis"' not in b
    assert "5:48" not in _body("login.html")


def test_landing_sin_claims_de_ia_al_atleta():
    b = _body("landing.html")
    assert not re.search(r"\bIA\b|AI Assistant", b)
    i18n = _src("i18n.js")
    for key in ("lnd_hero_desc_html", "lnd_strip_6", "lnd_card5_t", "lnd_how4_d"):
        lines = re.findall(r"\b%s: [^\n]*" % key, i18n)
        assert len(lines) == 3, key  # ES, PT, EN
        for line in lines:
            seg = line.split("', lnd_")[0]
            assert not re.search(
                r"Asistente IA|Assistente IA|AI Assistant|AI Assistanting", seg
            ), key


def test_registro_sin_selector_de_rol():
    s = _src("registro.html")
    assert 'name="rol"' not in s
    assert "selectRole" not in s and "_currentRole" not in s
    assert 'data-i18n="reg_athlete_note"' in s
    assert "rol: 'atleta'" in s


def test_dashboard_sin_datos_ajenos():
    s = _src("dashboard.html")
    assert "+3.2" not in s
    assert not re.search(r'id="kl-greeting-name">\s*[^<\s]', s)
    assert "|| 240" not in s and "|| 180" not in s
    m = re.search(r"function eTSS\(a\) \{(.*?)\n        \}\n", s, re.S)
    assert m
    assert "h * 50" not in m.group(1) and "'???'" in m.group(1)


def test_onboarding_avisa_si_falla_el_guardado():
    s = _src("onboarding.html")
    assert 'id="finish-err"' in s
    m = re.search(r"async function saveProfileData\(\) \{(.*?)\n      \}\n", s, re.S)
    assert m and "catch (e) {}" not in m.group(1) and "return r.ok" in m.group(1)
    f = re.search(r"async function finish\(\) \{(.*?)\n      \}\n", s, re.S).group(1)
    assert f.index("if (!saved)") < f.index("lx_onboarding_done")
    assert "onb_save_error" in _src("i18n.js")


def test_comunidad_tuteo_y_plan_basico():
    s = _src("community.html") + _src("i18n.js")
    assert "Mejorá" not in s and "Plan Free" not in s
    assert "Plan Básico: estás viendo" in s
    assert "Plano Básico" in s and "Basic plan: you are viewing" in s
