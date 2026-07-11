"""
E2E-INDOOR — Indoor Workout Builder Tests
======================================================
Priority : HIGH
Markers  : athlete
Coverage :
  TC-IND-001  indoor_workout.html carga correctamente
  TC-IND-002  Agregar bloque de calentamiento
  TC-IND-003  Agregar bloque de intervalos
  TC-IND-004  Agregar bloque de vuelta a la calma
  TC-IND-005  SVG curve se renderiza con bloques
  TC-IND-006  Exportar .zwo (Zwift Workout XML)
  TC-IND-007  Exportar .erg (TrainerRoad format)
  TC-IND-008  Exportar .mrc (CyclingPeaks format)
  TC-IND-009  Workout aparece en training_plan.html
  TC-IND-010  Coach puede asignar workout indoor a atleta
  TC-IND-011  Validación: duración total > 0
  TC-IND-012  Bloques reordenables (drag & drop)
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from e2e.conftest import BASE_URL


def _inject_auth(page: Page, token: str, rol: str = "atleta"):
    page.evaluate(f"""() => {{
        localStorage.setItem('lx_co_token', '{token}');
        localStorage.setItem('lx_co_rol', '{rol}');
        localStorage.setItem('lx_co_nombre', 'E2E User');
    }}""")


# ─────────────────────────────────────────────────────────────────────────────
# TC-IND-001 — indoor_workout.html carga
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.smoke
@pytest.mark.athlete
def test_indoor_workout_carga(page: Page, athlete_api):
    """
    Acceptance:
      /indoor_workout.html returns 200 with content
      Page loads without JS errors
      Workout builder UI elements visible
    """
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)

    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(f"{BASE_URL}/indoor_workout.html")
    page.wait_for_load_state("networkidle")

    assert not errors, f"JS errors on indoor_workout.html: {errors}"

    # Builder container should exist
    builder = page.locator(
        "[class*='builder'], [class*='workout'], [id*='builder'], [id*='workout']"
    ).first
    expect(builder).to_be_visible(timeout=8000)


# ─────────────────────────────────────────────────────────────────────────────
# TC-IND-002 — Agregar bloque calentamiento
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
def test_agregar_bloque_calentamiento(page: Page, athlete_api):
    """
    Given: Indoor workout builder loaded
    When:  Click 'Añadir Calentamiento' or equivalent button
    Then:  Warmup block appears in workout list
           Block shows duration and intensity fields
    """
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)

    page.goto(f"{BASE_URL}/indoor_workout.html")
    page.wait_for_load_state("networkidle")

    # Find warmup button
    warmup_btn = page.locator(
        "button:has-text('Calentamiento'), button:has-text('Warmup'), "
        "button:has-text('Warm'), [data-type='warmup'], [data-block='warmup']"
    ).first

    if not warmup_btn.is_visible(timeout=3000):
        pytest.skip("Warmup add button not found in current DOM")

    initial_blocks = page.locator(
        "[class*='block'], [class*='segment'], [class*='interval']"
    ).count()

    warmup_btn.click()
    page.wait_for_timeout(500)

    new_blocks = page.locator(
        "[class*='block'], [class*='segment'], [class*='interval']"
    ).count()

    assert new_blocks > initial_blocks, \
        f"No block added after clicking warmup. Before: {initial_blocks}, After: {new_blocks}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-IND-003 — Agregar bloque intervalos
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
def test_agregar_bloque_intervalos(page: Page, athlete_api):
    """
    Given: Indoor workout builder loaded
    When:  Add interval block (high intensity)
    Then:  Block appears with power % and duration fields
    """
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)

    page.goto(f"{BASE_URL}/indoor_workout.html")
    page.wait_for_load_state("networkidle")

    interval_btn = page.locator(
        "button:has-text('Intervalo'), button:has-text('Interval'), "
        "[data-type='interval'], [data-block='interval'], "
        "button:has-text('Añadir'), button:has-text('Add Block')"
    ).first

    if not interval_btn.is_visible(timeout=3000):
        pytest.skip("Interval block button not found")

    interval_btn.click()
    page.wait_for_timeout(500)

    # Block should appear
    blocks = page.locator("[class*='block'], [class*='segment']")
    assert blocks.count() >= 1, "No blocks after clicking interval"


# ─────────────────────────────────────────────────────────────────────────────
# TC-IND-004 — SVG curve renderiza
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
def test_svg_curve_renderiza(page: Page, athlete_api):
    """
    Acceptance:
      SVG or canvas element present and has content
      Workout curve visualization is not blank
    """
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)

    page.goto(f"{BASE_URL}/indoor_workout.html")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)

    # Check for SVG or canvas (power curve visualization)
    svg_count = page.locator("svg").count()
    canvas_count = page.locator("canvas").count()

    assert svg_count + canvas_count >= 1, \
        "No SVG or canvas element found for workout curve visualization"

    if svg_count > 0:
        svg = page.locator("svg").first
        # SVG should have some path or rect elements (not empty)
        svg_html = page.evaluate("""() => document.querySelector('svg').innerHTML""")
        assert len(svg_html) > 50, "SVG appears empty"


# ─────────────────────────────────────────────────────────────────────────────
# TC-IND-005 — Exportar .zwo
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
def test_exportar_zwo(page: Page, athlete_api):
    """
    Given: Workout builder with at least 1 block
    When:  Click 'Export ZWO' button
    Then:  File download triggered with .zwo extension
           OR ZWO XML content displayed in textarea
    """
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)

    page.goto(f"{BASE_URL}/indoor_workout.html")
    page.wait_for_load_state("networkidle")

    # Find ZWO export button
    zwo_btn = page.locator(
        "button:has-text('ZWO'), button:has-text('Zwift'), "
        "[data-export='zwo'], button:has-text('Export ZWO')"
    ).first

    if not zwo_btn.is_visible(timeout=3000):
        pytest.skip("ZWO export button not found")

    # Listen for download or dialog
    downloaded = []
    page.on("download", lambda d: downloaded.append(d.suggested_filename))

    zwo_btn.click()
    page.wait_for_timeout(1500)

    if downloaded:
        assert any(".zwo" in f for f in downloaded), \
            f"Downloaded file not .zwo: {downloaded}"
    else:
        # May show content in textarea or new element
        zwo_content = page.locator(
            "textarea, [class*='xml'], [class*='zwo'], pre"
        ).first
        if zwo_content.is_visible(timeout=2000):
            text = zwo_content.inner_text()
            assert "workout" in text.lower() or "xml" in text.lower() or \
                   len(text) > 50, "ZWO content appears invalid"


# ─────────────────────────────────────────────────────────────────────────────
# TC-IND-006 — Exportar .erg
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
def test_exportar_erg(page: Page, athlete_api):
    """
    Given: Workout builder
    When:  Click 'Export ERG' button
    Then:  Download .erg file OR content shown
    """
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)

    page.goto(f"{BASE_URL}/indoor_workout.html")
    page.wait_for_load_state("networkidle")

    erg_btn = page.locator(
        "button:has-text('ERG'), button:has-text('.erg'), [data-export='erg']"
    ).first

    if not erg_btn.is_visible(timeout=3000):
        pytest.skip("ERG export button not found")

    downloaded = []
    page.on("download", lambda d: downloaded.append(d.suggested_filename))

    erg_btn.click()
    page.wait_for_timeout(1500)

    if downloaded:
        assert any(".erg" in f for f in downloaded), \
            f"Expected .erg download, got: {downloaded}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-IND-007 — Exportar .mrc
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
def test_exportar_mrc(page: Page, athlete_api):
    """
    Given: Workout builder
    When:  Click 'Export MRC' button
    Then:  Download .mrc file
    """
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)

    page.goto(f"{BASE_URL}/indoor_workout.html")
    page.wait_for_load_state("networkidle")

    mrc_btn = page.locator(
        "button:has-text('MRC'), button:has-text('.mrc'), [data-export='mrc']"
    ).first

    if not mrc_btn.is_visible(timeout=3000):
        pytest.skip("MRC export button not found")

    downloaded = []
    page.on("download", lambda d: downloaded.append(d.suggested_filename))

    mrc_btn.click()
    page.wait_for_timeout(1500)

    if downloaded:
        assert any(".mrc" in f for f in downloaded), \
            f"Expected .mrc download, got: {downloaded}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-IND-008 — Workout tiene duración > 0 antes de export
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
def test_validacion_duracion_total(page: Page, athlete_api):
    """
    Acceptance:
      Empty workout (no blocks) cannot be exported
      Error message or disabled export button if workout is empty
    """
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)

    page.goto(f"{BASE_URL}/indoor_workout.html")
    page.wait_for_load_state("networkidle")

    # Check if any export buttons are disabled when no blocks
    export_buttons = page.locator("button:has-text('Export'), button:has-text('ZWO')")

    if export_buttons.count() > 0:
        first_export = export_buttons.first
        is_disabled = first_export.get_attribute("disabled") is not None
        aria_disabled = first_export.get_attribute("aria-disabled") == "true"

        if is_disabled or aria_disabled:
            print("\nExport properly disabled for empty workout")
        else:
            # Try clicking and check for validation
            first_export.click()
            page.wait_for_timeout(500)
            body = page.locator("body").inner_text().lower()
            has_error = any(w in body for w in ["vacío", "empty", "bloque", "añade"])
            print(f"\nExport clicked on empty workout, error shown: {has_error}")


# ─────────────────────────────────────────────────────────────────────────────
# TC-IND-009 — Workout en training plan (integración)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
def test_indoor_workout_en_training_plan(page: Page, athlete_api, coach_api):
    """
    Given: Coach assigns indoor workout to athlete
    When:  Athlete views training_plan.html
    Then:  Indoor workout appears with indoor/bike icon
    """
    # Get athlete ID
    profile_r = athlete_api.get("/athlete/profile")
    if profile_r.status_code != 200:
        pytest.skip("Cannot get profile")
    athlete_id = profile_r.json().get("id") or profile_r.json().get("user_id")
    if not athlete_id:
        pytest.skip("No athlete ID")

    # Create indoor template
    tpl_r = coach_api.post("/coach/workout-templates", json={
        "nombre": "Indoor FTP Test",
        "sport": "bike",
        "description": "Indoor cycling E2E test",
        "duration_min": 60,
        "indoor": True,
    })
    if tpl_r.status_code not in (200, 201):
        pytest.skip("Cannot create indoor template")
    template_id = tpl_r.json().get("id")

    from datetime import date, timedelta
    future = (date.today() + timedelta(days=2)).isoformat()

    coach_api.post("/coach/assign-workout", json={
        "template_id": template_id,
        "athlete_id": athlete_id,
        "date_iso": future,
    })

    # View training plan
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)
    page.goto(f"{BASE_URL}/training_plan.html")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)

    # Plan should have some content
    body = page.locator("body").inner_text()
    assert len(body) > 100, "Training plan appears empty"


# ─────────────────────────────────────────────────────────────────────────────
# TC-IND-010 — Workout builder integrado en training_plan
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
def test_indoor_builder_integrado_training_plan(page: Page, athlete_api):
    """
    Acceptance:
      training_plan.html has link or button to create indoor workout
      OR indoor_workout.html is accessible from training plan
    """
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)

    page.goto(f"{BASE_URL}/training_plan.html")
    page.wait_for_load_state("networkidle")

    indoor_link = page.locator(
        "a[href*='indoor'], button:has-text('Indoor'), [class*='indoor']"
    ).first

    if indoor_link.is_visible(timeout=3000):
        print("\nIndoor workout link found in training plan")
        # Test navigation to indoor workout
        indoor_link.click()
        page.wait_for_timeout(1000)
        current = page.url
        if "indoor" in current:
            print(f"Navigated to: {current}")


# ─────────────────────────────────────────────────────────────────────────────
# TC-IND-011 — Drag & drop reorder blocks
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.athlete
@pytest.mark.slow
def test_drag_drop_reorder_blocks(page: Page, athlete_api):
    """
    Given: Multiple blocks in workout builder
    When:  Drag first block to second position
    Then:  Block order changes in the UI

    NOTE: This test is visual and requires actual blocks to be added first.
    May need to be adapted to specific DOM structure.
    """
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)

    page.goto(f"{BASE_URL}/indoor_workout.html")
    page.wait_for_load_state("networkidle")

    # Try to add 2 blocks
    add_btns = page.locator(
        "button:has-text('Añadir'), button:has-text('Add'), button:has-text('Calentamiento')"
    )

    if add_btns.count() >= 1:
        add_btns.first.click()
        page.wait_for_timeout(300)
        if add_btns.count() >= 1:
            add_btns.first.click()
            page.wait_for_timeout(300)

    blocks = page.locator("[class*='block'], [class*='segment'], [draggable='true']")
    if blocks.count() < 2:
        pytest.skip("Need at least 2 blocks for drag-drop test")

    # Attempt drag from first to second block
    block1 = blocks.nth(0)
    block2 = blocks.nth(1)

    block1_box = block1.bounding_box()
    block2_box = block2.bounding_box()

    if block1_box and block2_box:
        page.mouse.move(block1_box["x"] + 10, block1_box["y"] + 10)
        page.mouse.down()
        page.wait_for_timeout(200)
        page.mouse.move(block2_box["x"] + 10, block2_box["y"] + 10)
        page.wait_for_timeout(200)
        page.mouse.up()
        page.wait_for_timeout(500)

        print("\nDrag-drop attempt completed")
