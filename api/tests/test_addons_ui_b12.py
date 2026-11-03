"""
B12/P9 — "Mi plan" en Perfil: tarjeta al final de la pestaña, colapsada por
defecto, con tres grupos (incluidos / comprables / próximamente) y nombres
traducidos en el cliente.

Contrato estático del HTML (la lógica de cobro está en test_addons_b12.py).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILE = (ROOT / "athlete_profile.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")


def test_perfil_tiene_tarjeta_mi_plan():
    assert 'id="addons-list"' in PROFILE
    assert 'data-i18n="addon_card_title"' in PROFILE
    assert 'id="myplan-toggle"' in PROFILE


def test_tarjeta_vive_en_cuenta_fuera_de_mis_datos():
    # W13: "Mi plan"/addons salen de la primera pantalla y van a la pestana Cuenta.
    assert PROFILE.index('id="tab-seguridad"') < PROFILE.index('id="addons-list"')
    mis_datos = PROFILE[PROFILE.index('id="tab-perfil"'):PROFILE.index('id="tab-conexiones"')]
    assert 'id="addons-list"' not in mis_datos


def test_addons_usan_los_endpoints_de_stripe():
    assert "fetch(API + '/stripe/addons'" in PROFILE
    assert "fetch(API + '/stripe/addons/checkout'" in PROFILE
    assert "window.location.href = d.checkout_url" in PROFILE


def test_arranca_colapsada_y_se_expande_con_el_toggle():
    assert 'id="addons-list" class="mp-detail" hidden' in PROFILE
    assert "function toggleMyPlan()" in PROFILE
    assert "box.hasAttribute('hidden')" in PROFILE
    assert "aria-expanded" in PROFILE
    # El botón cambia de clave i18n al expandir (Ver detalle / Ocultar).
    assert "'myplan_hide_detail'" in PROFILE
    assert "'myplan_see_detail'" in PROFILE


def test_tres_grupos_con_las_reglas_de_siempre():
    # incluidos / comprables / el resto — mismas condiciones que antes.
    assert "if (a.included) inc.push(a);" in PROFILE
    assert "else if (a.available && d.enabled && a.price_configured)" in PROFILE
    assert "else soon.push(a);" in PROFILE


def test_incluido_no_lleva_boton():
    incluidos = PROFILE.split("if (inc.length) {")[1].split("if (buy.length)")[0]
    assert "buyAddon" not in incluidos
    assert "addon_included" in incluidos


def test_proximamente_es_una_sola_linea():
    proximos = PROFILE.split("if (soon.length)")[1].split("box.innerHTML")[0]
    assert "soon.map(nameOf).join(', ')" in proximos
    assert "mp-soon" in proximos


def test_precio_solo_si_el_payload_lo_trae():
    # No se inventa un monto: sin campo `price` no se pinta nada.
    assert "var p = a.price;" in PROFILE
    assert "if (!p) return '';" in PROFILE


def test_nombres_de_addons_se_traducen_por_id():
    assert "MP_ADDON_NAMES" in PROFILE
    for aid in (
        "asistente_ia",
        "labs",
        "estrategia_carrera",
        "protocolos_mentales",
        "indoor",
        "ajustes_adaptativos",
        "rendimiento_avanzado",
        "retrospectiva",
    ):
        assert aid + ": 'myplan_addon_" in PROFILE, aid


def test_claves_de_mi_plan_en_tres_idiomas():
    claves = (
        "addon_card_title",
        "myplan_included",
        "myplan_available",
        "myplan_see_detail",
        "myplan_hide_detail",
        "myplan_summary_one",
        "myplan_summary_many",
        "myplan_summary_none",
        "myplan_addon_asistente_ia",
        "myplan_addon_labs",
        "myplan_addon_estrategia",
        "myplan_addon_mentales",
        "myplan_addon_indoor",
        "myplan_addon_adaptativos",
        "myplan_addon_rendimiento",
        "myplan_addon_retrospectiva",
        "addon_buy",
        "addon_soon",
        "addon_included",
    )
    for k in claves:
        assert len(re.findall(r"^\s*" + k + r":", I18N, re.M)) == 3, k
