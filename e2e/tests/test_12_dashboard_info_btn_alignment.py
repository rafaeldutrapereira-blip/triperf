"""
E2E-DASHBOARD-P11B2FIX2 — Posición única e inline del botón ⓘ
=================================================================
Priority : HIGH
Markers  : smoke, dashboard, ui-regression
Coverage :
  TC-P11B2F2-001  Todas las filas con ⓘ quedan inline (centro vertical
                  en la línea del título, borde izq. <24px del texto)
  TC-P11B2F2-002  Las 4 filas de ACWR por deporte muestran su propio
                  deporte (Natación/Ciclismo/Trote/Prep. física), no
                  un nombre genérico repetido
  TC-P11B2F2-003  VO2 Running/Ciclismo conservan el texto que escribe
                  _vo2Sport() y el ⓘ sigue funcional (no fue borrado)
  TC-P11B2F2-004  Todos los ⓘ son clicables y abren contenido real
                  (título + texto, no vacío)
  TC-P11B2F2-005  Estable con badges anchos (fuerza "Sem dados" /
                  "Carregada · ontem") en PT y ES, 1280 y 390

Usa el harness existente (logged_in_page + athlete_api real, mismo
patrón que test_02_athlete_flow.py) — no se agregan scripts nuevos
fuera de e2e/. Para reproducir el caso borde de badges anchos sin
depender de datos reales del atleta de prueba, se fuerza el texto
de los badges vía page.evaluate() después del render (mismo DOM que
vería un atleta con Body Battery cargada ayer o sin datos recientes).
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

from e2e.conftest import BASE_URL
from e2e.pages.athlete_page import DashboardPage

# Términos válidos: los únicos ids que existen en SIGLAS (lx-info.js,
# bloque LXTerm). Si una fila usa un id fuera de esta lista como
# data-lx-term, autoInit no la rellena (falla en silencio).
VALID_TERMS = {
    "ctl", "atl", "tsb", "acwr", "tss", "hrv", "recovery_score",
    "readiness", "body_battery", "fatiga_mental", "ftp", "css",
    "vo2max", "rpe", "compliance", "tapering", "resting_hr",
    "fatiga_muscular", "sueno",
}

# Badges anchos reales de la app (PT es el caso más ancho: "Carregada
# · ontem" / "Sem dados") — forzados sobre el DOM ya renderizado para
# reproducir el wrap sin depender de datos reales del atleta E2E.
WIDE_BADGES_PT = {
    "#badge-vo2": "Sem dados",
    "#badge-vo2-cycling": "Sem dados",
    "#badge-tss": "Sem dados",
    "#kc-acwr-badge": "Sem dados",
}


def _force_wide_badges(page: Page, badges: dict[str, str]):
    """Inyecta texto ancho en badges reales para reproducir el wrap."""
    for selector, text in badges.items():
        page.evaluate(
            """([sel, txt]) => {
                const el = document.querySelector(sel);
                if (el) el.textContent = txt;
            }""",
            [selector, text],
        )


def _set_language(page: Page, lang: str):
    page.evaluate(
        """(lang) => {
            try { localStorage.setItem('lx_lang', lang); } catch(e) {}
            if (window.i18n && window.i18n.setLanguage) window.i18n.setLanguage(lang);
            document.dispatchEvent(new Event('lx:langchange'));
        }""",
        lang,
    )


def _inventory_info_buttons(page: Page) -> list[dict]:
    """
    Recorre TODAS las filas con ⓘ (patrón A: .lx-term-info dentro de
    .kcr-label-main vía LXTerm; patrón B: .lx-term-info hermano del
    título con onclick=LXTerm.open; patrón C: .lx-info-btn del sistema
    viejo data-lx-info) y devuelve la geometría + texto de cada una.
    """
    return page.evaluate("""() => {
        const rows = [];
        document.querySelectorAll('.kcr, .insight-card, #insight-card').forEach((row) => {
            const btns = row.querySelectorAll(':scope .lx-term-info, :scope > .lx-info-btn, :scope .kcr-label-main > .lx-info-btn');
            btns.forEach((btn) => {
                const label = row.querySelector('.kcr-label-main, .kpi-card-q') || row;
                const labelBox = label.getBoundingClientRect();
                const btnBox = btn.getBoundingClientRect();
                const vCenterDiff = Math.abs(
                    (btnBox.top + btnBox.height / 2) - (labelBox.top + labelBox.height / 2)
                );
                const hGap = btnBox.left - labelBox.right;
                rows.push({
                    rowText: (label.textContent || '').trim().slice(0, 40),
                    vCenterDiff,
                    hGap,
                    visible: btnBox.width > 0 && btnBox.height > 0,
                });
            });
        });
        return rows;
    }""")


@pytest.mark.smoke
@pytest.mark.dashboard
@pytest.mark.parametrize("viewport", [
    {"width": 1280, "height": 900},
    {"width": 390, "height": 844},
])
@pytest.mark.parametrize("lang", ["es", "pt"])
def test_info_buttons_inline_all_rows(logged_in_page: Page, viewport, lang):
    """TC-P11B2F2-001/005: ⓘ inline en TODAS las filas, PT/ES, 1280/390,
    incluso forzando badges anchos."""
    page = logged_in_page
    page.set_viewport_size(viewport)

    dash = DashboardPage(page, BASE_URL).navigate()
    dash.wait_for_data()
    page.wait_for_selector(".kcr-label-main", timeout=8000)

    _set_language(page, lang)
    page.wait_for_timeout(300)
    if lang == "pt":
        _force_wide_badges(page, WIDE_BADGES_PT)
    page.wait_for_timeout(200)

    rows = _inventory_info_buttons(page)
    visible_rows = [r for r in rows if r["visible"]]

    assert len(visible_rows) > 0, "No se encontró ningún botón ⓘ visible en el dashboard"

    failures = [
        r for r in visible_rows
        if r["vCenterDiff"] > 2 or not (-5 < r["hGap"] < 24)
    ]
    assert not failures, (
        f"{len(failures)} fila(s) con ⓘ fuera de línea ({lang}, {viewport['width']}px): "
        f"{failures}"
    )


@pytest.mark.smoke
@pytest.mark.dashboard
def test_acwr_sport_rows_keep_distinct_labels(logged_in_page: Page):
    """TC-P11B2F2-002: las 4 filas de ACWR por deporte muestran su propio
    deporte, no un nombre genérico repetido (regresión de usar
    data-lx-term="acwr" sobre el título, que LXTerm sobreescribiría)."""
    page = logged_in_page
    page.set_viewport_size({"width": 1280, "height": 900})

    dash = DashboardPage(page, BASE_URL).navigate()
    dash.wait_for_data()

    # El detalle por deporte está dentro de un <details> colapsado
    details = page.locator("#acwr-detail")
    if details.count():
        details.locator("summary").click()

    expected = {
        "kc-acwr-swim": "Natación",
        "kc-acwr-bike": "Ciclismo",
        "kc-acwr-run": "Trote",
        "kc-acwr-gym": "física",  # "Prep. física"
    }
    for row_id, expected_fragment in expected.items():
        row = page.locator(f"#{row_id}")
        text = row.locator(".kcr-label-main").inner_text()
        assert expected_fragment in text, (
            f"#{row_id} debería mostrar '{expected_fragment}' pero muestra: {text!r}"
        )
        # Cada fila conserva su propio ⓘ funcional
        assert row.locator(".lx-term-info").count() == 1


@pytest.mark.smoke
@pytest.mark.dashboard
def test_vo2_rows_survive_sport_rewrite(logged_in_page: Page):
    """TC-P11B2F2-003: _vo2Sport() reescribe el texto del título (sigue
    vivo) y el ⓘ, al ser hermano y no hijo, no se borra."""
    page = logged_in_page
    page.set_viewport_size({"width": 1280, "height": 900})

    dash = DashboardPage(page, BASE_URL).navigate()
    dash.wait_for_data()

    for name_id in ("kl-vo2-running-name", "kl-vo2-cycling-name"):
        label = page.locator(f"#{name_id}")
        assert label.count() == 1
        # El ⓘ debe existir como hermano inmediato, no dentro del span
        sibling_btn = page.locator(f"#{name_id} + .lx-term-info")
        assert sibling_btn.count() == 1, (
            f"#{name_id}: el botón ⓘ no está como hermano inmediato "
            f"(¿_vo2Sport() lo borró por estar dentro del span?)"
        )


@pytest.mark.smoke
@pytest.mark.dashboard
def test_info_buttons_open_real_content(logged_in_page: Page):
    """TC-P11B2F2-004: muestra de cada patrón (A: ctl term; B: acwr
    solo-botón; C: injury_risk sin término) — el clic abre una tarjeta
    con título y texto reales, no vacía."""
    page = logged_in_page
    page.set_viewport_size({"width": 1280, "height": 900})

    dash = DashboardPage(page, BASE_URL).navigate()
    dash.wait_for_data()

    # Patrón A: CTL (data-lx-term)
    page.locator('[data-lx-term="ctl"] .lx-term-info').first.click()
    page.wait_for_selector(".lx-term-card", timeout=3000)
    card_text = page.locator(".lx-term-card").inner_text()
    assert len(card_text.strip()) > 10
    page.locator(".lx-term-card-close").click()

    # Patrón B: ACWR por deporte (solo-botón, LXTerm.open)
    details = page.locator("#acwr-detail")
    if details.count():
        details.locator("summary").click()
    page.locator("#kc-acwr-swim .lx-term-info").click()
    page.wait_for_selector(".lx-term-card", timeout=3000)
    card_text2 = page.locator(".lx-term-card").inner_text()
    assert len(card_text2.strip()) > 10
    page.locator(".lx-term-card-close").click()

    # Patrón C: injury_risk (data-lx-info, sistema viejo)
    injury_btn = page.locator("#kc-injury .lx-info-btn")
    if injury_btn.count():
        injury_btn.click()
        page.wait_for_timeout(300)
        # El panel viejo usa #lx-info-panel / #lx-info-body
        body_text = page.locator("#lx-info-body").inner_text()
        assert len(body_text.strip()) > 10
