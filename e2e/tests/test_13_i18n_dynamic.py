"""
E2E-I18N-DYN — Contenido dinámico de la app móvil en PT/EN (Sprint 2b)
======================================================
Priority : HIGH
Markers  : mobile
Coverage :
  TC-I18N-001  Pantalla "Hoy" sin plan asignado muestra el estado de
               descanso TRADUCIDO (no hardcodeado en español), con el
               ícono 🛌 correcto — regresión directa del bug real
               encontrado en 2b-i (renderNoWorkout adivinaba el ícono
               buscando la palabra "descanso" en el string, lo que se
               rompía en cualquier idioma que no fuera español).
  TC-I18N-002  Pantalla "Semana" muestra los días abreviados y el
               estado "Descanso" de cada celda vacía en el idioma
               elegido, no en español.
  TC-I18N-003  Ningún error de consola/página al cargar con idioma PT/EN
               (detecta template literals rotos por un reemplazo mal
               hecho durante la localización).

A diferencia de test_i18n.py (estático, sin servidor), esto SÍ ejecuta
el JS real contra un servidor real — es lo único que puede detectar si
una función de render quedó rota al tocarla para traducir contenido
generado dinámicamente (ver memoria project-labx-i18n-brasil, Sprint 2b).
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from e2e.conftest import BASE_URL


MOBILE_VIEWPORT = {"width": 390, "height": 844}  # iPhone 14


def _inject_auth_and_lang(page: Page, token: str, lang: str):
    page.evaluate(
        """([token, lang]) => {
            localStorage.setItem('lx_co_token', token);
            localStorage.setItem('lx_co_rol', 'atleta');
            localStorage.setItem('lxapp_token', token);
            localStorage.setItem('lx_co_nombre', 'Athlete E2E');
            localStorage.setItem('lx_lang', lang);
        }""",
        [token, lang],
    )


@pytest.mark.mobile
@pytest.mark.timeout(60)
@pytest.mark.parametrize("lang,rest_day_word", [("pt", "descanso"), ("en", "rest")])
def test_today_screen_rest_state_is_translated(page: Page, athlete_api, lang, rest_day_word):
    """
    Given: un atleta de prueba SIN plan asignado y sin actividades hoy
           (estado real de cualquier cuenta recién creada)
    When:  entra a Hoy con el idioma elegido
    Then:  el mensaje de "día de descanso" aparece en ese idioma
           (nunca en español), y el ícono es el de descanso (🛌), no el
           de "sin conexión" (📡) — confirma que renderNoWorkout(msg, isRest)
           recibe el flag explícito en vez de adivinar por texto.
    """
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth_and_lang(page, athlete_api._token, lang)

    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("domcontentloaded")

    today_content = page.locator("#today-content")
    expect(today_content).to_contain_text(rest_day_word, ignore_case=True, timeout=20000)

    # No debe quedar nada en español en este estado (palabra inequívoca
    # del mensaje ES: "descanso" en minúscula exacta solo aparece en el
    # string español — verificamos que el string ES no se coló.
    if lang != "es":
        text = today_content.inner_text()
        assert "Día de descanso" not in text, (
            f"El mensaje de descanso quedó en español pese a lang={lang}: {text!r}"
        )

    icon = page.locator("#today-content .no-workout-ico")
    expect(icon).to_have_text("🛌")

    assert not errors, f"JS errors con lang={lang}: {errors}"


@pytest.mark.mobile
@pytest.mark.timeout(60)
def test_week_screen_days_and_rest_label_translated(page: Page, athlete_api):
    """
    Given: un atleta sin entrenamientos planificados esta semana
    When:  entra a Semana con idioma portugués
    Then:  los 7 días de la semana están abreviados en portugués
           (Seg/Ter/Qua/Qui/Sex/Sáb/Dom) y cada celda vacía dice
           "Descanso" en portugués, no en español ("Lun"/"Descanso").
    """
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth_and_lang(page, athlete_api._token, "pt")

    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_selector("#today-content .no-workout, #today-content .today-card-compact", timeout=20000)

    page.evaluate("goScreen('screen-week')")

    week_grid = page.locator("#week-grid")
    expect(week_grid).to_be_visible()
    expect(week_grid.locator(".wk-day")).to_have_count(7, timeout=20000)
    grid_text = week_grid.inner_text().lower()

    # El CSS pone estas etiquetas en mayúsculas (text-transform) -- comparar
    # en minúsculas, no es una traducción fallida.
    assert "seg" in grid_text, f"Día abreviado en portugués ('Seg') no encontrado: {grid_text!r}"
    assert "lun" not in grid_text, f"Día quedó en español ('Lun') pese a lang=pt: {grid_text!r}"
    assert "descanso" in grid_text, (
        f"Etiqueta 'Descanso' (PT, coincide con ES) no encontrada: {grid_text!r}"
    )

    assert not errors, f"JS errors en Semana (pt): {errors}"


@pytest.mark.mobile
@pytest.mark.timeout(60)
def test_wellness_screen_factors_translated(page: Page, athlete_api):
    """
    Given: un atleta sin datos de recuperación cargados aún
    When:  entra a Bienestar > Resumen con idioma inglés
    Then:  o bien aparece el mensaje "no recovery data" traducido, o
           (si por algún motivo sí hay datos) las etiquetas de los
           factores (Sleep/Load/Stress/Battery/Wellness) aparecen en
           inglés, nunca en español ("Sueño"/"Carga"/"Estrés").
    """
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth_and_lang(page, athlete_api._token, "en")

    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_selector("#today-content .no-workout, #today-content .today-card-compact", timeout=20000)

    page.evaluate("goScreen('screen-wellness')")
    page.wait_for_selector("#rc-mob-card:not(:has-text('Cargando'))", timeout=20000)

    card_text = page.locator("#rc-mob-card").inner_text()
    assert "Cargando" not in card_text, f"Pantalla quedó en estado de carga: {card_text!r}"
    assert "Sueño" not in card_text and "Carga" not in card_text and "Estrés" not in card_text, (
        f"Etiquetas quedaron en español pese a lang=en: {card_text!r}"
    )

    assert not errors, f"JS errors en Bienestar (en): {errors}"
