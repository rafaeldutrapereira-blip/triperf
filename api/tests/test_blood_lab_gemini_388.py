"""GEMINI-GRATIS (BUILD 388): la lectura de PDF de Blood Labs despacha a Google Gemini.

Gemini se mockea en la capa HTTP (_gemini_post): nada sale a la red ni usa claves reales.
"""
import io
import json
import logging
import urllib.error

import pytest

from ..services import blood_lab_parser as bp
from .test_blood_lab_autoread_380 import MODULAB


def _gemini_resp(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def _http_error(code, body=""):
    return urllib.error.HTTPError("https://x", code, "err", {}, io.BytesIO(body.encode()))


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("LAB_PARSER_PROVIDER", raising=False)


def test_gemini_parse_modulab_14_markers(monkeypatch):
    seen = {}

    def fake_post(url, key, payload):
        seen.update(url=url, key=key, payload=payload)
        return _gemini_resp(json.dumps(MODULAB))

    monkeypatch.setattr(bp, "_gemini_post", fake_post)
    out = bp.parse_report(b"%PDF-1.4\nfake")
    assert out["exam_date"] == "2026-05-30"
    assert out["lab_name"] == "Clínica Alemana"
    got = {m["key"]: m["value"] for m in out["markers"]}
    assert len(got) == 14
    for r in MODULAB["results"]:
        assert got[r["key"]] == pytest.approx(r["value"], rel=0.01), r["key"]
    # contrato de la llamada: modelo vigente, inlineData PDF, consigna de texto
    assert bp.GEMINI_MODEL in seen["url"]
    parts = seen["payload"]["contents"][0]["parts"]
    assert parts[0]["inlineData"]["mimeType"] == "application/pdf"
    assert "Catalogo" in parts[1]["text"]
    assert seen["key"] == "test-key"


def test_gemini_model_overridable_by_env(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-xyz")
    urls = []
    monkeypatch.setattr(bp, "_gemini_post", lambda u, k, p: urls.append(u) or _gemini_resp("{}"))
    bp._call_gemini("application/pdf", b"%PDF-", "p")
    assert "gemini-xyz" in urls[0]


def test_gemini_image_sent_as_image_mime(monkeypatch):
    seen = {}
    monkeypatch.setattr(bp, "_gemini_post",
                        lambda u, k, p: seen.update(p=p) or _gemini_resp("{}"))
    bp._call_gemini("image/png", b"\x89PNG", "p")
    assert seen["p"]["contents"][0]["parts"][0]["inlineData"]["mimeType"] == "image/png"


def test_quota_429_is_classified_and_logged(monkeypatch, caplog):
    def boom(*a):
        raise _http_error(429, '{"error":{"status":"RESOURCE_EXHAUSTED"}}')

    monkeypatch.setattr(bp, "_gemini_post", boom)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(bp.ParseUnavailable) as ei:
            bp._call_gemini("application/pdf", b"%PDF-", "p")
    assert ei.value.reason == "quota"
    assert "[QUOTA]" in caplog.text
    assert "test-key" not in caplog.text


def test_other_gemini_errors_are_unavailable(monkeypatch):
    def boom(*a):
        raise _http_error(500, "boom")

    monkeypatch.setattr(bp, "_gemini_post", boom)
    with pytest.raises(bp.ParseUnavailable) as ei:
        bp._call_gemini("application/pdf", b"%PDF-", "p")
    assert ei.value.reason == "unavailable"
    monkeypatch.setattr(bp, "_gemini_post", lambda *a: (_ for _ in ()).throw(TimeoutError("t")))
    with pytest.raises(bp.ParseUnavailable) as ei:
        bp._call_gemini("application/pdf", b"%PDF-", "p")
    assert ei.value.reason == "unavailable"


def test_missing_key_is_unavailable(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(bp.ParseUnavailable):
        bp._call_gemini("application/pdf", b"%PDF-", "p")


def test_unreadable_json_is_unavailable(monkeypatch):
    monkeypatch.setattr(bp, "_gemini_post", lambda *a: _gemini_resp("no es json"))
    with pytest.raises(bp.ParseUnavailable):
        bp.parse_report(b"%PDF-1.4\nfake")


def test_response_without_candidates_is_unavailable(monkeypatch):
    monkeypatch.setattr(bp, "_gemini_post", lambda *a: {"promptFeedback": {"blockReason": "X"}})
    with pytest.raises(bp.ParseUnavailable):
        bp.parse_report(b"%PDF-1.4\nfake")


def test_dispatch_default_is_gemini(monkeypatch):
    calls = []
    monkeypatch.setattr(bp, "_call_gemini", lambda *a: calls.append("g") or "{}")
    monkeypatch.setattr(bp, "_call_model", lambda *a: calls.append("a") or "{}")
    bp._call_provider("application/pdf", b"%PDF-", "p")
    assert calls == ["g"]


def test_dispatch_anthropic_fallback(monkeypatch):
    monkeypatch.setenv("LAB_PARSER_PROVIDER", "Anthropic")
    calls = []
    monkeypatch.setattr(bp, "_call_gemini", lambda *a: calls.append("g") or "{}")
    monkeypatch.setattr(bp, "_call_model", lambda *a: calls.append("a") or "{}")
    bp._call_provider("application/pdf", b"%PDF-", "p")
    assert calls == ["a"]


def test_blood_labs_page_names_gemini_in_all_languages():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    html = (root / "blood_labs.html").read_text(encoding="utf-8")
    i18n = (root / "i18n.js").read_text(encoding="utf-8")
    assert 'data-i18n="bl_up_provider"' in html and "Gemini" in html
    assert i18n.count("bl_up_provider:") == 3
    assert "Anthropic" not in html
