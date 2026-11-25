"""Pruebas del gate E2E (sin levantar servidor ni navegador)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labx_e2e_gate as g  # noqa: E402


def test_every_e2e_file_is_classified():
    files = {p.name for p in g.E2E_DIR.glob("test_*.py")}
    assert files == set(g.CRITICAL_FILES) | set(g.NOT_COVERED_REASON)
    assert not set(g.CRITICAL_FILES) & set(g.NOT_COVERED_REASON)


@pytest.mark.parametrize("url", ["https://labxperformanceapp.com", "http://34.145.118.232:8000",
                                 "http://evil.localhost.example.com"])
def test_refuses_non_local_urls(url):
    with pytest.raises(SystemExit):
        g._assert_local(url)


def test_accepts_localhost():
    g._assert_local("http://localhost:8001")


def test_allow_prod_is_refused():
    with pytest.raises(SystemExit):
        g.main(["--allow-prod"])  # argparse no lo conoce
    with pytest.raises(SystemExit):
        g.main(["x", "--allow-prod"])  # pasado como argumento extra a pytest


def test_server_env_is_isolated(tmp_path):
    env = g.server_env(tmp_path / "x.db", 8001)
    assert env["APP_ENV"] == "test" and env["DATABASE_URL"].startswith("sqlite:///")
    assert "labx_coach.db" not in env["DATABASE_URL"]
    assert env["E2E_BASE_URL"] == "http://localhost:8001"
