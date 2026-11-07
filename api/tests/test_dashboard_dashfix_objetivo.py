"""DASHFIX: el dashboard muestra la etiqueta del objetivo, no el codigo crudo + km."""
import re
from pathlib import Path

from api.tests.text_match import squash

ROOT = Path(__file__).resolve().parents[2]
DASH = (ROOT / "dashboard.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")


def test_no_concatena_codigo_crudo_ni_sufijo_km():
    assert not re.search(r"race_goal_dist\s*\+", DASH)
    assert "profile.race_goal_dist+'km'" not in squash(DASH)


def test_703_resuelve_a_etiqueta_half_113():
    s = squash(DASH)
    assert '"70.3":["prof_opt_703"' in s
    assert "70.3/Half(113km)" in s
    assert len(re.findall(r"prof_opt_703: '70\.3 / Half \(113 km\)'", I18N)) == 3


def test_full_y_codigos_running_mapeados():
    s = squash(DASH)
    # CARRERAS-DASHBOARD: los codigos legacy resuelven por alias al mapa unico
    for frag in ('full:"ironman"', '"21k":"half_marathon"', '"42k":"marathon"',
                 '"703":"70.3"', 'sprint:["prof_opt_sprint"',
                 'olympic:["prof_opt_olympic"'):
        assert frag in s


def test_codigo_desconocido_cae_a_otro_nunca_al_codigo_crudo():
    assert '_RACE_DIST_ALIAS[code]||"other"' in squash(DASH)
