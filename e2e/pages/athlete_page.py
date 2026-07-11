"""
Page Object Model — Athlete Pages (dashboard, training_plan, athlete-app)
"""
from __future__ import annotations
from playwright.sync_api import Page, expect


class DashboardPage:
    URL = "/dashboard.html"

    def __init__(self, page: Page, base_url: str = "http://localhost:8000"):
        self.page = page
        self.base_url = base_url

        # KPI cards
        self.ctl_card    = page.locator("[class*='ctl'], [id*='ctl']")
        self.atl_card    = page.locator("[class*='atl'], [id*='atl']")
        self.tsb_card    = page.locator("[class*='tsb'], [id*='tsb']")
        self.acwr_card   = page.locator("[class*='acwr'], [id*='acwr']")

        # Charts
        self.pmc_chart   = page.locator("canvas, [class*='chart'], [id*='pmc']")

        # Recent activities
        self.activities  = page.locator("[class*='activity-item'], [class*='recent-act']")

        # Nav sidebar
        self.nav_links   = page.locator("nav a, [class*='sidebar'] a")

        # User menu
        self.user_menu   = page.locator("[class*='user-menu'], [class*='avatar']")
        self.logout_btn  = page.locator("button:has-text('Salir'), a:has-text('Logout'), [onclick*='logout']")

    def navigate(self):
        self.page.goto(f"{self.base_url}{self.URL}")
        self.page.wait_for_load_state("networkidle")
        return self

    def wait_for_data(self, timeout: int = 8000):
        """Wait for dashboard to finish loading API data."""
        self.page.wait_for_load_state("networkidle", timeout=timeout)

    def logout(self):
        self.user_menu.click()
        self.page.wait_for_timeout(200)
        self.logout_btn.click()
        self.page.wait_for_url(lambda url: "login" in url, timeout=5000)


class TrainingPlanPage:
    URL = "/training_plan.html"

    def __init__(self, page: Page, base_url: str = "http://localhost:8000"):
        self.page = page
        self.base_url = base_url

        self.calendar        = page.locator("[class*='calendar'], [id*='calendar']")
        self.sessions        = page.locator("[class*='session-card'], [class*='plan-session']")
        self.week_nav_prev   = page.locator("[class*='prev'], button:has-text('‹'), button:has-text('<')")
        self.week_nav_next   = page.locator("[class*='next'], button:has-text('›'), button:has-text('>')")
        self.complete_btn    = page.locator("button:has-text('Completar'), button:has-text('Done')")

    def navigate(self):
        self.page.goto(f"{self.base_url}{self.URL}")
        self.page.wait_for_load_state("networkidle")
        return self


class AthleteAppPage:
    """PWA Mobile App (athlete-app.html)"""
    URL = "/athlete-app.html"

    def __init__(self, page: Page, base_url: str = "http://localhost:8000"):
        self.page = page
        self.base_url = base_url

        # Bottom nav
        self.nav_home        = page.locator("[data-screen='home'], [class*='nav-home']")
        self.nav_training    = page.locator("[data-screen='training'], [class*='nav-train']")
        self.nav_calendar    = page.locator("[data-screen='calendar'], [class*='nav-cal']")
        self.nav_profile     = page.locator("[data-screen='profile'], [class*='nav-profile']")

        # Readiness score
        self.readiness_score = page.locator("[class*='readiness'], [id*='readiness']")

        # Training today
        self.today_workout   = page.locator("[class*='today-workout'], [class*='workout-card']")

    def navigate(self):
        self.page.goto(f"{self.base_url}{self.URL}")
        self.page.wait_for_load_state("networkidle")
        return self

    def set_mobile_viewport(self):
        self.page.set_viewport_size({"width": 390, "height": 844})  # iPhone 14
