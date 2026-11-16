"""BLOODLABS-AUTOREAD (BUILD 380).

Causa diagnosticada en produccion: la API de Anthropic respondia 400
"credit balance is too low" a toda llamada -> ParseUnavailable -> 503.
"""
import logging
import sys
import types

import pytest

from ..services import blood_lab_parser as bp

# Los 14 marcadores del MODULAB Clinica Alemana 30/05/2026 (peticion 02147223)
MODULAB = {
    "exam_date": "2026-05-30", "lab_name": "Clínica Alemana",
    "results": [
        {"key": "hb", "name_original": "Hemoglobina", "value": 16.5, "unit": "g/dL"},
        {"key": "hct", "name_original": "Hematocrito", "value": 47.5, "unit": "%"},
        {"key": "rbc", "name_original": "Eritrocitos", "value": 5.29, "unit": "10^6/uL"},
        {"key": "vitamin_d", "name_original": "Vitamina D", "value": 32.8, "unit": "ng/mL"},
        {"key": "b12", "name_original": "Vitamina B12", "value": 848, "unit": "pg/mL"},
        {"key": "ck", "name_original": "CK", "value": 120, "unit": "U/L"},
        {"key": "glucose", "name_original": "Glucosa", "value": 78, "unit": "mg/dL"},
        {"key": "cholesterol", "name_original": "Colesterol total", "value": 138, "unit": "mg/dL"},
        {"key": "ldl", "name_original": "LDL", "value": 81, "unit": "mg/dL"},
        {"key": "hdl", "name_original": "HDL", "value": 56.1, "unit": "mg/dL"},
        {"key": "triglycerides", "name_original": "Triglicéridos", "value": 48, "unit": "mg/dL"},
        {"key": "creatinine", "name_original": "Creatinina", "value": 0.91, "unit": "mg/dL"},
        {"key": "urea", "name_original": "Urea", "value": 42.4, "unit": "mg/dL"},
        {"key": "alt", "name_original": "ALT", "value": 30, "unit": "U/L"},
    ],
}


def _fake_anthropic(monkeypatch, exc):
    class _Msgs:
        def create(self, **kw):
            raise exc

    class _Client:
        def __init__(self, **kw):
            self.messages = _Msgs()

    mod = types.SimpleNamespace(Anthropic=_Client)
    monkeypatch.setitem(sys.modules, "anthropic", mod)


def test_billing_error_is_classified_and_logged(monkeypatch, caplog):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    _fake_anthropic(monkeypatch, RuntimeError(
        "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
        "'message': 'Your credit balance is too low to access the Anthropic API.'}}"))
    with caplog.at_level(logging.ERROR):
        with pytest.raises(bp.ParseUnavailable) as ei:
            bp._call_model("application/pdf", b"%PDF-1.4", "p")
    assert ei.value.reason == "billing"
    assert "[BILLING]" in caplog.text


def test_other_errors_keep_generic_reason(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    _fake_anthropic(monkeypatch, RuntimeError("timeout"))
    with pytest.raises(bp.ParseUnavailable) as ei:
        bp._call_model("application/pdf", b"%PDF-1.4", "p")
    assert ei.value.reason == "unavailable"


def test_parse_report_modulab_14_markers(monkeypatch):
    import json
    monkeypatch.setattr(bp, "_call_provider", lambda *a: json.dumps(MODULAB))
    out = bp.parse_report(b"%PDF-1.4\nfake")
    assert out["exam_date"] == "2026-05-30"
    assert out["lab_name"] == "Clínica Alemana"
    got = {m["key"]: m["value"] for m in out["markers"]}
    assert len(got) == 14
    for r in MODULAB["results"]:
        assert got[r["key"]] == pytest.approx(r["value"], rel=0.01), r["key"]
