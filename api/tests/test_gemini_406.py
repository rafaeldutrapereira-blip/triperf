"""BUILD 406 GEMINI: timeout largo (300 s) y modelo verificado (gemini-3.8-flash).

Nada sale a la red ni usa claves reales: urlopen se reemplaza por un doble.
"""
import io
import json
import socket
import urllib.error
import urllib.request

import pytest

from ..services import blood_lab_parser as bp
from .test_blood_lab_autoread_380 import MODULAB


class _Resp:
    def __init__(self, body):
        self._b = body

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok_body():
    return json.dumps({"candidates": [{"content": {"parts": [
        {"text": json.dumps(MODULAB)}]}}]}).encode()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_TIMEOUT", raising=False)
    monkeypatch.delenv("LAB_PARSER_PROVIDER", raising=False)


def test_defaults_300_and_model():
    assert bp.GEMINI_TIMEOUT == 300
    assert bp.GEMINI_MODEL == "gemini-3.8-flash"


def test_timeout_applied_is_300_and_env_overrides(monkeypatch):
    seen = []

    def fake_urlopen(req, timeout=None):
        seen.append(timeout)
        return _Resp(_ok_body())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    bp._gemini_post("https://x", "k", {})
    monkeypatch.setenv("GEMINI_TIMEOUT", "45")
    bp._gemini_post("https://x", "k", {})
    monkeypatch.setenv("GEMINI_TIMEOUT", "basura")
    bp._gemini_post("https://x", "k", {})
    assert seen == [300, 45, 300]


def test_url_carries_model_and_env_override(monkeypatch):
    urls = []
    monkeypatch.setattr(bp, "_gemini_post",
                        lambda url, key, payload: urls.append(url) or json.loads(_ok_body()))
    bp._call_gemini("application/pdf", b"%PDF", "p")
    monkeypatch.setenv("GEMINI_MODEL", "otro-modelo")
    bp._call_gemini("application/pdf", b"%PDF", "p")
    assert "/models/gemini-3.8-flash:generateContent" in urls[0]
    assert "/models/otro-modelo:generateContent" in urls[1]


def test_slow_response_between_90_and_300_is_parsed(monkeypatch):
    """Respuesta simulada de 270 s: con timeout 90 se rendia; con 300 llega a parsearse."""
    def slow_urlopen(req, timeout=None):
        if 270 > timeout:
            raise socket.timeout("timed out")
        return _Resp(_ok_body())

    monkeypatch.setattr(urllib.request, "urlopen", slow_urlopen)
    out = bp.parse_report(b"%PDF-1.4\nfake")
    assert out["exam_date"] == "2026-05-30"
    assert len(out["markers"]) == 14
    monkeypatch.setenv("GEMINI_TIMEOUT", "90")  # el comportamiento viejo sigue siendo rendirse
    with pytest.raises(bp.ParseUnavailable):
        bp._call_gemini("application/pdf", b"%PDF", "p")


def _http_error(code, body=""):
    return urllib.error.HTTPError("https://x", code, "err", {}, io.BytesIO(body.encode()))


def test_error_mapping_intact(monkeypatch):
    def boom429(url, key, payload):
        raise _http_error(429, "RESOURCE_EXHAUSTED")

    monkeypatch.setattr(bp, "_gemini_post", boom429)
    with pytest.raises(bp.ParseUnavailable) as e:
        bp._call_gemini("application/pdf", b"%PDF", "p")
    assert e.value.reason == "quota"

    def boom500(url, key, payload):
        raise _http_error(500, "boom")

    monkeypatch.setattr(bp, "_gemini_post", boom500)
    with pytest.raises(bp.ParseUnavailable) as e:
        bp._call_gemini("application/pdf", b"%PDF", "p")
    assert e.value.reason == "unavailable"

    class Billing(Exception):
        pass

    monkeypatch.setenv("LAB_PARSER_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    import anthropic

    def raise_billing(*a, **k):
        raise Billing("credit balance is too low")

    monkeypatch.setattr(anthropic.resources.messages.Messages, "create", raise_billing)
    with pytest.raises(bp.ParseUnavailable) as e:
        bp._call_provider("application/pdf", b"%PDF", "p")
    assert e.value.reason == "billing"
