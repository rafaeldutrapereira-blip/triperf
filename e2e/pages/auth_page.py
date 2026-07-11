"""
Page Object Model — Auth Pages (login, registro, reset-password)
"""
from __future__ import annotations
from playwright.sync_api import Page, expect


class LoginPage:
    URL = "/login.html"

    def __init__(self, page: Page, base_url: str = "http://localhost:8000"):
        self.page = page
        self.base_url = base_url

        # Locators
        self.username_input  = page.locator("#username")
        self.password_input  = page.locator("#password")
        self.remember_check  = page.locator("#remember")
        self.submit_btn      = page.locator("#btn-login, button[type='submit']").first
        self.error_msg       = page.locator("[class*='error'], [class*='alert-danger'], #login-error")
        self.pw_toggle       = page.locator("#pw-toggle")
        self.forgot_link     = page.locator("a[href*='reset']")

    def navigate(self):
        self.page.goto(f"{self.base_url}{self.URL}")
        self.page.wait_for_load_state("domcontentloaded")
        return self

    def login(self, email: str, password: str, remember: bool = False):
        self.username_input.fill(email)
        self.password_input.fill(password)
        if remember:
            self.remember_check.check()
        self.submit_btn.click()
        return self

    def wait_for_redirect(self, timeout: int = 5000):
        self.page.wait_for_url(lambda url: "login.html" not in url, timeout=timeout)
        return self

    def expect_error(self, text: str = None):
        self.error_msg.wait_for(state="visible", timeout=4000)
        if text:
            expect(self.error_msg).to_contain_text(text, ignore_case=True)


class RegistroPage:
    URL = "/registro.html"

    def __init__(self, page: Page, base_url: str = "http://localhost:8000"):
        self.page = page
        self.base_url = base_url

        self.nombre_input   = page.locator("#nombre")
        self.email_input    = page.locator("#email")
        self.password_input = page.locator("#password")
        self.password2_input = page.locator("#password2")
        self.submit_btn     = page.locator("#btn-reg, button[type='submit']").first
        self.strength_bar   = page.locator("[class*='strength'], [class*='pw-strength']")
        self.error_msg      = page.locator("[class*='error'], [id*='error']")

    def navigate(self):
        self.page.goto(f"{self.base_url}{self.URL}")
        self.page.wait_for_load_state("domcontentloaded")
        return self

    def register(self, nombre: str, email: str, password: str, confirm: str = None):
        self.nombre_input.fill(nombre)
        self.email_input.fill(email)
        self.password_input.fill(password)
        self.password2_input.fill(confirm or password)
        self.submit_btn.click()
        return self


class ResetPasswordPage:
    URL = "/reset-password.html"

    def __init__(self, page: Page, base_url: str = "http://localhost:8000"):
        self.page = page
        self.base_url = base_url
        self.email_input = page.locator("input[type='email'], #email")
        self.submit_btn  = page.locator("button[type='submit']").first

    def navigate(self):
        self.page.goto(f"{self.base_url}{self.URL}")
        self.page.wait_for_load_state("domcontentloaded")
        return self

    def request_reset(self, email: str):
        self.email_input.fill(email)
        self.submit_btn.click()
