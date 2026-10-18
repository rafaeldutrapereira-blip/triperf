"""
Pulido Free: en Equipo no se ven bicicletas y en Comunidad no hay editor ni
acciones de escritura para plan Free (basic). En vez de errores 403.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEAR = (ROOT / "gear.html").read_text(encoding="utf-8")
COMMUNITY = (ROOT / "community.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")


def test_gear_oculta_bicis_para_free():
    assert "lx-free [data-main=\"bikes\"],.lx-free #pane-bikes{display:none !important}" in GEAR


def test_community_oculta_escritura_para_free():
    for sel in ("#post-form-wrap", ".kudo-btn", ".comment-toggle", ".follow-btn",
                "[onclick*=\"openCreate\"]", "[onclick*=\"joinChallenge\"]"):
        assert f".lx-free {sel}" in COMMUNITY or f".lx-free {sel}".replace('"', '"') in COMMUNITY, sel


def test_community_muestra_aviso_de_lectura():
    assert 'class="lx-free-note" data-i18n="cmw_free_read_only"' in COMMUNITY
    assert ".lx-free .lx-free-note{display:block}" in COMMUNITY


def test_deteccion_free_usa_el_plan_de_la_sesion():
    for page in (GEAR, COMMUNITY):
        assert "s.plan==='basic'" in page
        assert "classList.add('lx-free')" in page


def test_aviso_en_tres_idiomas():
    assert len(re.findall(r"^\s*cmw_free_read_only:", I18N, re.M)) == 3
