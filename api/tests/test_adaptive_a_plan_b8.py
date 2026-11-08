"""
B8 â€” Adaptativo pasa al Plan (pestaÃ±a "Ajustes adaptativos", embebida).
Las vistas de coach de RecuperaciÃ³n y Adaptativo salen de sus pÃ¡ginas de atleta
y se embeben en el mÃ³dulo Coach.
"""
from pathlib import Path

from .text_match import squash

ROOT = Path(__file__).resolve().parents[2]
ADAPTIVE = (ROOT / "adaptive.html").read_text(encoding="utf-8")
RECOVERY = (ROOT / "recovery.html").read_text(encoding="utf-8")
PLAN = (ROOT / "training_plan.html").read_text(encoding="utf-8")
COACH = (ROOT / "coach.html").read_text(encoding="utf-8")


def test_adaptativo_sin_tab_coach_pero_con_vista_embebida():
    assert 'id="coach-tab-btn"' not in ADAPTIVE
    assert "switchTab('coach',this)" not in ADAPTIVE
    assert 'id="tab-coach"' in ADAPTIVE            # la vista sigue existiendo para Coach
    assert squash("get('view')==='coach'") in squash(ADAPTIVE)


def test_recuperacion_sin_tab_coach_pero_con_vista_embebida():
    assert 'id="tab-coach-btn"' not in RECOVERY
    assert "switchTab('coach',this)" not in RECOVERY
    assert 'id="tab-coach"' in RECOVERY
    assert squash("get('view')==='coach'") in squash(RECOVERY)


def test_modo_embed_en_ambas_paginas():
    for page in (ADAPTIVE, RECOVERY):
        assert ".lx-embed #sidebar" in page
        assert squash('get("embed")==="1"') in squash(page)


def test_plan_sin_seccion_adaptativa_incrustada():
    # S14 (2026-11-01): la sección incrustada que S10 (2026-11-01) dejó
    # dentro de "Ver más" (iframe perezoso a adaptive.html) sale de Mi
    # Plan. El motor (adaptive_routes.py) y adaptive.html no se tocan --
    # ya no hay iframe ni panel #s-adaptive en training_plan.html.
    assert 'id="s-adaptive"' not in PLAN
    assert 'id="tp-adaptive-frame"' not in PLAN
    assert 'data-src="adaptive.html?embed=1"' not in PLAN


def test_plan_tiene_enlace_a_ajustes_adaptativos():
    # S14: en su lugar queda un enlace simple a la
    # página completa (que sigue viva e intacta, ya no incrustada).
    assert 'id="tp-more"' not in PLAN  # MIPLAN-SIN-VERMAS: sin seccion plegada
    assert 'id="s-adaptive-link"' in PLAN
    assert 'href="adaptive.html"' in PLAN


def test_plan_tiene_aviso_adaptativo_ocasional():
    # S14: el valor de Ajustes Adaptativos llega como aviso descartable
    # SOLO cuando el motor propone un ajuste real para hoy (patrón
    # "Adaptations Pending" de TrainerRoad) -- consulta GET
    # /adaptive/signal/{hoy} (mismo endpoint real que ya usa
    # adaptive.html, sin inventar ninguno nuevo) y decide con los campos
    # que esa respuesta ya trae: signal.signal !== 'maintain' (el valor
    # neutro del propio motor) y signal.accepted !== true.
    assert 'id="adp-banner"' in PLAN
    assert "/adaptive/signal/" in PLAN
    assert "signal.signal === 'maintain'" in PLAN
    assert "signal.accepted === true" in PLAN
    # "Aplicar ajuste" hace el POST real sobre el motor (accept); "Ahora
    # no" es deliberadamente solo local, no reject -- no toca el backend.
    assert "/adaptive/accept/" in PLAN
    assert "/adaptive/reject/" not in PLAN
    assert "kl_adp_dismissed_date" in PLAN


def test_coach_embebe_las_dos_vistas():
    assert 'data-src="adaptive.html?view=coach&amp;embed=1"' in COACH
    assert 'data-src="recovery.html?view=coach&amp;embed=1"' in COACH
    assert "data-tab=\"adp-coach\"" in COACH
    assert "data-tab=\"rec-coach\"" in COACH
    assert "'adp-coach': 'coach-adp-frame'" in COACH
