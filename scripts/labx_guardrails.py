"""Guardrails pre-push de LabX: reglas que el sistema impone a la pila.

Corre antes de que una pila reporte DONE y sale distinto de 0 si algo falla.
Vigila a la PILA (diff, tests, build, secretos), no a quien hace el push.

Uso:
    python scripts/labx_guardrails.py --base <sha> --allow <glob> [--allow <glob> ...]
                                      [--allow-migrations <nombre>] [--skip <check>]

Chequeos (una linea PASS/FAIL cada uno): lint, tests, build, report, scope,
migrations, secrets. Los globs de --allow usan fnmatch sobre rutas con "/"
(un "*" tambien cruza directorios). Los REPORT-*.md y los dos archivos de este
guardrail siempre estan permitidos. --skip existe solo para verificar historia
(commits viejos sin el hook de reporte o sin correr la suite completa): el
resultado lo declara como SKIP y queda en la salida.
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

ALWAYS_ALLOWED = ["REPORT-*.md", "scripts/labx_guardrails.py", "scripts/test_labx_guardrails.py"]

# make lint no existe en la PC de Rafael (sin make) y flake8 con las opciones del
# Makefile da ~7300 avisos de estilo sobre el HEAD limpio (alineacion intencional).
# Se fija lo que si corresponde: lo mismo que el job Lint del CI (errores reales)
# + bandit HIGH como el Makefile + compilacion.
LINT_CMDS = [
    [sys.executable, "-m", "flake8", "api/", "--exclude=api/tests/,__pycache__,api/migrations/",
     "--select=E9,F63,F7,F821,F822,F823"],
    [sys.executable, "-m", "bandit", "-r", "api/", "--skip", "B101,B601",
     "--severity-level", "high", "-q"],
    [sys.executable, "-m", "compileall", "-q", "api/"],
]
TEST_CMD = [sys.executable, "-m", "pytest", "api/tests/", "-q", "--tb=short",
            "--cov=api", "--cov-report=term", "--cov-fail-under=70"]
BUILD_CMD = [sys.executable, "scripts/build_www.py"]

SECRET_PATTERNS = [
    r"password\s*=",
    r"api[_-]?key\s*=",
    r"secret\s*=",
    r"BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY",
    r"Authorization:\s*Bearer",
]
SECRET_RE = [re.compile(p, re.IGNORECASE) for p in SECRET_PATTERNS]
ENV_FILE_RE = re.compile(r"(^|/)\.env[^/]*$")

CHECK_NAMES = ["lint", "tests", "build", "report", "scope", "migrations", "secrets"]


def _git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def diff_files(repo, base):
    out = _git(repo, "diff", "--name-only", f"{base}...HEAD")
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def added_lines(repo, base):
    """Pares (archivo, linea) de las lineas anadidas del diff."""
    out = _git(repo, "diff", "-U0", "--no-color", f"{base}...HEAD")
    cur, res = None, []
    for ln in out.splitlines():
        if ln.startswith("+++ "):
            cur = ln[6:] if ln.startswith("+++ b/") else None
        elif ln.startswith("+") and cur:
            res.append((cur, ln[1:]))
    return res


def _run(cmds, repo, timeout=None):
    for cmd in cmds:
        r = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        if r.returncode != 0:
            tail = (r.stdout + r.stderr).strip().splitlines()[-8:]
            return False, f"{' '.join(cmd[:4])} -> exit {r.returncode}: " + " | ".join(tail)
    return True, "ok"


def check_lint(repo, cmds=None):
    return _run(cmds or LINT_CMDS, repo)


def check_tests(repo, cmd=None):
    return _run([cmd or TEST_CMD], repo)


def check_build(repo, cmd=None):
    return _run([cmd or BUILD_CMD], repo)


def check_report(repo, base):
    sha = _git(repo, "rev-parse", "--short", "HEAD").strip()
    in_range = [s[:7] for s in _git(repo, "rev-list", f"{base}..HEAD").split()] or [sha]
    for f in diff_files(repo, base):
        name = f.rsplit("/", 1)[-1]
        if fnmatch.fnmatch(name, "REPORT-*.md") and (Path(repo) / f).is_file():
            text = (Path(repo) / f).read_text(encoding="utf-8", errors="replace")
            if any(s in text for s in in_range):
                return True, f"{f} contiene el SHA"
    return False, f"ningun REPORT-*.md del diff contiene un SHA de {base[:7]}..{sha}"


def check_scope(repo, base, allow):
    patterns = list(allow) + ALWAYS_ALLOWED
    bad = [f for f in diff_files(repo, base)
           if not any(fnmatch.fnmatch(f, p) or (p.startswith("REPORT-") and fnmatch.fnmatch(f.rsplit("/", 1)[-1], p))
                      for p in patterns)]
    return (not bad), ("todos los archivos dentro del alcance" if not bad
                       else "fuera de alcance: " + ", ".join(bad))


def check_migrations(repo, base, allow_migrations):
    migs = [f for f in diff_files(repo, base) if f.startswith("alembic/versions/")]
    bad = [m for m in migs if not any(a and a in m for a in allow_migrations)]
    return (not bad), ("sin migraciones no autorizadas" if not bad
                       else "migracion no autorizada: " + ", ".join(bad))


def check_secrets(repo, base):
    hits = []
    for f in diff_files(repo, base):
        if ENV_FILE_RE.search(f) and not f.endswith(".env.example"):
            hits.append(f"{f}: archivo .env modificado")
    for f, line in added_lines(repo, base):
        for rx in SECRET_RE:
            if rx.search(line):
                hits.append(f"{f}: /{rx.pattern}/ en linea anadida")
                break
    return (not hits), ("sin secretos en el diff" if not hits else "; ".join(hits[:10]))


def run_all(repo, base, allow, allow_migrations=(), skip=()):
    results = []

    def go(name, fn):
        if name in skip:
            results.append((name, "SKIP", "omitido por --skip"))
            return
        try:
            ok, msg = fn()
        except Exception as e:  # un chequeo que revienta cuenta como FAIL
            ok, msg = False, f"error del chequeo: {e}"
        results.append((name, "PASS" if ok else "FAIL", msg))

    go("lint", lambda: check_lint(repo))
    go("tests", lambda: check_tests(repo))
    go("build", lambda: check_build(repo))
    go("report", lambda: check_report(repo, base))
    go("scope", lambda: check_scope(repo, base, allow))
    go("migrations", lambda: check_migrations(repo, base, allow_migrations))
    go("secrets", lambda: check_secrets(repo, base))
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="SHA base de la pila")
    ap.add_argument("--allow", action="append", default=[], help="glob permitido (repetible)")
    ap.add_argument("--allow-migrations", action="append", default=[], help="nombre de migracion autorizada")
    ap.add_argument("--skip", action="append", default=[], choices=CHECK_NAMES,
                    help="solo para verificar historia; queda declarado como SKIP")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    a = ap.parse_args(argv)
    res = run_all(a.repo, a.base, a.allow, a.allow_migrations, a.skip)
    for name, st, msg in res:
        print(f"{st} {name}: {msg}")
    failed = [n for n, st, _ in res if st == "FAIL"]
    print("GUARDRAILS " + ("FAIL (" + ", ".join(failed) + ")" if failed else "PASS"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
