"""BUILD 409 GEMINI-MODELO: default gemini-3.5-flash (3.8-flash daba 503), timeout intacto."""
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


def test_default_model_is_35_flash():
    assert bp.GEMINI_MODEL == "gemini-3.5-flash"


def test_url_uses_default_and_env_override(monkeypatch):
    urls = []
    monkeypatch.setattr(bp, "_gemini_post",
                        lambda url, key, payload: urls.append(url) or json.loads(_ok_body()))
    bp._call_gemini("application/pdf", b"%PDF", "p")
    monkeypatch.setenv("GEMINI_MODEL", "otro-modelo")
    bp._call_gemini("application/pdf", b"%PDF", "p")
    assert "/models/gemini-3.5-flash:generateContent" in urls[0]
    assert "/models/otro-modelo:generateContent" in urls[1]


def test_503_high_demand_is_unavailable_not_quota(monkeypatch):
    def boom503(url, key, payload):
        raise urllib.error.HTTPError(
            url, 503, "err", {}, io.BytesIO(b"This model is currently experiencing high demand"))

    monkeypatch.setattr(bp, "_gemini_post", boom503)
    with pytest.raises(bp.ParseUnavailable) as e:
        bp._call_gemini("application/pdf", b"%PDF", "p")
    assert e.value.reason == "unavailable"


def test_timeout_stays_300_and_expiry_is_unavailable(monkeypatch):
    assert bp.GEMINI_TIMEOUT == 300
    seen = []

    def slow(req, timeout=None):
        seen.append(timeout)
        raise socket.timeout("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", slow)
    with pytest.raises(bp.ParseUnavailable):
        bp._call_gemini("application/pdf", b"%PDF", "p")
    assert seen == [300]
