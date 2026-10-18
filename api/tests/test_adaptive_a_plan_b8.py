"""
B8 — Adaptativo pasa al Plan (pestaña "Ajustes adaptativos", embebida).
Las vistas de coach de Recuperación y Adaptativo salen de sus páginas de atleta
y se embeben en el módulo Coach.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADAPTIVE = (ROOT / "adaptive.html").read_text(encoding="utf-8")
RECOVERY = (ROOT / "recovery.html").read_text(encoding="utf-8")
PLAN = (ROOT / "training_plan.html").read_text(encoding="utf-8")
COACH = (ROOT / "coach.html").read_text(encoding="utf-8")


def test_adaptativo_sin_tab_coach_pero_con_vista_embebida():
    assert 'id="coach-tab-btn"' not in ADAPTIVE
    assert "switchTab('coach',this)" not in ADAPTIVE
    assert 'id="tab-coach"' in ADAPTIVE            # la vista sigue existiendo para Coach
    assert "get('view')==='coach'" in ADAPTIVE


def test_recuperacion_sin_tab_coach_pero_con_vista_embebida():
    assert 'id="tab-coach-btn"' not in RECOVERY
    assert "switchTab('coach',this)" not in RECOVERY
    assert 'id="tab-coach"' in RECOVERY
    assert "get('view')==='coach'" in RECOVERY


def test_modo_embed_en_ambas_paginas():
    for page in (ADAPTIVE, RECOVERY):
        assert ".lx-embed #sidebar" in page
        assert 'get("embed")==="1"' in page


def test_plan_tiene_pestana_ajustes_adaptativos_perezosa():
    assert 'data-tab="adaptive"' in PLAN
    assert 'id="tp-adaptive-frame"' in PLAN
    assert 'data-src="adaptive.html?embed=1"' in PLAN


def test_coach_embebe_las_dos_vistas():
    assert 'data-src="adaptive.html?view=coach&amp;embed=1"' in COACH
    assert 'data-src="recovery.html?view=coach&amp;embed=1"' in COACH
    assert "data-tab=\"adp-coach\"" in COACH
    assert "data-tab=\"rec-coach\"" in COACH
    assert "'adp-coach': 'coach-adp-frame'" in COACH
