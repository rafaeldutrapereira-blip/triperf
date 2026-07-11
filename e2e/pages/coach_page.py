"""
Page Object Model — Coach Platform (coach.html)
"""
from __future__ import annotations
from playwright.sync_api import Page, expect


class CoachPage:
    URL = "/coach.html"

    def __init__(self, page: Page, base_url: str = "http://localhost:8000"):
        self.page = page
        self.base_url = base_url

        # Sidebar nav tabs
        self.tab_athletes    = page.locator("[data-tab='athletes'], [href*='athletes'], button:has-text('Atletas')")
        self.tab_workouts    = page.locator("[data-tab='workouts'], button:has-text('Workouts')")
        self.tab_groups      = page.locator("[data-tab='groups'], button:has-text('Grupos')")
        self.tab_messages    = page.locator("[data-tab='messages'], button:has-text('Mensajes')")
        self.tab_templates   = page.locator("[data-tab='templates'], button:has-text('Plantillas')")
        self.tab_compliance  = page.locator("[data-tab='compliance'], button:has-text('Compliance')")

        # Athlete list
        self.athlete_list    = page.locator("[class*='athlete-list'], [id*='athlete-list']")
        self.athlete_cards   = page.locator("[class*='athlete-card']")

        # Workout assignment
        self.assign_btn      = page.locator("button:has-text('Asignar'), [class*='assign']")

        # Notification bell
        self.notif_bell      = page.locator("[class*='notif-bell'], [class*='bell'], [id*='notif']")

    def navigate(self):
        self.page.goto(f"{self.base_url}{self.URL}")
        self.page.wait_for_load_state("networkidle")
        return self

    def go_to_tab(self, tab_name: str):
        tab = self.page.locator(f"button:has-text('{tab_name}'), [data-tab='{tab_name.lower()}']").first
        tab.click()
        self.page.wait_for_timeout(300)

    def wait_for_athletes_loaded(self):
        self.athlete_cards.first.wait_for(state="visible", timeout=8000)

    def assign_workout_to_athlete(self, athlete_name: str, workout_name: str, date: str):
        """Assign a workout template to a specific athlete."""
        # Find athlete card and click assign
        card = self.page.locator(f"[class*='athlete-card']:has-text('{athlete_name}')").first
        card.locator("button:has-text('Asignar'), [class*='assign']").click()
        # Fill assignment modal
        self.page.wait_for_selector("[class*='modal'], [role='dialog']", state="visible")
        self.page.locator("select[name*='template'], [id*='template-select']").select_option(label=workout_name)
        self.page.locator("input[type='date'], [id*='date']").fill(date)
        self.page.locator("button:has-text('Confirmar'), button:has-text('Asignar'), button[type='submit']").click()
