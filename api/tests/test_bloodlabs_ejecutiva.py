"""BLOODLABS-EJECUTIVA (BUILD 389): Blood Labs como pagina ejecutiva en capas.

Cubre el backend (historial completo en timeline y correlacion, sin tope de
12 meses ni de 120 dias), el fixture de 5 examenes como los de produccion de la
cuenta coach, los estados vacios y el banner de sexo faltante; y los asserts
estaticos de la pagina (nada se elimina, capas L1/L2/L3, i18n ES/PT/EN).
"""
import json
import re
from pathlib import Path

import pytest

from ..models import BloodLabExam, GarminTrainingLoad
from ..routes.blood_lab_routes import regenerate_alerts_for_user
from .conftest import login
from .text_match import squash

ROOT = Path(__file__).resolve().parents[2]


def _read(name):
    return (ROOT / name).read_text(encoding="utf-8")


# 10 marcadores en rango (examen mas reciente de produccion: 10 de 10)
OK_10 = {
    "hb": 15.0, "hct": 45.0, "ferritin": 90.0, "vitamin_d": 50.0, "cortisol": 12.0,
    "ck": 150.0, "hba1c": 5.2, "glucose": 85.0, "creatinine": 1.0, "crp": 0.5,
}

# (fecha, laboratorio, valores) — los 5 examenes reales de la cuenta coach
EXAMS_5 = [
    ("2024-02-08", "CLC", {"creatinine": 2.5, "hb": 15.0, "ferritin": 90.0}),
    ("2025-03-27", "CLC", {"hb": 15.0, "ferritin": 85.0, "vitamin_d": 45.0}),
    ("2026-01-17", "MODULAB / Alemana",
     dict({"hdl": 25.0, "hb": 15.0, "ferritin": 80.0, "vitamin_d": 48.0},
          **{"extra_%d" % i: float(i) for i in range(31)})),   # 35 valores
    ("2026-01-22", "CLC", {"hdl": 25.0, "hb": 14.8, "ferritin": 82.0}),
    ("2026-09-29", "RedSalud", dict(OK_10)),
]


@pytest.fixture
def coach5(client, db, coach_user):
    """Cuenta coach con sexo 'm', 5 examenes y carga de entrenamiento en cada fecha."""
    coach_user.sexo = "m"
    db.commit()
    for i, (d, lab, vals) in enumerate(EXAMS_5):
        db.add(BloodLabExam(user_id=coach_user.id, date_iso=d, lab_name=lab,
                            values_json=json.dumps(vals)))
        db.add(GarminTrainingLoad(user_id=coach_user.id, date_iso=d,
                                  ctl=40.0 + i, atl=50.0 + i, tsb=-10.0 + i))
    db.flush()
    regenerate_alerts_for_user(coach_user, db)
    db.commit()
    token = login(client, "coach@test.com", "CoachPass123")
    return {"Authorization": "Bearer " + token}


@pytest.fixture
def coach0(client, db, coach_user):
    """Cuenta sin examenes ni sexo (como la cuenta admin de produccion)."""
    token = login(client, "coach@test.com", "CoachPass123")
    return {"Authorization": "Bearer " + token}


# ───────────────────────── L1: datos con 5 examenes ─────────────────────────

def test_l1_lista_cinco_examenes_con_fecha_lab_y_conteo(client, coach5):
    r = client.get("/api/labs/exams", headers=coach5)
    assert r.status_code == 200
    ex = r.json()
    assert len(ex) == 5
    assert ex[0]["date_iso"] == "2026-09-29" and ex[0]["lab_name"] == "RedSalud"
    assert ex[0]["markers"] == 10
    assert {e["markers"] for e in ex} >= {35}      # MODULAB con 35 valores
    assert ex[-1]["date_iso"] == "2024-02-08"


def test_l1_ultimo_examen_diez_de_diez_y_trs_100(client, coach5):
    s = client.get("/api/labs/summary", headers=coach5).json()
    assert s["has_labs"] and s["latest_date"] == "2026-09-29"
    assert s["total_exams"] == 5
    assert s["markers_ok"] == 10 and s["total_markers"] == 10
    assert s["markers_warning"] == 0 and s["markers_critical"] == 0
    assert isinstance(s["next_recommended_in_days"], int)
    ti = client.get("/api/labs/training-impact", headers=coach5).json()
    assert ti["has_labs"] and ti["trs"] == 100
    assert ti["exam_date"] == "2026-09-29"


