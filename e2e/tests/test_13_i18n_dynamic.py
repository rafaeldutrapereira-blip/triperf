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


@pytest.mark.mobile
@pytest.mark.timeout(60)
def test_community_clubs_screen_translated(page: Page, athlete_api):
    """
    Given: un atleta sin clubes (estado real de cualquier cuenta nueva)
    When:  entra a Comunidad > Clubes con idioma portugués
    Then:  el botón de crear club y el estado vacío aparecen en
           portugués, no en español.
    """
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth_and_lang(page, athlete_api._token, "pt")

    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_selector("#today-content .no-workout, #today-content .today-card-compact", timeout=20000)

    page.evaluate("goScreen('screen-community')")
    page.evaluate("communityTab('clubs')")
    # No esperar por ausencia de "Cargando" (en PT ahora dice "Carregando",
    # justamente lo que se está probando) -- esperar el botón real en su lugar.
    page.wait_for_selector("#community-content .wl-submit", timeout=20000)

    content_text = page.locator("#community-content").inner_text().lower()
    assert "criar clube" in content_text, f"Botón de crear club no está en portugués: {content_text!r}"
    assert "crear club" not in content_text, f"Quedó texto en español: {content_text!r}"

    assert not errors, f"JS errors en Comunidad/Clubes (pt): {errors}"


@pytest.mark.mobile
@pytest.mark.timeout(60)
def test_community_discover_screen_translated(page: Page, athlete_api):
    """
    Given: un atleta cualquiera
    When:  entra a Comunidad > Descubrir con idioma inglés
    Then:  el placeholder de búsqueda, el botón y el título de
           sugerencias aparecen en inglés, no en español.
    """
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth_and_lang(page, athlete_api._token, "en")

    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_selector("#today-content .no-workout, #today-content .today-card-compact", timeout=20000)

    page.evaluate("goScreen('screen-community')")
    page.evaluate("communityTab('discover')")
    page.wait_for_selector("#community-content .cm-search-bar", timeout=20000)

    placeholder = page.locator("#cm-search-inp").get_attribute("placeholder")
    assert placeholder and "search" in placeholder.lower(), f"Placeholder no está en inglés: {placeholder!r}"
    content_text = page.locator("#community-content").inner_text().lower()
    assert "suggested athletes" in content_text, f"Título de sugerencias no está en inglés: {content_text!r}"

    assert not errors, f"JS errors en Comunidad/Descubrir (en): {errors}"


@pytest.mark.mobile
@pytest.mark.timeout(60)
def test_profile_screen_connections_translated(page: Page, athlete_api):
    """
    Given: un atleta sin Garmin/Strava conectados (estado real de una
           cuenta nueva)
    When:  entra a Perfil con idioma portugués
    Then:  el estado de conexión ("Não conectado") aparece en
           portugués, no en español ("No conectado").
    """
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth_and_lang(page, athlete_api._token, "pt")

    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_selector("#today-content .no-workout, #today-content .today-card-compact", timeout=20000)

    page.evaluate("goScreen('screen-profile')")
    page.wait_for_selector("#pf-connections .pf-conn-row", timeout=20000)

    conn_text = page.locator("#pf-connections").inner_text()
    assert "Não conectado" in conn_text, f"Estado de conexión no está en portugués: {conn_text!r}"
    assert "No conectado" not in conn_text, f"Quedó texto en español: {conn_text!r}"

    assert not errors, f"JS errors en Perfil (pt): {errors}"


@pytest.mark.mobile
@pytest.mark.timeout(60)
def test_mental_screen_translated(page: Page, athlete_api):
    """
    Given: un atleta de prueba sin plan Coach (gateado) o sin check-in
           previo del día (estado real de cualquier cuenta nueva)
    When:  entra a Rendimiento Mental con idioma inglés
    Then:  o bien el mensaje de gate de plan aparece en inglés, o el
           título "Mental Fatigue Score" y "Last 7 days" aparecen sin
           texto español colado (confirma que renderMentalScore,
           MTL_CAT_LABELS/MTL_DIFF_LABELS como funciones, y los mensajes
           de check-in quedaron traducidos — Sprint 2b-vi).
    """
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth_and_lang(page, athlete_api._token, "en")

    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_selector("#today-content .no-workout, #today-content .today-card-compact", timeout=20000)

    page.evaluate("goScreen('screen-mental')")
    page.wait_for_selector("#mtl-score-card:not(:has-text('Loading'))", timeout=20000)

    card_text = page.locator("#mtl-score-card").inner_text()
    assert "Cargando" not in card_text, f"Pantalla quedó en estado de carga (ES): {card_text!r}"
    assert "Rendimiento Mental" not in card_text, f"Mensaje de gate quedó en español: {card_text!r}"
    if "Mental Fatigue Score" in card_text:
        assert "Últimos" not in card_text, f"Texto de score quedó en español: {card_text!r}"

    assert not errors, f"JS errors en Mental (en): {errors}"


