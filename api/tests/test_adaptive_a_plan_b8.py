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


def test_plan_tiene_ajustes_adaptativos_perezosos():
    # S10 (2026-11-01): Ajustes Adaptativos deja de ser pestaña permanente
    # de Mi Plan -- vive dentro de "Ver más" (<details id="tp-more">,
    # cerrado por defecto) y el iframe sigue cargando recién al abrirse esa
    # zona, no de entrada con la página.
    assert 'id="tp-more"' in PLAN
    assert 'id="s-adaptive"' in PLAN
    assert 'id="tp-adaptive-frame"' in PLAN
    assert 'data-src="adaptive.html?embed=1"' in PLAN
    assert "tpMoreEl.addEventListener('toggle'" in PLAN


def test_coach_embebe_las_dos_vistas():
    assert 'data-src="adaptive.html?view=coach&amp;embed=1"' in COACH
    assert 'data-src="recovery.html?view=coach&amp;embed=1"' in COACH
    assert "data-tab=\"adp-coach\"" in COACH
    assert "data-tab=\"rec-coach\"" in COACH
    assert "'adp-coach': 'coach-adp-frame'" in COACH
