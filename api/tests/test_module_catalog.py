"""
B2 — El catálogo del servidor (api/module_catalog.py) y el de la web
(routes.config.js: tier, addonId, minPlan) deben coincidir.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from api.module_catalog import ADDONS, MODULES

ROOT = Path(__file__).resolve().parents[2]
PLAN_NAME = {"basico": "basic", "agegroup": "agegroup", "elite": "elite", None: None}

NODE = shutil.which("node")


def _routes_modules() -> dict:
    if not NODE:
        pytest.skip("node no disponible")
    script = (
        "const fs=require('fs');"
        "const src=fs.readFileSync(process.argv[1],'utf8');"
        "const w={};new Function('window',src)(w);"
        "console.log(JSON.stringify(w.LX_ROUTES.modules.filter(m=>m.tier)));"
    )
    out = subprocess.run(
        [NODE, "-e", script, str(ROOT / "routes.config.js")],
        capture_output=True, text=True, check=True,
    ).stdout
    return {m["id"]: m for m in json.loads(out)}


def test_cada_modulo_del_catalogo_existe_en_la_web():
    web = _routes_modules()
    assert set(MODULES) == set(web), (
        f"solo en servidor: {set(MODULES) - set(web)}; solo en web: {set(web) - set(MODULES)}"
    )


@pytest.mark.parametrize("module_id", sorted(MODULES))
def test_tier_y_addon_coinciden_con_la_web(module_id):
    spec = MODULES[module_id]
    web = _routes_modules()[module_id]
    assert web["tier"] == spec.tier
    assert web.get("addonId") == spec.addon_id


@pytest.mark.parametrize("module_id", sorted(MODULES))
def test_min_plan_coincide_con_la_web(module_id):
    spec = MODULES[module_id]
    web = _routes_modules()[module_id]
    assert web.get("minPlan") == PLAN_NAME[spec.min_plan]


def test_addons_referenciados_existen():
    for mid, spec in MODULES.items():
        if spec.addon_id is not None:
            assert spec.addon_id in ADDONS, f"{mid} apunta a addon desconocido {spec.addon_id}"


def test_addon_tiene_tier_addon_y_core_no_tiene_addon():
    for mid, spec in MODULES.items():
        if spec.tier == "addon":
            assert spec.addon_id is not None, mid
        if spec.tier == "core":
            assert spec.addon_id is None, mid
