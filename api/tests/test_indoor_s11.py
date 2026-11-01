"""S11 — Indoor simple y automática: guardar sincroniza con el reloj, sin credenciales Garmin."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDOOR = (ROOT / "indoor_workout.html").read_text(encoding="utf-8-sig")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")


def _page_js() -> str:
    return "\n".join(re.findall(r"<script>(.*?)</script>", INDOOR, re.S))


def test_pagina_sin_formulario_de_credenciales_garmin():
    low = INDOOR.lower()
    assert 'type="password"' not in low and "type='password'" not in low
    assert "<form" not in low
    assert "send-to-garmin" not in low
    assert "sendtogarmin" not in low
    assert "btn-send-garmin" not in low


def test_el_endpoint_garmin_sigue_en_backend():
    # Solo se retiró la UI de Indoor: el endpoint queda (otros flujos lo usan).
    assert "send-to-garmin" in (ROOT / "api/routes/athlete_routes.py").read_text(encoding="utf-8")


def test_guardar_dispara_un_unico_envio_automatico():
    js = _page_js()
    # el único POST a send-to-watch vive en doSend, y saveWorkout tiene guarda anti doble click
    assert js.count("/send-to-watch'") == 1
    assert "if (saving) return;" in js
    assert "afterSave(wo)" in js and "doSend(wo.id)" in js
    # preferencia prendida por defecto
    assert "localStorage.getItem(LS_AUTO) !== '0'" in js


def test_exportar_es_un_menu_con_los_cuatro_formatos():
    js = _page_js()
    for fmt in ("zwo", "erg", "mrc", "tcx"):
        assert "fmt: '%s'" % fmt in js
    # ya no hay botones sueltos de descarga en el HTML
    assert 'onclick="exportZWO()"' not in INDOOR
    assert 'onclick="exportTCX()"' not in INDOOR


def test_claves_i18n_nuevas_en_es_pt_en():
    keys = set(re.findall(r"\b(iw_(?:tpl|ctl|sel|watch_state|watch_on|watch_off|watch_auto|exp_only|toast_saved_|btn_export|btn_duplicate|btn_detail|copy_suffix|toast_dup)[a-z_]*)\s*:", INDOOR + I18N))
    assert len(keys) >= 25
    for k in keys:
        assert len(re.findall(r"\b%s\s*:" % re.escape(k), I18N)) == 3, k
