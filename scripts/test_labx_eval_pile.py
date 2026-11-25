"""Tests de scripts/labx_eval_pile.py: un caso PASS y uno FAIL por punto.

Todo corre en repos git temporales con runners falsos para pytest/guardrails; no toca el
repo real ni la BD.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labx_eval_pile as ev  # noqa: E402


def git(repo, *a):
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                   check=True, capture_output=True)


def rev(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "ok.py").write_text("X = 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def commit(repo, files):
    base = rev(repo)
    for name, content in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "work")
    return base


GOOD_REPORT = "# REPORT\nCambio api/ok.py.\nTests: 10 passed.\nE2E gate: PASS.\nSHA {sha}\n"


def fake_tests(rc=0, out="10 passed in 1s"):
    return lambda repo: (rc, out)


def fake_guard(rc=0, out="PASS lint: ok\nGUARDRAILS PASS"):
    return lambda repo, base, allow, am, skip: (rc, out)


def run(repo, base, report_text, allow=("api/*",), **kw):
    (repo / "REPORT-x.md").write_text(report_text)
    return ev.evaluate(repo, base, "HEAD", str(repo / "REPORT-x.md"), allow,
                       tests_runner=kw.get("t", fake_tests()), guardrails_runner=kw.get("g", fake_guard()))


def stage_and_report(repo, files, report_tpl=GOOD_REPORT):
    """Commit de codigo, luego commit del reporte citando el SHA del codigo."""
    base = commit(repo, files)
    sha = rev(repo)[:7]
    (repo / "REPORT-x.md").write_text(report_tpl.format(sha=sha))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "report")
    return base


def status(res, name):
    return next(st for n, st, _ in res if n == name)


def detail(res, name):
    return next(m for n, _, m in res if n == name)


def test_pila_buena_6_de_6(repo):
    base = stage_and_report(repo, {"api/ok.py": "X = 2\n"})
    res = ev.evaluate(repo, base, "HEAD", str(repo / "REPORT-x.md"), ["api/*"],
                      tests_runner=fake_tests(), guardrails_runner=fake_guard())
    assert [st for _, st, _ in res] == ["PASS"] * 6, res


# 1 alcance
def test_alcance_fail_archivo_fuera(repo):
    base = stage_and_report(repo, {"api/ok.py": "X = 2\n", "otro/x.txt": "no\n"})
    res = ev.evaluate(repo, base, "HEAD", str(repo / "REPORT-x.md"), ["api/*"],
                      tests_runner=fake_tests(), guardrails_runner=fake_guard())
    assert status(res, "alcance") == "FAIL" and "otro/x.txt" in detail(res, "alcance")


def test_alcance_fail_sin_allow(repo):
    base = stage_and_report(repo, {"api/ok.py": "X = 2\n"})
    res = ev.evaluate(repo, base, "HEAD", str(repo / "REPORT-x.md"), [],
                      tests_runner=fake_tests(), guardrails_runner=fake_guard())
    assert status(res, "alcance") == "FAIL"


def test_alcance_pass_allow_leido_del_reporte(repo):
    base = stage_and_report(repo, {"api/ok.py": "X = 2\n"}, GOOD_REPORT + "ALLOW: api/*, sw.js\n")
    res = ev.evaluate(repo, base, "HEAD", str(repo / "REPORT-x.md"), [],
                      tests_runner=fake_tests(), guardrails_runner=fake_guard())
    assert status(res, "alcance") == "PASS"


# 2 reporte
def test_reporte_fail_no_nombra_archivo(repo):
    base = stage_and_report(repo, {"api/ok.py": "X = 2\n", "api/extra.py": "Y = 1\n"})
    res = ev.evaluate(repo, base, "HEAD", str(repo / "REPORT-x.md"), ["api/*"],
                      tests_runner=fake_tests(), guardrails_runner=fake_guard())
    assert status(res, "reporte") == "FAIL" and "extra.py" in detail(res, "reporte")


def test_reporte_fail_sin_sha(repo):
    base = stage_and_report(repo, {"api/ok.py": "X = 2\n"}, "api/ok.py 10 passed E2E PASS\n")
    res = ev.evaluate(repo, base, "HEAD", str(repo / "REPORT-x.md"), ["api/*"],
                      tests_runner=fake_tests(), guardrails_runner=fake_guard())
    assert status(res, "reporte") == "FAIL" and "SHA" in detail(res, "reporte")


# 3 tests
def test_tests_fail_suite_roja(repo):
    base = stage_and_report(repo, {"api/ok.py": "X = 2\n"})
    res = ev.evaluate(repo, base, "HEAD", str(repo / "REPORT-x.md"), ["api/*"],
                      tests_runner=fake_tests(1, "2 failed, 8 passed"), guardrails_runner=fake_guard())
    assert status(res, "tests") == "FAIL"


def test_tests_fail_reporte_sin_conteo(repo):
    base = stage_and_report(repo, {"api/ok.py": "X = 2\n"}, "api/ok.py E2E PASS {sha}\n")
    res = ev.evaluate(repo, base, "HEAD", str(repo / "REPORT-x.md"), ["api/*"],
                      tests_runner=fake_tests(), guardrails_runner=fake_guard())
    assert status(res, "tests") == "FAIL" and "conteo" in detail(res, "tests")


def test_tests_pass_con_pytest_log(repo, tmp_path):
    log = tmp_path / "p.txt"
    log.write_text("....\n12 passed, 1 skipped in 3s\n")
    ok, msg = ev.check_tests("10 passed", repo, str(log))
    assert ok and "12 passed" in msg


# 4 guardrails
def test_guardrails_fail(repo):
    base = stage_and_report(repo, {"api/ok.py": "X = 2\n"})
    res = ev.evaluate(repo, base, "HEAD", str(repo / "REPORT-x.md"), ["api/*"], tests_runner=fake_tests(),
                      guardrails_runner=fake_guard(1, "FAIL lint: roto\nGUARDRAILS FAIL (lint)"))
    assert status(res, "guardrails") == "FAIL" and "lint" in detail(res, "guardrails")


# 5 e2e
def test_e2e_fail_diff_de_ui_sin_mencion(repo):
    base = stage_and_report(repo, {"pagina.html": "<p>x</p>\n"}, "pagina.html 10 passed {sha}\nALLOW: pagina.html\n")
    res = ev.evaluate(repo, base, "HEAD", str(repo / "REPORT-x.md"), [],
                      tests_runner=fake_tests(), guardrails_runner=fake_guard())
    assert status(res, "e2e") == "FAIL"


def test_e2e_fail_declarado_pero_no_corrio(repo):
    base = stage_and_report(repo, {"pagina.html": "<p>x</p>\n"}, "pagina.html 10 passed {sha}\nE2E: no corrio\n")
    res = ev.evaluate(repo, base, "HEAD", str(repo / "REPORT-x.md"), ["pagina.html"],
                      tests_runner=fake_tests(), guardrails_runner=fake_guard())
    assert status(res, "e2e") == "FAIL"


def test_e2e_pass_explica_no_aplica_o_diff_sin_ui(repo):
    base = stage_and_report(repo, {"pagina.html": "<p>x</p>\n"},
                            "pagina.html 10 passed {sha}\nE2E: no aplica, solo copy estatico\n")
    res = ev.evaluate(repo, base, "HEAD", str(repo / "REPORT-x.md"), ["pagina.html"],
                      tests_runner=fake_tests(), guardrails_runner=fake_guard())
    assert status(res, "e2e") == "PASS"
    base2 = stage_and_report(repo, {"docs/a.md": "x\n"}, "docs/a.md 10 passed {sha}\n")
    res2 = ev.evaluate(repo, base2, "HEAD", str(repo / "REPORT-x.md"), ["docs/*"],
                       tests_runner=fake_tests(), guardrails_runner=fake_guard())
    assert status(res2, "e2e") == "PASS" and "no aplica" in detail(res2, "e2e")


# 6 migraciones y secretos
def test_seguridad_fail_migracion_no_autorizada(repo):
    base = stage_and_report(repo, {"alembic/versions/abc_nueva.py": "x = 1\n"},
                            "alembic/versions/abc_nueva.py 10 passed E2E PASS {sha}\n")
    res = ev.evaluate(repo, base, "HEAD", str(repo / "REPORT-x.md"), ["alembic/*"],
                      tests_runner=fake_tests(), guardrails_runner=fake_guard())
    assert status(res, "seguridad") == "FAIL" and "migracion" in detail(res, "seguridad")


def test_seguridad_fail_secreto(repo):
    base = stage_and_report(repo, {"api/ok.py": 'password = "hunter2"\n'})
    res = ev.evaluate(repo, base, "HEAD", str(repo / "REPORT-x.md"), ["api/*"],
                      tests_runner=fake_tests(), guardrails_runner=fake_guard())
    assert status(res, "seguridad") == "FAIL"


# pila vieja: head != HEAD usa worktree temporal y lo limpia
def test_pila_vieja_usa_worktree_y_lo_limpia(repo):
    base = stage_and_report(repo, {"api/ok.py": "X = 2\n"})
    head = rev(repo)
    commit(repo, {"api/later.py": "Z = 1\n"})
    res = ev.evaluate(repo, base, head, str(repo / "REPORT-x.md"), ["api/*"],
                      tests_runner=fake_tests(), guardrails_runner=fake_guard())
    assert [st for _, st, _ in res] == ["PASS"] * 5 + ["PASS"]
    assert "ACTUAL" in detail(res, "tests")
    wts = subprocess.run(["git", "-C", str(repo), "worktree", "list"], capture_output=True, text=True).stdout
    assert len(wts.strip().splitlines()) == 1


def test_main_exit_code(repo, capsys, monkeypatch):
    base = stage_and_report(repo, {"api/ok.py": "X = 2\n", "otro/x.txt": "no\n"})
    monkeypatch.setattr(ev, "run_pytest", fake_tests())
    monkeypatch.setattr(ev, "run_guardrails", fake_guard())
    monkeypatch.setattr(ev, "evaluate", lambda *a, **k: [("alcance", "FAIL", "x")] + [(n, "PASS", "") for n in ev.POINTS[1:]])
    rc = ev.main(["--base", base, "--head", "HEAD", "--report", "REPORT-x.md", "--repo", str(repo)])
    out = capsys.readouterr().out
    assert rc == 1 and "EVAL: 5/6 FAIL" in out