def test_l1_alertas_de_examenes_anteriores_dicen_su_examen(client, coach5):
    al = client.get("/api/labs/alerts", headers=coach5).json()
    assert al, "los examenes viejos (creatinina 2024, HDL ene 2026) generan alertas"
    assert {a["exam_date"] for a in al} <= {"2024-02-08", "2026-01-17", "2026-01-22"}
    assert "2026-09-29" not in {a["exam_date"] for a in al}
    assert all(a["exam_id"] for a in al)
    # el detalle del ultimo examen no trae alertas propias
    last = client.get("/api/labs/exams", headers=coach5).json()[0]["id"]
    det = client.get("/api/labs/exams/" + last, headers=coach5).json()
    assert det["alerts"] == [] and det["ai_interpretation"] is None


# ───────────────────── Tendencias: historial completo ───────────────────────

def test_tendencias_sin_tope_de_12_meses(client, coach5):
    t = client.get("/api/labs/timeline", headers=coach5).json()
    assert t["exam_count"] == 5
    assert [x["exam_date"] for x in t["timeline"]] == [e[0] for e in EXAMS_5]
    assert t["date_range"] == {"from": "2024-02-08", "to": "2026-09-29"}
    # hemoglobina (hb) aparece en los 5 examenes viejos y nuevos: hay serie dibujable
    assert sum(1 for x in t["timeline"] if x["hemoglobin"] is not None) == 5
    assert sum(1 for x in t["timeline"] if x["ferritin"] is not None) == 5


def test_tendencias_con_months_sigue_acotando_si_se_pide(client, coach5):
    t = client.get("/api/labs/timeline?months=6", headers=coach5).json()
    assert t["exam_count"] < 5
    assert t["date_range"]["to"] == "2026-09-29"
    # fuera de rango = historial completo, no 12 meses
    assert client.get("/api/labs/timeline?months=9999", headers=coach5).json()["exam_count"] == 5


def test_correlaciones_estadisticas_usan_todo_el_historial(client, coach5):
    c = client.get("/api/labs/correlations", headers=coach5).json()
    assert c["exam_count"] == 5


# ───────────────────── Correlacion Garmin: 5 examenes ───────────────────────

def test_correlacion_muestra_los_cinco_examenes_con_ctl_atl_tsb(client, coach5):
    rows = client.get("/api/labs/correlation", headers=coach5).json()
    assert [r["date_iso"] for r in rows] == [e[0] for e in EXAMS_5]
    for i, r in enumerate(rows):
        assert r["ctl"] == 40.0 + i and r["atl"] == 50.0 + i
        assert r["tsb"] == -10.0 + i or (r["tsb"] is None and -10.0 + i == 0)


def test_correlacion_con_days_explicito_sigue_acotando(client, coach5):
    assert len(client.get("/api/labs/correlation?days=90", headers=coach5).json()) <= 1
    assert len(client.get("/api/labs/correlation?days=3650", headers=coach5).json()) == 5


def test_correlacion_sin_carga_en_la_fecha_devuelve_null_no_cero(client, db, coach5, coach_user):
    db.query(GarminTrainingLoad).filter(GarminTrainingLoad.user_id == coach_user.id).delete()
    db.commit()
    rows = client.get("/api/labs/correlation", headers=coach5).json()
    assert len(rows) == 5 and all(r["ctl"] is None and r["atl"] is None for r in rows)


# ───────────────────────────── Estados vacios ───────────────────────────────

def test_cuenta_sin_examenes_endpoints_honestos(client, coach0):
    assert client.get("/api/labs/exams", headers=coach0).json() == []
    assert client.get("/api/labs/summary", headers=coach0).json()["has_labs"] is False
    assert client.get("/api/labs/training-impact", headers=coach0).json()["has_labs"] is False
    assert client.get("/api/labs/correlation", headers=coach0).json() == []
    t = client.get("/api/labs/timeline", headers=coach0).json()
    assert t["timeline"] == [] and t["exam_count"] == 0
    assert client.get("/api/labs/alerts", headers=coach0).json() == []


