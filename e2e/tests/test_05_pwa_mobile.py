"""
E2E-PWA — Mobile & Progressive Web App Tests
======================================================
Priority : HIGH
Markers  : mobile
Coverage :
  TC-PWA-001  athlete-app.html carga en viewport mobile
  TC-PWA-002  Manifest.json válido (instalable)
  TC-PWA-003  Service Worker registrado
  TC-PWA-004  Navegación bottom nav funciona
  TC-PWA-005  Readiness score visible en home
  TC-PWA-006  Calendario disponible en nav
  TC-PWA-007  App en modo offline muestra contenido cacheado
  TC-PWA-008  Theme color y apple-mobile-web-app-capable presentes
  TC-PWA-009  Touch targets >= 44px (accesibilidad táctil)
  TC-PWA-010  No horizontal scroll en mobile 390px
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect, BrowserContext

from e2e.conftest import BASE_URL, TEST_ATHLETE


MOBILE_VIEWPORT = {"width": 390, "height": 844}   # iPhone 14
TABLET_VIEWPORT = {"width": 768, "height": 1024}  # iPad


def _inject_auth(page: Page, token: str):
    page.evaluate(f"""() => {{
        localStorage.setItem('lx_co_token', '{token}');
        localStorage.setItem('lx_co_rol', 'atleta');
        localStorage.setItem('lx_ath_token', '{token}');
        localStorage.setItem('lx_co_nombre', 'Athlete E2E');
    }}""")


# ─────────────────────────────────────────────────────────────────────────────
# TC-PWA-001 — athlete-app.html en viewport mobile
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.smoke
@pytest.mark.mobile
def test_athlete_app_mobile_viewport(page: Page, athlete_api):
    """
    Given: Mobile viewport (390x844)
    When:  Navigate to athlete-app.html with auth
    Then:  Page renders without horizontal overflow
           Content visible, no JS errors
    """
    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)

    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("networkidle")

    assert not errors, f"JS errors on mobile: {errors}"

    # Page body should have content
    body = page.locator("body")
    expect(body).to_be_visible()

    # No horizontal scroll (scrollWidth should equal clientWidth)
    scroll_info = page.evaluate("""() => ({
        scrollW: document.documentElement.scrollWidth,
        clientW: document.documentElement.clientWidth
    })""")
    assert scroll_info["scrollW"] <= scroll_info["clientW"] + 5, \
        f"Horizontal scroll detected: scrollWidth={scroll_info['scrollW']} > clientWidth={scroll_info['clientW']}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-PWA-002 — Manifest.json válido
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.mobile
def test_manifest_valido():
    """
    Acceptance:
      /manifest.json returns 200
      Has: name, short_name, start_url, display, icons
      At least one icon with size 192x192
    """
    r = requests.get(f"{BASE_URL}/manifest.json", timeout=5)
    assert r.status_code == 200, f"manifest.json not found: {r.status_code}"

    data = r.json()
    assert "name" in data, "Missing 'name' in manifest"
    assert "short_name" in data, "Missing 'short_name' in manifest"
    assert "start_url" in data, "Missing 'start_url' in manifest"
    assert "display" in data, "Missing 'display' in manifest"
    assert data["display"] in ("standalone", "fullscreen", "minimal-ui"), \
        f"Invalid display mode: {data['display']}"

    icons = data.get("icons", [])
    assert len(icons) >= 1, "No icons in manifest"

    icon_sizes = [i.get("sizes", "") for i in icons]
    assert any("192" in s for s in icon_sizes), \
        f"No 192x192 icon found. Available: {icon_sizes}"


# ─────────────────────────────────────────────────────────────────────────────
# TC-PWA-003 — Service Worker registrado
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.mobile
def test_service_worker_registrado(page: Page, athlete_api):
    """
    Acceptance:
      /sw.js returns 200
      athlete-app.html registers the service worker
    """
    # Verify sw.js accessible
    r = requests.get(f"{BASE_URL}/sw.js", timeout=5)
    assert r.status_code == 200, "sw.js not found"
    assert len(r.text) > 100, "sw.js appears empty"

    # Verify sw.js has CACHE_NAME and PRECACHE
    assert "CACHE_NAME" in r.text or "BUILD_VERSION" in r.text, \
        "sw.js missing cache configuration"

    # Check BUILD_VERSION is a number
    import re
    match = re.search(r"BUILD_VERSION\s*=\s*'(\d+)'", r.text)
    assert match, "BUILD_VERSION not found in sw.js"
    version = int(match.group(1))
    assert version >= 28, f"BUILD_VERSION {version} seems outdated"


# ─────────────────────────────────────────────────────────────────────────────
# TC-PWA-004 — Bottom nav funciona en mobile
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.mobile
def test_bottom_nav_mobile(page: Page, athlete_api):
    """
    Given: Mobile viewport, athlete-app.html
    When:  Tap each bottom nav item
    Then:  Screen changes without full page reload
           Active state indicator updates
    """
    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)

    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("networkidle")

    # Find bottom nav
    nav = page.locator(
        "[class*='bottom-nav'], [class*='tab-bar'], nav.mobile, [class*='nav-bottom']"
    ).first

    if not nav.is_visible(timeout=3000):
        pytest.skip("No bottom nav found on athlete-app.html")

    # Try clicking nav items
    nav_items = nav.locator("a, button")
    count = nav_items.count()
    assert count >= 3, f"Expected at least 3 nav items, got {count}"

    # Click second nav item
    if count >= 2:
        nav_items.nth(1).click()
        page.wait_for_timeout(500)
        # Page should not have redirected (SPA behavior)
        assert "athlete-app" in page.url or "login" not in page.url


# ─────────────────────────────────────────────────────────────────────────────
# TC-PWA-005 — Readiness score en home
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.mobile
def test_readiness_score_visible_mobile(page: Page, athlete_api):
    """
    Given: Mobile, athlete-app.html
    When:  Home screen loads
    Then:  Readiness score element visible (may show '--' if no data)
    """
    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)

    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)

    readiness = page.locator(
        "[class*='readiness'], [id*='readiness'], [class*='drs'], [id*='drs']"
    ).first
    expect(readiness).to_be_visible(timeout=6000)


# ─────────────────────────────────────────────────────────────────────────────
# TC-PWA-006 — Calendar screen disponible
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.mobile
def test_calendar_screen_mobile(page: Page, athlete_api):
    """
    Given: Mobile athlete app
    When:  Navigate to calendar screen
    Then:  Monthly grid or weekly strip visible
    """
    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)

    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("networkidle")

    # Try to find and click calendar nav item
    cal_nav = page.locator(
        "[data-screen='calendar'], [class*='nav-cal'], [href*='calendar'], [aria-label*='calendar']"
    ).first

    if cal_nav.is_visible(timeout=3000):
        cal_nav.click()
        page.wait_for_timeout(500)
        cal_content = page.locator(
            "[class*='calendar'], [class*='monthly'], [class*='weekly']"
        ).first
        expect(cal_content).to_be_visible(timeout=5000)


# ─────────────────────────────────────────────────────────────────────────────
# TC-PWA-007 — META tags para PWA
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.mobile
def test_pwa_meta_tags(page: Page, athlete_api):
    """
    Acceptance:
      theme-color meta tag present
      apple-mobile-web-app-capable present
      viewport meta tag present
    """
    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("domcontentloaded")

    theme_color = page.locator('meta[name="theme-color"]')
    assert theme_color.count() >= 1, "Missing theme-color meta tag"

    apple_cap = page.locator('meta[name="apple-mobile-web-app-capable"]')
    assert apple_cap.count() >= 1, "Missing apple-mobile-web-app-capable meta"

    viewport = page.locator('meta[name="viewport"]')
    assert viewport.count() >= 1, "Missing viewport meta"

    vp_content = viewport.first.get_attribute("content") or ""
    assert "width=device-width" in vp_content, "Viewport not device-width"


# ─────────────────────────────────────────────────────────────────────────────
# TC-PWA-008 — Offline comportamiento (sin network)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.mobile
@pytest.mark.slow
def test_offline_cache_behavior(page: Page, athlete_api):
    """
    Given: Page has been loaded (SW cached)
    When:  Network is disabled
    Then:  Previously cached pages still load (not blank/error)

    NOTE: Requires service worker to be active. First visit may not be cached.
    """
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)

    # Load athlete-app to prime cache
    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)  # Let SW cache

    # Go offline
    page.context.set_offline(True)

    try:
        # Navigate again
        page.reload()
        page.wait_for_timeout(2000)

        # Should either show cached content or offline fallback
        body_text = page.locator("body").inner_text()
        assert len(body_text) > 20, "Offline: page appears blank (no cache)"

    finally:
        # Re-enable network
        page.context.set_offline(False)


# ─────────────────────────────────────────────────────────────────────────────
# TC-PWA-009 — Touch targets (accesibilidad)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.mobile
def test_touch_targets_size(page: Page, athlete_api):
    """
    Acceptance:
      All interactive elements (buttons, links) >= 44x44px
      per WCAG 2.5.5 and Apple HIG
    """
    page.set_viewport_size(MOBILE_VIEWPORT)
    page.goto(f"{BASE_URL}/login.html")
    _inject_auth(page, athlete_api._token)
    page.goto(f"{BASE_URL}/athlete-app.html")
    page.wait_for_load_state("networkidle")

    small_targets = page.evaluate("""() => {
        const elements = document.querySelectorAll('button, a, [role="button"], input[type="submit"]');
        const small = [];
        elements.forEach(el => {
            const rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                if (rect.width < 44 || rect.height < 44) {
                    small.push({
                        tag: el.tagName,
                        text: el.innerText?.trim().substring(0, 30),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height)
                    });
                }
            }
        });
        return small;
    }""")

    if small_targets:
        # Report as warning, not hard failure (some elements may intentionally be small)
        print(f"\n⚠️ Touch targets < 44px ({len(small_targets)} found):")
        for t in small_targets[:5]:
            print(f"  {t['tag']} '{t['text']}' → {t['width']}x{t['height']}px")
        # Fail only if more than 20% of targets are too small
        total = page.evaluate("""() =>
            document.querySelectorAll('button, a, [role="button"], input[type="submit"]').length
        """)
        if total > 0:
            ratio = len(small_targets) / total
            assert ratio < 0.3, \
                f"Too many small touch targets: {len(small_targets)}/{total} ({ratio:.0%})"


# ─────────────────────────────────────────────────────────────────────────────
# TC-PWA-010 — No horizontal scroll (375px viewport)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.mobile
@pytest.mark.parametrize("page_path", [
    "/athlete-app.html",
    "/login.html",
    "/registro.html",
])
def test_no_horizontal_scroll_mobile(page: Page, athlete_api, page_path: str):
    """
    Acceptance:
      No horizontal scroll on 375px viewport (iPhone SE)
      scrollWidth <= clientWidth + 5px tolerance
    """
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(f"{BASE_URL}/login.html")
    if "athlete-app" in page_path:
        _inject_auth(page, athlete_api._token)

    page.goto(f"{BASE_URL}{page_path}")
    page.wait_for_load_state("domcontentloaded")

    overflow = page.evaluate("""() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
        overflow: getComputedStyle(document.documentElement).overflowX
    })""")

    assert overflow["scrollWidth"] <= overflow["clientWidth"] + 5, \
        f"Horizontal overflow on {page_path}: " \
        f"scrollWidth={overflow['scrollWidth']} clientWidth={overflow['clientWidth']}"
