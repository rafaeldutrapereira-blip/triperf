"""
E2E-I18N-CLICK — Selector de idioma: clic real en la bandera (Sprint 0)
======================================================
Priority : CRITICAL
Markers  : smoke, critical
Coverage :
  TC-I18N-CLICK-001  Widget flotante (landing.html, sin sesión): clic en
                      la bandera PT cambia el idioma de verdad — no solo
                      inyectando localStorage.lx_lang, sino disparando el
                      evento 'click' del botón real.
  TC-I18N-CLICK-002  Widget de sidebar (dashboard.html, desktop): clic en
                      la bandera EN cambia el idioma y mueve la clase
                      'active' al botón correcto.
  TC-I18N-CLICK-003  Widget de topbar (dashboard.html, mobile): mismo
                      comportamiento en el contexto de inyección móvil.

Regresión directa del bug real encontrado el 2026-10-12: `_buildWidget()`
marcaba PT/EN con `lx-lang-soon` ("— Próximamente") y ningún botón tenía
`addEventListener('click', ...)` — un usuario real NUNCA pudo cambiar de
idioma clickeando la UI, aunque el contenido ya estuviera traducido. Los
tests de `test_13_i18n_dynamic.py` no lo detectaban porque inyectan
`localStorage.lx_lang` directamente, sin pasar por el botón.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from e2e.conftest import BASE_URL


def _inject_auth(page: Page, token: str):
    page.evaluate(f"""() => {{
        localStorage.setItem('lx_co_token', '{token}');
        localStorage.setItem('lx_co_rol', 'atleta');
        localStorage.setItem('lx_co_nombre', 'Athlete E2E');
        localStorage.setItem('lx_ath_token', '{token}');
        // Evita el redirect a onboarding.html: en una corrida aislada (no la
        // suite completa) la cuenta compartida TEST_ATHLETE puede no tener
        // onboarding_completed_at todavía — acá se simula un usuario real
        // que ya onboardeó, que es el escenario que este test quiere cubrir.
        localStorage.setItem('lx_onboarding_done', '1');
        const sess = {{
            username: 'e2e', name: 'Athlete E2E',
            initials: 'AE', role: 'Atleta',
            plan: 'elite', api_rol: 'atleta',
            user_id: 'e2e', ts: Date.now()
        }};
        sessionStorage.setItem('kl_s', JSON.stringify(sess));
        localStorage.setItem('kl_s', JSON.stringify(sess));
    }}""")


@pytest.mark.smoke
@pytest.mark.critical
def test_floating_widget_flag_click_switches_language(page: Page):
    """
    Given: un visitante anónimo en landing.html (sin sidebar/topbar —
           usa el widget flotante)
    When:  hace clic (de verdad, no localStorage) en la bandera PT
    Then:  el botón "Ingresar" pasa a "Entrar", localStorage.lx_lang
           queda en 'pt', la bandera PT gana la clase 'active' y la ES
           la pierde — sin errores de consola.
    """
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(f"{BASE_URL}/landing.html")
    page.wait_for_selector("#lx-lang-sw", timeout=10000)

    login_btn = page.locator("#nav-login")
    expect(login_btn).to_have_text("Ingresar")

    es_btn = page.locator("#lx-lang-sw .lx-lang-btn[data-lang='es']")
    pt_btn = page.locator("#lx-lang-sw .lx-lang-btn[data-lang='pt']")
    expect(es_btn).to_have_class("lx-lang-btn active")

    pt_btn.click()

    expect(login_btn).to_have_text("Entrar", timeout=5000)
    expect(pt_btn).to_have_class("lx-lang-btn active")
    expect(es_btn).not_to_have_class("lx-lang-btn active")

    stored_lang = page.evaluate("() => localStorage.getItem('lx_lang')")
    assert stored_lang == "pt", f"localStorage.lx_lang no se actualizó al hacer clic: {stored_lang!r}"

    assert not errors, f"JS errors al cambiar idioma por clic (floating/pt): {errors}"


@pytest.mark.smoke
@pytest.mark.critical
def test_sidebar_widget_flag_click_switches_language(page: Page, athlete_api):
    """
    Given: un atleta logueado en dashboard.html, viewport desktop
           (el widget se inyecta al fondo del sidebar)
    When:  hace clic en la bandera EN
    Then:  un texto conocido (el label del botón "Actualizar Plan",
           oculto pero igual traducido) pasa a inglés y la bandera EN
           queda activa.
    """
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)

    page.goto(f"{BASE_URL}/dashboard.html")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_selector("#sidebar #lx-lang-sw", timeout=20000)

    en_btn = page.locator("#sidebar #lx-lang-sw .lx-lang-btn[data-lang='en']")
    en_btn.click()

    label = page.locator("#btn-upgrade-label")
    expect(label).to_have_text("Update Plan", timeout=5000)
    expect(en_btn).to_have_class("lx-lang-btn active")

    stored_lang = page.evaluate("() => localStorage.getItem('lx_lang')")
    assert stored_lang == "en", f"localStorage.lx_lang no se actualizó al hacer clic: {stored_lang!r}"

    assert not errors, f"JS errors al cambiar idioma por clic (sidebar/en): {errors}"


@pytest.mark.smoke
@pytest.mark.critical
def test_topbar_widget_flag_click_switches_language(page: Page, athlete_api):
    """
    Given: un atleta logueado en dashboard.html, viewport mobile
           (el widget se inyecta en el topbar, antes del avatar)
    When:  hace clic en la bandera PT
    Then:  mismo comportamiento que en sidebar — confirma que los 3
           contextos de inyección (`_injectWidget()`) quedan arreglados,
           no solo uno.
    """
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)

    page.goto(f"{BASE_URL}/dashboard.html")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_selector("#lx-lang-sw-tb", timeout=20000)

    pt_btn = page.locator("#lx-lang-sw-tb .lx-lang-btn[data-lang='pt']")
    pt_btn.click()

    label = page.locator("#btn-upgrade-label")
    expect(label).to_have_text("Atualizar Plano", timeout=5000)
    expect(pt_btn).to_have_class("lx-lang-btn active")

    stored_lang = page.evaluate("() => localStorage.getItem('lx_lang')")
    assert stored_lang == "pt", f"localStorage.lx_lang no se actualizó al hacer clic: {stored_lang!r}"

    assert not errors, f"JS errors al cambiar idioma por clic (topbar/pt): {errors}"
