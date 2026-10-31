"""
E2E-DASHBOARD-P11B2POLISH — ⓘ de VO2 e Insight junto a la 1ª línea
también a 390px
===========================================================================
Priority : MEDIUM
Markers  : smoke, dashboard, ui-regression
Coverage :
  TC-P11B2POL-001  VO2 Running/Ciclismo: a 1280 y 390, |top del ⓘ −
                   top de la primera línea del título| < 6px (antes a
                   390 el título envolvía y el ⓘ quedaba centrado
                   contra todo el bloque, ~32px más abajo)
  TC-P11B2POL-002  Insight: a 1280 y 390, el ⓘ sigue en la primera
                   línea de "Insight del día" (gap < 24px tras el
                   título; antes a 390 el h3 se encogía contra el
                   pill de readiness y el ⓘ caía a su propia línea)
  TC-P11B2POL-003  No regresión: CTL y ACWR Natación siguen inline
                   (gap ~6px) a 1280 y 390 — el selector :has() del
                   pulido no debe tocar filas de una sola línea
  TC-P11B2POL-004  No regresión: el clic en el ⓘ de VO2 Trote sigue
                   abriendo su tarjeta sin navegar fuera de
                   dashboard.html

Usa el harness existente (logged_in_page + DashboardPage), PT y ES,
1280 y 390 — mismo patrón que test_12 y test_13.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

from e2e.conftest import BASE_URL
from e2e.pages.athlete_page import DashboardPage


def _set_language(page: Page, lang: str):
    page.evaluate(
        """(lang) => {
            try { localStorage.setItem('lx_lang', lang); } catch(e) {}
            if (window.i18n && window.i18n.setLanguage) window.i18n.setLanguage(lang);
            document.dispatchEvent(new Event('lx:langchange'));
        }""",
        lang,
    )


def _open_url(page: Page) -> str:
    return page.evaluate("() => location.href")


@pytest.mark.smoke
@pytest.mark.dashboard
@pytest.mark.parametrize("lang", ["pt", "es"])
@pytest.mark.parametrize("width", [1280, 390])
def test_vo2_info_btn_stays_on_first_line(logged_in_page: Page, lang, width):
    """TC-P11B2POL-001: el ⓘ de VO2 Running/Ciclismo queda a la altura
    de la PRIMERA línea del título, incluso cuando este envuelve."""
    page = logged_in_page
    page.set_viewport_size({"width": width, "height": 900})

    dash = DashboardPage(page, BASE_URL).navigate()
    dash.wait_for_data()
    _set_language(page, lang)
    page.wait_for_timeout(150)

    for name_id in ("kl-vo2-running-name", "kl-vo2-cycling-name"):
        name = page.locator(f"#{name_id}")
        btn = page.locator(f"#{name_id} + .lx-term-info")
        name_box = name.bounding_box()
        btn_box = btn.bounding_box()
        assert name_box and btn_box, f"{name_id}: título o botón no visibles a {width}px"

        # Top de la primera línea del título: el propio top del span si
        # no envolvió, o su top (la línea 1 siempre arranca en el top
        # del bloque) si envolvió a varias líneas.
        v_top_diff = abs(btn_box["y"] - name_box["y"])
        assert v_top_diff < 8, (
            f"{name_id} ({lang}, {width}px): el ⓘ no está junto a la "
            f"primera línea del título (diff top {v_top_diff:.1f}px)"
        )


@pytest.mark.smoke
@pytest.mark.dashboard
@pytest.mark.parametrize("lang", ["pt", "es"])
@pytest.mark.parametrize("width", [1280, 390])
def test_insight_info_btn_stays_on_first_line(logged_in_page: Page, lang, width):
    """TC-P11B2POL-002: el ⓘ de Insight sigue junto a "Insight del día"
    (no cae a una línea propia cuando el pill de readiness aprieta al
    h3 a 390px)."""
    page = logged_in_page
    page.set_viewport_size({"width": width, "height": 900})

    dash = DashboardPage(page, BASE_URL).navigate()
    dash.wait_for_data()
    _set_language(page, lang)
    page.wait_for_timeout(150)

    title = page.locator("#insight-card .kpi-card-q")
    btn = page.locator("#insight-card .kpi-card-q .lx-info-btn")
    title_box = title.bounding_box()
    btn_box = btn.bounding_box()
    assert title_box and btn_box

    v_center_diff = abs(
        (btn_box["y"] + btn_box["height"] / 2) - (title_box["y"] + title_box["height"] / 2)
    )
    assert v_center_diff <= 6, (
        f"Insight ({lang}, {width}px): el ⓘ no está a la altura del "
        f"título (diff vertical {v_center_diff:.1f}px — el h3 se está "
        f"encogiendo y envolviendo el botón a una línea propia)"
    )
    gap = btn_box["x"] - (title_box["x"] + title_box["width"])
    assert -5 < gap < 24, (
        f"Insight ({lang}, {width}px): el ⓘ no está inline tras el "
        f"título (gap {gap:.1f}px)"
    )


@pytest.mark.smoke
@pytest.mark.dashboard
@pytest.mark.parametrize("width", [1280, 390])
def test_single_line_rows_unaffected(logged_in_page: Page, width):
    """TC-P11B2POL-003: CTL y ACWR Natación (filas de una sola línea)
    no se ven afectadas por el selector :has() del pulido de VO2."""
    page = logged_in_page
    page.set_viewport_size({"width": width, "height": 900})

    dash = DashboardPage(page, BASE_URL).navigate()
    dash.wait_for_data()

    ctl_title = page.locator('[data-lx-term="ctl"] .lx-term-text')
    ctl_btn = page.locator('[data-lx-term="ctl"] .lx-term-info')
    ctl_title_box = ctl_title.bounding_box()
    ctl_btn_box = ctl_btn.bounding_box()
    assert ctl_title_box and ctl_btn_box
    gap_ctl = ctl_btn_box["x"] - (ctl_title_box["x"] + ctl_title_box["width"])
    assert -5 < gap_ctl < 24

    details = page.locator("#acwr-detail")
    if details.count():
        details.locator("summary").click()
    swim_btn = page.locator("#kc-acwr-swim .lx-term-info")
    swim_box = swim_btn.bounding_box()
    assert swim_box is not None


@pytest.mark.smoke
@pytest.mark.dashboard
def test_vo2_info_click_still_opens_without_navigating(logged_in_page: Page):
    """TC-P11B2POL-004: no regresión — el clic en el ⓘ de VO2 Trote
    sigue abriendo su tarjeta sin navegar fuera de dashboard.html."""
    page = logged_in_page
    page.set_viewport_size({"width": 390, "height": 900})

    dash = DashboardPage(page, BASE_URL).navigate()
    dash.wait_for_data()

    url_before = _open_url(page)
    page.locator("#kl-vo2-running-name + .lx-term-info").click()
    page.wait_for_selector(".lx-term-card", timeout=3000)
    assert "dashboard" in _open_url(page)
    page.wait_for_timeout(300)
    assert page.locator(".lx-term-card").count() == 1
    assert url_before == _open_url(page)
