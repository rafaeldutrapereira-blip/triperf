"""
Regresión del insight diario en varios idiomas.

build_daily_insight genera la narrativa de forma nativa en ES/PT/EN (no hay
post-traducción). Estas pruebas verifican:
  1. La tabla insight_texts tiene los tres idiomas y los mismos marcadores.
  2. Con los mismos datos, la estructura del insight es idéntica en los tres
     idiomas (severidad, cantidad de bullets, drivers, CTA).
  3. PT y EN no contienen tokens en español y ES se mantiene.
"""
import re

import pytest

from api.services import insight_texts as it
from api.services.training_service import build_daily_insight

BASE = dict(tsb=0.0, atl=50.0, ctl=50.0, acwr=1.0, acwr_zone="optimal")

SCENARIOS = {
    "neutral": dict(BASE),
    "good": dict(BASE, tsb=20.0, hrv_trend=2.0),
    "danger": dict(BASE, acwr=1.7, acwr_zone="danger"),
    "sport_risk": dict(BASE, acwr_by_sport={
        "bike": {"label": "Ciclismo", "zone": "danger", "acwr": 1.6, "insufficient_data": False},
    }),
    "injury_high": dict(BASE, injury_risk={"level": "high", "score": 78}),
    "injury_critical": dict(BASE, injury_risk={"level": "critical", "score": 92}),
    "fatigue": dict(BASE, tsb=-25.0),
    "mental_low": dict(BASE, mental_score=30.0),
    "recovery_signal": dict(BASE, tsb=-10.0, hrv_last_night=40.0, hrv_7d_avg=50.0,
                            hrv_trend=-6.0, sleep_total_h=5.5, sleep_trend=-1.0),
    "gear_alert": dict(BASE, gear_alerts=[{"label": "Zapatillas", "life_pct": 85}]),
    "fresh_low_compliance": dict(BASE, tsb=20.0, compliance_week=40.0),
}

# Tokens del español que no deben aparecer en la narrativa de PT ni EN.
SPANISH_TOKENS = re.compile(
    r"Recomendación|bajale|Venís|sesión|rango|reducí|priorizá|evitá|tu cuerpo|tu entrenamiento|tus |\btu\b",
    re.IGNORECASE,
)


def _run(scenario, lang):
    return build_daily_insight(**SCENARIOS[scenario], lang=lang)


def _all_text(ins):
    parts = [ins["headline"], ins["message"], ins.get("cta_label") or ""]
    parts += ins["message_bullets"] + ins["message_technical"]
    parts += [d["label"] + " " + str(d["value"]) for d in ins["drivers"]]
    return " | ".join(p for p in parts if p)


# ── 1. Tabla de textos ───────────────────────────────────────────

def test_every_text_has_all_languages_with_same_placeholders():
    problems = []
    for key, entry in it.TEXTS.items():
        for lang in it.SUPPORTED:
            if not entry.get(lang):
                problems.append("%s sin texto en %s" % (key, lang))
        want = set(re.findall(r"\{(\w+)\}", entry["es"]))
        for lang in ("pt", "en"):
            got = set(re.findall(r"\{(\w+)\}", entry.get(lang, "")))
            if got != want:
                problems.append("%s %s: marcadores %s != %s" % (key, lang, sorted(got), sorted(want)))
    assert not problems, "\n".join(problems)


def test_tr_falls_back_to_spanish_for_unknown_language():
    assert it.tr("h_neutral", "fr") == it.TEXTS["h_neutral"]["es"]
    assert it.tr("h_neutral", None) == it.TEXTS["h_neutral"]["es"]
    assert it.tr("h_neutral", "pt") == "Tudo dentro da faixa normal"


# ── 2. Estructura idéntica entre idiomas ─────────────────────────

@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_structure_is_identical_across_languages(scenario):
    es, pt, en = (_run(scenario, l) for l in ("es", "pt", "en"))
    for other in (pt, en):
        assert other["severity"] == es["severity"]
        assert len(other["message_bullets"]) == len(es["message_bullets"])
        assert len(other["message_technical"]) == len(es["message_technical"])
        assert len(other["drivers"]) == len(es["drivers"])
        assert other["cta_href"] == es["cta_href"]
        assert (other["cta_label"] is None) == (es["cta_label"] is None)


# ── 3. Idioma nativo ─────────────────────────────────────────────

@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
@pytest.mark.parametrize("lang", ["pt", "en"])
def test_pt_and_en_have_no_spanish_tokens(scenario, lang):
    text = _all_text(_run(scenario, lang))
    found = SPANISH_TOKENS.findall(text)
    assert not found, "tokens en español en %s (%s): %s" % (lang, scenario, found)


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_headline_is_translated_in_each_language(scenario):
    es, pt, en = (_run(scenario, l) for l in ("es", "pt", "en"))
    assert pt["headline"] != es["headline"], scenario
    assert en["headline"] != es["headline"], scenario


def test_default_language_keeps_spanish_output():
    ins = build_daily_insight(**SCENARIOS["neutral"])
    assert ins["headline"] == "Todo en rango normal"
    assert ins["message_bullets"][1] == "Recomendación: seguí tu plan con normalidad."


def test_english_neutral_reads_naturally():
    ins = _run("neutral", "en")
    assert ins["headline"] == "Everything within normal range"
    assert ins["message_bullets"][1] == "Recommendation: follow your plan as usual."


def test_sport_name_is_localized_in_templates():
    en = _run("sport_risk", "en")
    pt = _run("sport_risk", "pt")
    assert en["headline"] == "Injury risk in Cycling"
    assert "in cycling" in en["message_bullets"][0]
    assert pt["headline"] == "Risco de lesão em Ciclismo"
    assert any(d["label"] == "ACWR Cycling" for d in en["drivers"])


def test_gear_alert_is_localized():
    en = _run("gear_alert", "en")
    assert any("My Gear" in b for b in en["message_technical"])
