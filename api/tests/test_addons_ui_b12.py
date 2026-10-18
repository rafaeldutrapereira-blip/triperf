"""
B12 — Pantalla de compra de addons en Perfil: tarjeta, carga del catálogo y
checkout. Contrato estático (la lógica de cobro está en test_addons_b12.py).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILE = (ROOT / "athlete_profile.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")


def test_perfil_tiene_tarjeta_de_addons():
    assert 'id="addons-list"' in PROFILE
    assert 'data-i18n="addon_card_title"' in PROFILE


def test_addons_usan_los_endpoints_de_stripe():
    assert "fetch(API + '/stripe/addons'" in PROFILE
    assert "fetch(API + '/stripe/addons/checkout'" in PROFILE
    assert "window.location.href = d.checkout_url" in PROFILE


def test_sin_flag_no_se_ofrece_compra():
    # Si la API no está habilitada, la tarjeta muestra "próximamente", no el botón.
    assert "!a.available || !d.enabled || !a.price_configured" in PROFILE


def test_incluido_no_se_vende_de_nuevo():
    assert "a.included" in PROFILE


def test_claves_de_addons_en_tres_idiomas():
    for k in ("addon_card_title", "addon_included", "addon_buy", "addon_soon", "addon_err"):
        assert len(re.findall(r"^\s*" + k + r":", I18N, re.M)) == 3, k
