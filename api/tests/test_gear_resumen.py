"""GEAR-RESUMEN (BUILD 353) — Equipamiento abre con 'Qué necesita atención?'."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
H = (ROOT / "gear.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")

GUARD_IDS = [
    "alert-banner", "alert-text", "pane-shoes", "pane-bikes", "shoes-grid", "bikes-grid",
    "bikes-upgrade", "bikes-body", "modal-shoe", "modal-edit-shoe", "modal-schedule",
    "modal-bike", "modal-component", "modal-service", "shoe-brand", "shoe-model",
    "shoe-nickname", "shoe-type", "shoe-target", "shoe-default", "edit-shoe-id",
    "edit-shoe-target", "sched-shoe-id", "sched-days", "sched-start-date", "sched-force",
    "sched-backfill-btn", "bike-brand", "bike-model", "bike-type", "bike-default",
    "comp-bike-id", "comp-type", "comp-label", "comp-unit", "comp-target", "comp-charge",
    "service-bike-id", "service-comp-id", "service-desc", "service-cost", "service-date",
    "service-reset",
]


def test_ningun_id_desaparece():
    for i in GUARD_IDS:
        assert f'id="{i}"' in H, i


def test_resumen_antes_de_las_listas_y_banner_integrado():
    assert H.count('id="alert-banner"') == 1
    i_sum = H.index('id="gear-attn-list"')
    assert i_sum < H.index('id="pane-shoes"')
    assert 'data-i18n="gear_attn_title"' in H


def test_km_solo_del_calculo_existente():
    # km restantes = target - acumulado de los datos del backend; sin constantes inventadas
    assert "s.target_km - s.accumulated_km" in H
    assert "c.target_value - c.accumulated_value" in H
    assert "c.tracking_unit === 'km'" in H


def test_i18n_tres_idiomas():
    keys = ["gear_attn_title", "gear_attn_all_ok", "gear_attn_more", "gear_attn_shoe_left",
            "gear_attn_shoe_over", "gear_attn_comp_over", "gear_attn_comp_left", "gear_attn_comp_pct"]
    for k in keys:
        assert len(re.findall(rf"^\s*{k}:", I18N, re.M)) == 3, k


def test_build_353():
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    m = re.search(r"BUILD_VERSION = '(\d+)'", sw)
    assert m and int(m.group(1)) >= 353
