"""
Pulido Free: en Equipo no se ven bicicletas y en Comunidad no hay editor ni
acciones de escritura para plan Free (basic). En vez de errores 403.

Los asserts comparan con `squash()` (ver text_match.py): el CSS del repo pasÃ³
por Prettier y ahora estÃ¡ expandido y con comillas simples, pero las reglas y
los selectores son los mismos.
"""
import re
from pathlib import Path

from .text_match import squash

ROOT = Path(__file__).resolve().parents[2]
GEAR = (ROOT / "gear.html").read_text(encoding="utf-8")
COMMUNITY = (ROOT / "community.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")


def test_gear_bicis_para_free_muestra_invitacion_no_oculta():
    # W14/D9: el tab de Bicicletas ya no se oculta; Basico ve la invitacion a subir de plan
    g = squash(GEAR)
    assert squash('.lx-free [data-main="bikes"]') not in g
    assert squash(".lx-free #bikes-upgrade{display:block") in g
    assert squash(".lx-free #bikes-body{display:none") in g


def test_community_oculta_escritura_para_free():
    for sel in ("#post-form-wrap", ".kudo-btn", ".comment-toggle", ".follow-btn",
                '[onclick*="openCreate"]', '[onclick*="joinChallenge"]'):
        assert squash(f".lx-free {sel}") in squash(COMMUNITY), sel


def test_community_muestra_aviso_de_lectura():
    assert (
        squash('class="lx-free-note" data-i18n="cmw_free_read_only"')
        in squash(COMMUNITY)
    )
    assert squash(".lx-free .lx-free-note{display:block") in squash(COMMUNITY)


def test_deteccion_free_usa_el_plan_de_la_sesion():
    for page in (GEAR, COMMUNITY):
        assert squash("s.plan==='basic'") in squash(page)
        assert squash("classList.add('lx-free')") in squash(page)


def test_aviso_en_tres_idiomas():
    assert len(re.findall(r"^\s*cmw_free_read_only:", I18N, re.M)) == 3
