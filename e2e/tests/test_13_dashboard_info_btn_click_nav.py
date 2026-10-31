"""
E2E-DASHBOARD-P11B2FIX3 — Clic en el ⓘ no navega; VO2 e Insight en línea
===========================================================================
Priority : HIGH
Markers  : smoke, dashboard, ui-regression
Coverage :
  TC-P11B2F3-001  Clic en el ⓘ de filas que navegan (CTL, ACWR
                  principal, ACWR Natación, HRV, TSS semanal, VO2
                  Trote) abre la tarjeta/drawer y la URL sigue
                  siendo dashboard.html (antes: navegaba a
                  detalle.html?metric=ctl)
  TC-P11B2F3-002  Clic en el ⓘ de Insight abre el drawer y la URL
                  no cambia
  TC-P11B2F3-003  Clic en la fila de CTL FUERA del ⓘ sigue
                  navegando a detalle.html (no se rompió el golden
                  path)
  TC-P11B2F3-004  VO2 Running/Ciclismo: el ⓘ queda en la PRIMERA
                  línea del título (no se apila debajo)
  TC-P11B2F3-005  Insight: el ⓘ queda inline tras "Insight del día"
                  (no flotado en la esquina de la tarjeta)
  TC-P11B2F3-006  Clic en el ⓘ (patrón B, inline onclick=LXTerm.open)
                  no dispara un segundo open/close por el listener
                  delegado de document (bug latente: abría y se
                  cerraba en el mismo tick) — la tarjeta debe seguir
                  visible 300ms después del clic

Usa el harness existente (logged_in_page + DashboardPage), igual que
test_12_dashboard_info_btn_alignment.py (fix 2).
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

from e2e.conftest import BASE_URL
from e2e.pages.athlete_page import DashboardPage


def _open_url(page: Page) -> str:
    return page.evaluate("() => location.href")


@pytest.mark.smoke
@pytest.mark.dashboard
@pytest.mark.parametrize("row_id,btn_selector,card_selector", [
    ('[data-lx-term="ctl"]', '.lx-term-info', ".lx-term-card"),
    ("#kc-acwr", ".lx-term-info", ".lx-term-card"),
    ('[data-lx-term="hrv"]', ".lx-term-info", ".lx-term-card"),
])
def test_info_click_does_not_navigate_pattern_a(logged_in_page: Page, row_id, btn_selector, card_selector):
    """TC-P11B2F3-001: patrón A (CTL/ACWR-carga/HRV) — clic en ⓘ abre
    tarjeta, URL sigue en dashboard.html."""
    page = logged_in_page
    page.set_viewport_size({"width": 1280, "height": 900})

    dash = DashboardPage(page, BASE_URL).navigate()
    dash.wait_for_data()

    url_before = _open_url(page)
    assert "dashboard" in url_before

    page.locator(f"{row_id} {btn_selector}").first.click()
    page.wait_for_selector(card_selector, timeout=3000)

    assert "dashboard" in _open_url(page), (
        f"{row_id}: el clic en el ⓘ navegó fuera de dashboard.html "
        f"(URL: {_open_url(page)})"
    )
    card_text = page.locator(card_selector).first.inner_text()
    assert len(card_text.strip()) > 10


@pytest.mark.smoke
@pytest.mark.dashboard
def test_info_click_does_not_navigate_acwr_swim(logged_in_page: Page):
    """TC-P11B2F3-001: ACWR Natación (patrón B, solo-botón) — clic en ⓘ
    abre tarjeta, URL sigue en dashboard.html, y la tarjeta sigue
    visible 300ms después (no hay open-then-close del listener
    delegado de document)."""
    page = logged_in_page
    page.set_viewport_size({"width": 1280, "height": 900})

    dash = DashboardPage(page, BASE_URL).navigate()
    dash.wait_for_data()

    details = page.locator("#acwr-detail")
    if details.count():
        details.locator("summary").click()

    url_before = _open_url(page)
    page.locator("#kc-acwr-swim .lx-term-info").click()
    page.wait_for_selector(".lx-term-card", timeout=3000)
    assert "dashboard" in _open_url(page)

    # TC-P11B2F3-006: no debe cerrarse solo por el listener delegado
    page.wait_for_timeout(300)
    assert page.locator(".lx-term-card").count() == 1, (
        "La tarjeta de ACWR Natación se cerró sola — el listener "
        "delegado de document volvió a procesar el mismo clic "
        "(falta event.stopPropagation() en el botón)"
    )
    assert url_before == _open_url(page)


@pytest.mark.smoke
@pytest.mark.dashboard
def test_info_click_does_not_navigate_tss(logged_in_page: Page):
    """TC-P11B2F3-001/006: TSS semanal (patrón B) — mismo caso que ACWR
    Natación, verificado por separado porque usa id 'tss'."""
    page = logged_in_page
    page.set_viewport_size({"width": 1280, "height": 900})

    dash = DashboardPage(page, BASE_URL).navigate()
    dash.wait_for_data()

    url_before = _open_url(page)
    page.locator('.kcr[onclick*="goMetric(\'tss\')"] .lx-term-info').click()
    page.wait_for_selector(".lx-term-card", timeout=3000)
    assert "dashboard" in _open_url(page)
    page.wait_for_timeout(300)
    assert page.locator(".lx-term-card").count() == 1
    assert url_before == _open_url(page)


@pytest.mark.smoke
@pytest.mark.dashboard
def test_info_click_does_not_navigate_vo2_running(logged_in_page: Page):
    """TC-P11B2F3-001/004/006: VO2 Trote — clic en ⓘ no navega, no se
    autocierra, y geométricamente queda en la primera línea del
    título (no apilado bajo "VO2 Max Running")."""
    page = logged_in_page
    page.set_viewport_size({"width": 1280, "height": 900})

    dash = DashboardPage(page, BASE_URL).navigate()
    dash.wait_for_data()

    name_box = page.locator("#kl-vo2-running-name").bounding_box()
    btn = page.locator("#kl-vo2-running-name + .lx-term-info")
    btn_box = btn.bounding_box()
    assert name_box and btn_box
    v_center_diff = abs(
        (btn_box["y"] + btn_box["height"] / 2) - (name_box["y"] + name_box["height"] / 2)
    )
    assert v_center_diff <= 4, (
        f"VO2 Running: el ⓘ no está en la primera línea del título "
        f"(diff vertical {v_center_diff:.1f}px)"
    )

    url_before = _open_url(page)
    btn.click()
    page.wait_for_selector(".lx-term-card", timeout=3000)
    assert "dashboard" in _open_url(page)
    page.wait_for_timeout(300)
    assert page.locator(".lx-term-card").count() == 1
    assert url_before == _open_url(page)


@pytest.mark.smoke
@pytest.mark.dashboard
def test_insight_info_click_does_not_navigate_and_is_inline(logged_in_page: Page):
    """TC-P11B2F3-002/005: Insight — ⓘ inline tras el título (no
    flotado en la esquina), clic abre el drawer viejo (#lx-info-panel)
    y la URL no cambia."""
    page = logged_in_page
    page.set_viewport_size({"width": 1280, "height": 900})

    dash = DashboardPage(page, BASE_URL).navigate()
    dash.wait_for_data()

    title = page.locator("#insight-card .kpi-card-q")
    btn = page.locator("#insight-card .kpi-card-q .lx-info-btn")
    assert btn.count() == 1

    title_box = title.bounding_box()
    btn_box = btn.bounding_box()
    assert title_box and btn_box
    gap = btn_box["x"] - (title_box["x"] + title_box["width"])
    assert -5 < gap < 24, (
        f"Insight: el ⓘ no está inline tras el título (gap {gap:.1f}px "
        f"— si es muy grande, sigue flotado en la esquina de la tarjeta)"
    )
    v_center_diff = abs(
        (btn_box["y"] + btn_box["height"] / 2) - (title_box["y"] + title_box["height"] / 2)
    )
    assert v_center_diff <= 4

    url_before = _open_url(page)
    btn.click()
    page.wait_for_timeout(300)
    assert "dashboard" in _open_url(page)
    assert url_before == _open_url(page)
    body_text = page.locator("#lx-info-body").inner_text()
    assert len(body_text.strip()) > 10


@pytest.mark.smoke
@pytest.mark.dashboard
def test_ctl_row_click_outside_info_still_navigates(logged_in_page: Page):
    """TC-P11B2F3-003: golden path intacto — clic en la fila de CTL
    FUERA del ⓘ sigue navegando a detalle.html."""
    page = logged_in_page
    page.set_viewport_size({"width": 1280, "height": 900})

    dash = DashboardPage(page, BASE_URL).navigate()
    dash.wait_for_data()

    # Click en el valor numérico (lado derecho de la fila), no en el ⓘ
    page.locator('[data-lx-term="ctl"]').locator("xpath=ancestor::div[contains(@class,'kcr')]") \
        .locator(".kcr-right").click()
    page.wait_for_url(lambda url: "detalle.html" in url and "metric=ctl" in url, timeout=5000)
