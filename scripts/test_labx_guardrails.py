"""Tests de scripts/labx_guardrails.py: un caso PASS y uno FAIL por chequeo.

Todo corre en repos git temporales; no toca el repo real ni la BD.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labx_guardrails as g  # noqa: E402

PY = sys.executable


def git(repo, *a):
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                   check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "ok.py").write_text("X = 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def base_of(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


def commit(repo, files):
    base = base_of(repo)
    for name, content in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "work")
    return base


# a. lint + compilacion (cmds reales de flake8/compileall sobre un api/ temporal)
LINT_REAL = [g.LINT_CMDS[0], g.LINT_CMDS[2]]


def test_lint_pass(repo):
    assert g.check_lint(repo, LINT_REAL)[0] is True


def test_lint_fail_syntax_error(repo):
    (repo / "api" / "bad.py").write_text("def f(:\n")
    assert g.check_lint(repo, LINT_REAL)[0] is False


# b. tests
def test_tests_pass(repo):
    assert g.check_tests(repo, [PY, "-c", "raise SystemExit(0)"])[0] is True


def test_tests_fail(repo):
    assert g.check_tests(repo, [PY, "-c", "raise SystemExit(1)"])[0] is False


# c. build
def test_build_pass(repo):
    assert g.check_build(repo, [PY, "-c", "pass"])[0] is True


def test_build_fail_missing_script(repo):
    assert g.check_build(repo)[0] is False  # el repo temporal no tiene scripts/build_www.py


# d. reporte con SHA
def test_report_pass(repo):
    base = base_of(repo)
    (repo / "REPORT-labx-x.md").write_text("x")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "w")
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True,
                         text=True).stdout.strip()
    (repo / "REPORT-labx-x.md").write_text(f"commit {sha}\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "w2")
    assert g.check_report(repo, base)[0] is True


def test_report_fail_without_sha(repo):
    base = commit(repo, {"REPORT-labx-x.md": "sin sha aqui\n"})
    assert g.check_report(repo, base)[0] is False


def test_report_fail_no_report_file(repo):
    base = commit(repo, {"api/a.py": "A = 1\n"})
    assert g.check_report(repo, base)[0] is False


# e. alcance
def test_scope_pass(repo):
    base = commit(repo, {"api/a.py": "A = 1\n", "REPORT-labx-x.md": "r"})
    assert g.check_scope(repo, base, ["api/a.py"])[0] is True


def test_scope_fail_file_outside(repo):
    base = commit(repo, {"api/a.py": "A = 1\n", "otro.html": "<p>"})
    ok, msg = g.check_scope(repo, base, ["api/*.py"])
    assert ok is False and "otro.html" in msg


# f. migraciones
def test_migrations_pass_when_authorized(repo):
    base = commit(repo, {"alembic/versions/abc123_x.py": "x = 1\n"})
    assert g.check_migrations(repo, base, ["abc123_x"])[0] is True


def test_migrations_fail_when_not_authorized(repo):
    base = commit(repo, {"alembic/versions/abc123_x.py": "x = 1\n"})
    assert g.check_migrations(repo, base, [])[0] is False


# g. secretos (las cadenas se arman partidas para que este archivo no dispare el escaneo)
SYNTHETIC = [
    "pass" + "word = 'hunter2'",
    "api" + "_key = 'abc'",
    "sec" + "ret = 'abc'",
    "-----BEGIN RSA PRIVATE" + " KEY-----",
    "Authorization:" + " Bearer abc.def",
]


def test_secrets_pass_clean_diff(repo):
    base = commit(repo, {"api/a.py": "A = os.environ['X']\n", ".env.example": "X=\n"})
    assert g.check_secrets(repo, base)[0] is True


@pytest.mark.parametrize("line", SYNTHETIC)
def test_secrets_fail_added_line(repo, line):
    base = commit(repo, {"api/a.py": line + "\n"})
    assert g.check_secrets(repo, base)[0] is False


def test_secrets_fail_env_file(repo):
    base = commit(repo, {".env.production": "X=1\n"})
    assert g.check_secrets(repo, base)[0] is False


def test_secrets_ignores_removed_lines(repo):
    (repo / "api" / "old.py").write_text("pass" + "word = 'x'\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "old")
    base = commit(repo, {"api/old.py": "Y = 1\n"})
    assert g.check_secrets(repo, base)[0] is True


# CLI de punta a punta: sale 1 si algo falla y --skip queda declarado
def test_cli_exit_code_and_skip(repo, capsys):
    base = commit(repo, {"api/a.py": "A = 1\n"})
    skip = ["--skip", "lint", "--skip", "tests", "--skip", "build", "--skip", "report"]
    rc = g.main(["--repo", str(repo), "--base", base, "--allow", "api/a.py", *skip])
    out = capsys.readouterr().out
    assert rc == 0 and "SKIP tests" in out and "PASS scope" in out
    rc = g.main(["--repo", str(repo), "--base", base, "--allow", "nada", *skip])
    assert rc == 1 and "FAIL scope" in capsys.readouterr().out
