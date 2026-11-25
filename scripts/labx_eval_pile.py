"""Evaluador de pilas de LabX (mecanismo 2: evals). Puntua una pila sobre 6.

El guardrail vigila la pila ANTES de reportar DONE; este evaluador la juzga DESPUES,
contra su reporte, y sirve para verificar pilas viejas y detectar reglas que no se
cumplen. Solo lee: nunca escribe en el repo ni toca la BD.

Uso:
    python scripts/labx_eval_pile.py --base <sha> --head <sha> --report <ruta>
        [--allow <glob> ...] [--allow-migrations <nombre> ...] [--pytest-log <archivo>]

Puntos (una linea PASS/FAIL + detalle cada uno), salida final "EVAL: n/6 PASS|FAIL":
  1 alcance      diff base...head solo toca archivos encargados (--allow o lineas
                 "ALLOW: glob, glob" / "--allow <glob>" del reporte; REPORT-*.md y los
                 archivos del guardrail/evaluador siempre permitidos).
  2 reporte      el reporte nombra cada archivo del diff (ruta, nombre o nombre sin .py)
                 y cita el SHA del head o de un commit de la pila (prefijo >= 7 hex;
                 el commit que contiene al reporte no puede citarse a si mismo).
  3 tests        el reporte declara un conteo "N passed" y una corrida real de pytest
                 queda en verde (0 failed/errors). --pytest-log reutiliza la salida de una
                 corrida real ya hecha en vez de lanzar otra (la suite tarda ~25 min).
  4 guardrails   labx_guardrails.py en verde para la pila.
  5 e2e          el diff toca algo de cara al usuario/servidor => el reporte debe decir que
                 el gate E2E corrio y paso, o por que "no aplica". Si el diff no lo toca,
                 el punto no aplica y pasa. Solo lee el reporte: NO corre el gate.
  6 seguridad    sin migraciones no autorizadas ni secretos (chequeos de guardrails).

Pilas viejas: si head no es el HEAD del repo, se crea un worktree temporal detached en head
(se borra al terminar) para los puntos 1, 4 y 6. El worktree no tiene el entorno instalado,
asi que el punto 3 corre pytest sobre el arbol ACTUAL, no sobre ese commit, y el punto 4
omite tests y build (los declara). Exit 0 solo con 6/6.
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labx_guardrails as g  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ALWAYS_ALLOWED = g.ALWAYS_ALLOWED + ["scripts/labx_eval_pile.py", "scripts/test_labx_eval_pile.py"]

# Rutas cuyo cambio afecta al usuario o al servidor: el gate E2E aplicaba.
E2E_RELEVANT = [r"\.html$", r"\.css$", r"(^|/)[^/]+\.js$", r"^api/(?!tests/)", r"^alembic/", r"^e2e/"]
E2E_RELEVANT_RE = [re.compile(p) for p in E2E_RELEVANT]
E2E_NOT_APPLY_RE = re.compile(r"(no\s+aplic|n/a|not\s+applicable|no\s+corresponde)", re.I)
E2E_PASS_RE = re.compile(r"(\bpass(ed)?\b|\bverde\b|exit\s*0|\bok\b|0\s+failed|\bpas[oó]\b)", re.I)
E2E_FAIL_RE = re.compile(r"(\bfail(ed)?\b|\bfall[oó]\b|\brojo\b|no\s+corri[oó]|no\s+se\s+corri[oó]|no\s+corr[ií])", re.I)

POINTS = ["alcance", "reporte", "tests", "guardrails", "e2e", "seguridad"]


def read_report(repo, report, head):
    p = Path(report)
    if p.is_file():
        return p.read_text(encoding="utf-8", errors="replace")
    try:
        return g._git(repo, "show", f"{head}:{report.replace(chr(92), '/')}")
    except RuntimeError:
        return None


def report_allow(text):
    out = []
    for ln in text.splitlines():
        m = re.match(r"^\s*[-*]?\s*ALLOW\s*:\s*(.+)$", ln)
        if m:
            out += [x.strip(" `") for x in m.group(1).split(",") if x.strip(" `")]
    out += [x for x in re.findall(r"--allow[ =]+`?([^\s`,;]+)", text)]
    return out


def diff_files_range(repo, base, head):
    out = g._git(repo, "diff", "--name-only", f"{base}...{head}")
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _mentioned(f, text):
    name = f.rsplit("/", 1)[-1]
    stem = name[:-3] if name.endswith(".py") else name
    return f in text or name in text or stem in text


def check_alcance(repo, base, head, allow):
    if not allow:
        return False, "sin alcance declarado (ni --allow ni ALLOW en el reporte)"
    pats = list(allow) + ALWAYS_ALLOWED
    bad = [f for f in diff_files_range(repo, base, head)
           if not any(fnmatch.fnmatch(f, p) or (p.startswith("REPORT-") and fnmatch.fnmatch(f.rsplit("/", 1)[-1], p))
                      for p in pats)]
    return (not bad), ("todos los archivos dentro del alcance" if not bad
                       else "fuera de alcance: " + ", ".join(bad))


def check_reporte(repo, base, head, text):
    if text is None:
        return False, "el reporte no existe"
    files = [f for f in diff_files_range(repo, base, head)
             if not fnmatch.fnmatch(f.rsplit("/", 1)[-1], "REPORT-*.md")]
    missing = [f for f in files if not _mentioned(f, text)]
    full = g._git(repo, "rev-parse", head).strip()
    # Un reporte versionado en el commit head no puede citar el SHA de su propio commit:
    # se acepta el head o cualquier commit de base..head (igual que el guardrail).
    toks = re.findall(r"\b[0-9a-f]{7,40}\b", text)
    in_range = g._git(repo, "rev-list", f"{base}..{full}").split()
    cites = any(c.startswith(t) for t in toks for c in in_range)
    problems = []
    if missing:
        problems.append("el reporte no nombra: " + ", ".join(missing))
    if not cites:
        problems.append(f"no cita el SHA del head ni de ningun commit de la pila ({full[:7]})")
    if problems:
        return False, "; ".join(problems)
    return True, f"nombra los {len(files)} archivos del diff y cita {full[:7]}"


def _counts(out):
    p = re.findall(r"(\d+)\s+passed", out)
    f = re.findall(r"(\d+)\s+failed", out)
    e = re.findall(r"(\d+)\s+errors?\b", out)
    return (int(p[-1]) if p else None, int(f[-1]) if f else 0, int(e[-1]) if e else 0)


def run_pytest(repo):
    r = subprocess.run([sys.executable, "-m", "pytest", "api/tests/", "-q", "-p", "no:cacheprovider"],
                       cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def check_tests(text, repo, pytest_log=None, runner=run_pytest, historical=False):
    claimed = _counts(text or "")[0]
    if claimed is None:
        return False, "el reporte no declara un conteo 'N passed'"
    if pytest_log:
        out = Path(pytest_log).read_text(encoding="utf-8", errors="replace")
        rc = None
        src = f"salida de corrida real ({Path(pytest_log).name})"
    else:
        rc, out = runner(repo)
        src = "corrida real de pytest"
    passed, failed, errors = _counts(out)
    if passed is None or failed or errors or (rc not in (None, 0)):
        return False, f"{src}: passed={passed} failed={failed} errors={errors} exit={rc}"
    note = " [AVISO: pytest sobre el arbol ACTUAL, no sobre el commit de la pila]" if historical else ""
    return True, f"reporte declara {claimed} passed; {src}: {passed} passed, 0 failed{note}"


def run_guardrails(repo, base, allow, allow_migrations, skip):
    cmd = [sys.executable, str(Path(__file__).resolve().parent / "labx_guardrails.py"),
           "--base", base, "--repo", str(repo)]
    for a in allow:
        cmd += ["--allow", a]
    for a in allow_migrations:
        cmd += ["--allow-migrations", a]
    for s in skip:
        cmd += ["--skip", s]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def check_guardrails(repo, base, allow, allow_migrations, historical=False, runner=run_guardrails):
    skip = ["tests", "build"] if historical else []
    rc, out = runner(repo, base, allow, allow_migrations, skip)
    lines = [ln for ln in out.splitlines() if ln.startswith(("PASS", "FAIL", "SKIP"))]
    bad = [ln for ln in lines if ln.startswith("FAIL")]
    sk = [ln.split(":")[0] for ln in lines if ln.startswith("SKIP")]
    note = f" (omitidos por pila vieja: {', '.join(sk)})" if sk else ""
    if rc == 0:
        return True, "GUARDRAILS PASS" + note
    return False, ("; ".join(b[:160] for b in bad) or out.strip()[-200:]) + note


def check_e2e(repo, base, head, text):
    rel = [f for f in diff_files_range(repo, base, head) if any(rx.search(f) for rx in E2E_RELEVANT_RE)]
    if not rel:
        return True, "no aplica: el diff no toca UI, API ni migraciones"
    lines = [ln for ln in (text or "").splitlines() if re.search(r"e2e|playwright", ln, re.I)]
    if not lines:
        return False, f"el diff toca {len(rel)} archivo(s) de UI/API (p. ej. {rel[0]}) y el reporte no menciona el gate E2E"
    for ln in lines:
        if E2E_NOT_APPLY_RE.search(ln):
            return True, "el reporte explica que no aplicaba: " + ln.strip()[:120]
    for ln in lines:
        if E2E_PASS_RE.search(ln) and not E2E_FAIL_RE.search(ln):
            return True, "el reporte declara el E2E en verde: " + ln.strip()[:120]
    return False, "el reporte menciona E2E pero no dice que paso ni por que no aplicaba: " + lines[0].strip()[:120]


def check_seguridad(repo, base, allow_migrations):
    ok_m, msg_m = g.check_migrations(repo, base, allow_migrations)
    ok_s, msg_s = g.check_secrets(repo, base)
    return (ok_m and ok_s), f"migraciones: {msg_m}; secretos: {msg_s}"


def evaluate(repo, base, head, report, allow=(), allow_migrations=(), pytest_log=None,
             tests_runner=run_pytest, guardrails_runner=run_guardrails):
    """Devuelve la lista de (punto, 'PASS'|'FAIL', detalle). Usa un worktree si head != HEAD."""
    repo = Path(repo)
    head_full = g._git(repo, "rev-parse", head).strip()
    historical = head_full != g._git(repo, "rev-parse", "HEAD").strip()
    wt = None
    work = repo
    try:
        if historical:
            wt = Path(tempfile.mkdtemp(prefix="labx-eval-"))
            g._git(repo, "worktree", "add", "--detach", str(wt), head_full)
            work = wt
        text = read_report(repo, report, head_full)
        allow_all = list(allow) + report_allow(text or "")
        res = []

        def go(name, fn):
            try:
                ok, msg = fn()
            except Exception as e:  # un punto que revienta cuenta como FAIL
                ok, msg = False, f"error del punto: {e}"
            res.append((name, "PASS" if ok else "FAIL", msg))

        go("alcance", lambda: check_alcance(work, base, head_full, allow_all))
        go("reporte", lambda: check_reporte(work, base, head_full, text))
        go("tests", lambda: check_tests(text, repo, pytest_log, tests_runner, historical))
        go("guardrails", lambda: check_guardrails(
            work, base, allow_all, list(allow_migrations), historical, guardrails_runner))
        go("e2e", lambda: check_e2e(work, base, head_full, text))
        go("seguridad", lambda: check_seguridad(work, base, list(allow_migrations)))
        return res
    finally:
        if wt is not None:
            subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)],
                           capture_output=True)
            shutil.rmtree(wt, ignore_errors=True)
            subprocess.run(["git", "-C", str(repo), "worktree", "prune"], capture_output=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--allow", action="append", default=[])
    ap.add_argument("--allow-migrations", action="append", default=[])
    ap.add_argument("--pytest-log", default=None, help="salida de una corrida real de pytest ya hecha")
    ap.add_argument("--repo", default=str(ROOT))
    a = ap.parse_args(argv)
    res = evaluate(a.repo, a.base, a.head, a.report, a.allow, a.allow_migrations, a.pytest_log)
    for i, (name, st, msg) in enumerate(res, 1):
        print(f"{st} {i} {name}: {msg}")
    n = sum(1 for _, st, _ in res if st == "PASS")
    ok = n == len(POINTS)
    print(f"EVAL: {n}/6 {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