def test_pagina_dice_en_llano_que_la_cuenta_no_tiene_examenes():
    h = _read("blood_labs.html")
    i = _read("i18n.js")
    assert 'id="bl-empty-account"' in h and 'data-i18n="bl_empty_account"' in h
    assert "Esta cuenta no tiene exámenes de sangre registrados." in i
    assert i.count("bl_empty_account:") == 3
    # la rama de cuenta vacia pinta chips honestos (no guiones)
    sq = squash(h)
    assert squash("if (!EXAMS.length) {\n renderSummaryChips();") in sq
    assert 'id="chip-score" data-i18n="bl_chip_nodata">Sin datos' in re.sub(r"\s+", " ", h)


def test_sin_guiones_mudos_en_los_estados_de_la_pagina():
    h = _read("blood_labs.html")
    sq = squash(h)
    # caja de IA: estado en palabras, nunca "—"
    assert "Aúnnogenerada" in sq
    assert "box.textContent=d.interpretation||'—'" not in sq.replace('"', "'")
    assert "textContent=d.ai_narrative||'—'" not in sq.replace('"', "'")
    assert "setKpi('trs','—')" not in sq.replace('"', "'")
    # radar y tendencias explican por que no hay grafico
    for key in ("bl_radar_sex", "bl_radar_none", "bl_tr_one_exam", "bl_tr_no_common",
                "bl_gr_none", "bl_gr_noload", "bl_ai_failed_net"):
        assert key in h, key


def test_ia_sin_sexo_422_y_con_estado_explicado(client, coach0):
    # cuenta sin sexo: el endpoint avisa; la pagina explica el estado (bl_ai_state_sex)
    r = client.post("/api/labs/exams/inexistente/analyze", headers=coach0, json={})
    assert r.status_code == 422
    assert "bl_ai_state_sex" in _read("blood_labs.html")


# ───────────────────────── Banner de sexo faltante ──────────────────────────

def test_sexo_faltante_con_examenes_vacia_alertas_y_trs(client, db, coach_user):
    db.add(BloodLabExam(user_id=coach_user.id, date_iso="2026-09-29", lab_name="RedSalud",
                        values_json=json.dumps(OK_10)))
    db.commit()
    assert coach_user.sexo is None
    h = {"Authorization": "Bearer " + login(client, "coach@test.com", "CoachPass123")}
    s = client.get("/api/labs/summary", headers=h).json()
    assert s["has_labs"] and s["sex_missing"] is True and s["markers_ok"] is None
    ti = client.get("/api/labs/training-impact", headers=h).json()
    assert ti["sex_missing"] is True and ti["trs"] is None
    assert client.get("/api/labs/alerts", headers=h).json() == []
    ex = client.get("/api/labs/exams", headers=h).json()[0]
    det = client.get("/api/labs/exams/" + ex["id"], headers=h).json()
    assert det["sex_missing"] is True


def test_banner_de_sexo_y_frase_que_lo_explica_en_la_pagina():
    h = _read("blood_labs.html")
    i = _read("i18n.js")
    assert 'id="sex-missing-banner"' in h and 'href="athlete_profile.html#p-sexo"' in h
    sq = squash(h)
    assert squash("document.getElementById('sex-missing-banner').style.display = EXAMS.length && sexMissing()") in sq
    assert "bl_plain_sex_missing" in h and "bl_alerts_sex_missing" in h
    assert "bl_chip_needs_sex" in h and i.count("bl_chip_needs_sex:") == 3


# ──────────────────── Pagina: capas, selector, inventario ───────────────────

IDS = [
    "sel-exam", "sel-comp", "comp-label", "exam-ctx-lbl", "exam-count-lbl",
    "btn-delete-exam", "chip-score", "chip-alerts", "chip-alert-n", "chip-exams",
    "bl-disclaimer", "bl-plain", "bl-plain-h", "bl-plain-s", "bl-l1-chips",
    "alerts-container", "bl-trs-read", "bl-variations", "clinical-summary",
    "bl-systems", "bl-ver-todo", "kpi-trs", "kpi-markers", "kpi-next", "ch-radar",
    "radar-empty", "btn-ai-analyze", "ai-interpretation-box", "bm-table-container",
    "tab-resumen", "tab-trends", "tab-garmin", "tab-import", "trend-content",
    "trend-single", "garmin-empty", "ch-ctl-overlay", "corr-table", "stat-corr-content",
    "inp-file", "btn-review-exam", "btn-save-exam", "btn-upload-exam", "upload-box",
]