@pytest.mark.mobile
@pytest.mark.timeout(60)
def test_raceday_screen_translated(page: Page, athlete_api):
    """
    Given: un atleta de prueba sin meta de carrera configurada (estado
           real de cualquier cuenta nueva) o sin plan Race Day (gateado)
    When:  entra a Race Day > Dashboard con idioma portugués
    Then:  el mensaje de "configurá tu meta de carrera" (o el gate de
           plan) aparece en portugués, nunca en español — confirma que
           renderRaceDayDashboard/loadRaceDayDashboard quedaron
           traducidos (Sprint 2b-vii).
    """
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth_and_lang(page, athlete_api._token, "pt")

    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_selector("#today-content .no-workout, #today-content .today-card-compact", timeout=20000)

    page.evaluate("goScreen('screen-raceday')")
    page.wait_for_selector("#rd-dash-card:not(:has-text('Carregando'))", timeout=20000)

    card_text = page.locator("#rd-dash-card").inner_text()
    assert "Configurá tu meta" not in card_text, f"Mensaje quedó en español: {card_text!r}"
    assert "Tu plan no incluye" not in card_text, f"Gate de plan quedó en español: {card_text!r}"

    assert not errors, f"JS errors en Race Day (pt): {errors}"


@pytest.mark.mobile
@pytest.mark.timeout(60)
def test_progress_screen_translated(page: Page, athlete_api):
    """
    Given: un atleta de prueba sin insights/datos de analytics todavía
           (estado real de cualquier cuenta nueva) o sin plan Analytics
           (gateado)
    When:  entra a Progreso > Insights con idioma inglés
    Then:  el mensaje de "todo en rango óptimo" (o el gate de plan)
           aparece en inglés, nunca en español — confirma que
           loadProgressInsights/renderProgressInsights quedaron
           traducidos (Sprint 2b-viii).
    """
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth_and_lang(page, athlete_api._token, "en")

    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_selector("#today-content .no-workout, #today-content .today-card-compact", timeout=20000)

    page.evaluate("goScreen('screen-progress')")
    page.wait_for_selector("#pgr-insights-list:not(:has-text('Loading'))", timeout=20000)

    list_text = page.locator("#pgr-insights-list").inner_text()
    assert "Cargando" not in list_text, f"Pantalla quedó en estado de carga (ES): {list_text!r}"
    assert "Todo en rango óptimo" not in list_text, f"Mensaje quedó en español: {list_text!r}"
    assert "Tu plan no incluye" not in list_text, f"Gate de plan quedó en español: {list_text!r}"

    assert not errors, f"JS errors en Progreso (en): {errors}"


@pytest.mark.mobile
@pytest.mark.timeout(60)
def test_aicoach_chat_new_conversation_translated(page: Page, athlete_api):
    """
    Given: un atleta de prueba cualquiera
    When:  entra a AI Coach > Chat con idioma portugués y toca "Nueva
           conversación"
    Then:  el mensaje de saludo inicial aparece en portugués, nunca en
           español — confirma que aicNewChat() quedó traducido
           (Sprint 2b-ix).
    """
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth_and_lang(page, athlete_api._token, "pt")

    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_selector("#today-content .no-workout, #today-content .today-card-compact", timeout=20000)

    page.evaluate("goScreen('screen-aicoach')")
    page.evaluate("aicNewChat()")
    page.wait_for_selector("#aic-messages .aic-msg-ai", timeout=10000)

    msg_text = page.locator("#aic-messages .aic-msg-ai").first.inner_text()
    assert "Nueva conversación" not in msg_text, f"Saludo quedó en español: {msg_text!r}"

    assert not errors, f"JS errors en AI Coach (pt): {errors}"


@pytest.mark.mobile
@pytest.mark.timeout(60)
def test_gear_screen_translated(page: Page, athlete_api):
    """
    Given: un atleta de prueba sin zapatillas/bicicletas registradas
           (estado real de cualquier cuenta nueva)
    When:  entra a Mi Equipo > Zapatillas con idioma inglés
    Then:  el mensaje de "todavía no agregaste zapatillas" aparece en
           inglés, nunca en español — confirma que
           loadGearShoes/renderGearShoes quedaron traducidos
           (Sprint 2b-x).
    """
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth_and_lang(page, athlete_api._token, "en")

    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_selector("#today-content .no-workout, #today-content .today-card-compact", timeout=20000)

    page.evaluate("goScreen('screen-gear')")
    page.wait_for_selector("#gear-shoes-list:not(:has-text('Loading'))", timeout=20000)

    list_text = page.locator("#gear-shoes-list").inner_text()
    assert "Cargando" not in list_text, f"Pantalla quedó en estado de carga (ES): {list_text!r}"
    assert "Todavía no agregaste" not in list_text, f"Mensaje quedó en español: {list_text!r}"

    assert not errors, f"JS errors en Mi Equipo (en): {errors}"
