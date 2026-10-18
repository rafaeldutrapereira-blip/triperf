"""
LabX — Catálogo de módulos: qué es core, qué es addon, y qué plan mínimo exige.

Fuente de verdad del lado del servidor para el modelo marketplace (B2).
Debe coincidir con los campos `tier` / `addonId` de routes.config.js; lo
verifica api/tests/test_module_catalog.py.

tier:
  core   incluido en el plan indicado por min_plan.
  addon  se compra por separado (addon_id) sobre cualquier plan que no lo
         incluya. Elite incluye algunos addons (included_in_elite).
  role   solo para un rol (coach/admin); no es un módulo de atleta.
  util   página utilitaria sin entrada propia de plan.

min_plan: plan mínimo que el sidebar y el servidor exigen HOY (lo que se aplica).
          Destino de la matriz, que se activa en B11/B12: addon comprable por
          Agegroup/Básico; Elite lo incluye (included_in_elite). Ver
          labx_audit/plan_reorganizacion.md, sección 1.1.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleSpec:
    tier: str
    min_plan: str | None
    addon_id: str | None = None
    included_in_elite: bool = False


# Addons vendibles (B12). Labs e Indoor tienen reglas de gracia (ver docs).
ADDONS: dict[str, str] = {
    "asistente_ia":          "Asistente IA",
    "labs":                  "Labs",
    "estrategia_carrera":    "Estrategia de carrera",
    "protocolos_mentales":   "Protocolos mentales avanzados",
    "indoor":                "Indoor",
    "ajustes_adaptativos":   "Ajustes adaptativos",
    "rendimiento_avanzado":  "Potencia y records avanzados",
    "retrospectiva":         "Retrospectiva anual",
}

MODULES: dict[str, ModuleSpec] = {
    # ── Core ─────────────────────────────────────────────────────────
    "dashboard":        ModuleSpec("core", "basico"),
    "athlete_profile":  ModuleSpec("core", "basico"),
    "athlete_app":      ModuleSpec("core", "basico"),
    "training_plan":    ModuleSpec("core", "agegroup"),   # B11: Free con plan de 1 semana
    "performance":      ModuleSpec("core", "basico"),     # Carga (PMC/ACWR); B7 lo fusiona en Rendimiento
    "recovery":         ModuleSpec("core", "agegroup"),   # Free NO accede (decisión)
    "mental":           ModuleSpec("core", "agegroup"),
    "nutrition":        ModuleSpec("core", "agegroup"),
    "race_day":         ModuleSpec("core", "agegroup"),   # pronóstico; estrategia = addon
    "community":        ModuleSpec("core", "agegroup"),   # pendiente: "Comunidad básica" en Free
    "gear":             ModuleSpec("core", "agegroup"),   # pendiente: "Equipo básico" en Free
    "analytics":        ModuleSpec("core", "agegroup"),
    "training_detail":  ModuleSpec("core", "elite"),      # Sesión: drill-down
    # ── Addons ───────────────────────────────────────────────────────
    "ai_coach":         ModuleSpec("addon", "elite", "asistente_ia", included_in_elite=True),
    "blood_labs":       ModuleSpec("addon", "elite", "labs", included_in_elite=False),
    "indoor_workout":   ModuleSpec("addon", "elite", "indoor", included_in_elite=True),
    "adaptive":         ModuleSpec("addon", "elite", "ajustes_adaptativos", included_in_elite=True),
    "huella":           ModuleSpec("addon", "agegroup", "retrospectiva", included_in_elite=True),
    # ── Rol ──────────────────────────────────────────────────────────
    "coach":            ModuleSpec("role", "basico"),
}


def addon_for(module_id: str) -> str | None:
    spec = MODULES.get(module_id)
    return spec.addon_id if spec else None