def test_paso_0_nada_se_elimina_y_las_capas_estan_en_orden():
    h = _read("blood_labs.html")
    for i in IDS:
        assert 'id="%s"' % i in h, i
    for tab in ("resumen", "trends", "garmin", "import"):
        assert 'data-tab="%s"' % tab in h
    l1 = h.index('id="bl-plain"')
    l2 = h.index('id="alerts-container"')
    l3 = h.index('<details class="bl-all')
    assert l1 < l2 < l3
    assert h.index('id="bl-disclaimer"') < l1
    assert h.index('id="bm-table-container"') > l3 and h.index('id="ch-radar"') > l3


def test_selector_con_fecha_laboratorio_y_conteo():
    sq = squash(_read("blood_labs.html"))
    assert squash("function examOptionLabel(e)") in sq
    assert "fmtDate(e.date_iso)" in sq and "e.lab_name" in sq and "e.markers" in sq
    assert "renderExamCount()" in sq
    assert "bl_sel_count_many" in sq and "bl_sel_markers" in sq


def test_l1_frase_en_llano_con_chips():
    h = _read("blood_labs.html")
    i = _read("i18n.js")
    for k in ("bl_l1_ok", "bl_l1_bad_many", "bl_l1_noeval", "bl_l1_last", "bl_l1_next", "bl_l1_trs"):
        assert k in h and i.count(k + ":") == 3, k
    assert "Tu sangre está bien:\u00a0{ok} de {total} marcadores en rango, sin alertas activas. Último examen {date}." in i
    assert "Hay {n} cosas a mirar: {list}{more}. Examen del {date}." in i
    assert "Restricción de entrenamiento (TRS):" in i       # nombre primero, sigla despues


def test_l2_alertas_con_examen_de_origen_y_variaciones_con_contexto():
    sq = squash(_read("blood_labs.html"))
    assert squash("function alertSrcTag(a)") in sq and "a.exam_date" in sq
    assert "bl_alert_src_other" in sq and "bl_alert_src_cur" in sq
    assert squash("function renderVariations(cur, comp)") in sq
    assert "bl_var_head" in sq                      # dice de que dos examenes salen
    assert squash("function renderTrsRead()") in sq


def test_l3_historial_completo_sin_topes_en_el_cliente():
    h = _read("blood_labs.html")
    assert "months=12" not in h and "days=120" not in h
    assert "/labs/timeline?all=1" in h and "/labs/correlation?all=1" in h
    assert "bl_tr_full" in h
    assert "bl_th_ctl" in h and "bl_th_atl" in h and "bl_th_tsb" in h


def test_radar_no_inventa_un_50_y_se_redibuja_al_abrir_el_detalle():
    sq = squash(_read("blood_labs.html"))
    assert "push(m.pct!=null?m.pct:50)" not in sq.replace('"', "'")
    assert squash("if (m.cat && byCat[m.cat] && m.pct != null)") in sq
    assert squash("d.addEventListener('toggle'") in sq and "renderRadar(curExam())" in sq


def test_i18n_nuevas_claves_en_tres_idiomas():
    h = _read("blood_labs.html")
    i = _read("i18n.js")
    keys = set(re.findall(r"""_t\(\s*['"](bl_[a-z0-9_]+)['"]""", h))
    keys |= set(re.findall(r'data-i18n="(bl_[a-z0-9_]+)"', h))
    keys |= set(re.findall(r"""tpl\(\s*(?:[^'"]*?\?\s*)?['"](bl_[a-z0-9_]+)['"]""", h))
    assert len(keys) > 40
    missing = [k for k in sorted(keys) if i.count(k + ":") != 3]
    assert missing == [], missing


def test_build_389_y_sellos():
    m = re.search(r"BUILD_VERSION = '(\d+)'", _read("sw.js"))
    assert m and int(m.group(1)) >= 389
    assert "i18n.js?v=389" in _read("blood_labs.html")
    assert "'/i18n.js?v=389'" in _read("sw.js")
    assert "i18n.js?v=389" in _read("athlete-app.html")


def test_no_se_toco_el_parser_ni_el_proveedor():
    # BLOODLABS-EJECUTIVA no cambia la seleccion de proveedor de la 388
    src = _read("api/services/blood_lab_parser.py")
    assert "LAB_PARSER_PROVIDER" in src
    assert "bl_up_provider" in _read("blood_labs.html")
