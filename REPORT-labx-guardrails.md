# REPORT labx-guardrails (BUILD 412)

Commit del script: `c38458b` (base de la pila: `02b8ccd`). Solo local, sin push, sin migraciones, BD intacta.
El SHA del propio commit del reporte no puede escribirse dentro de si mismo, por eso el reporte va en un segundo commit y cita `c38458b`.

## Archivos
- `scripts/labx_guardrails.py` (nuevo): CLI.
- `scripts/test_labx_guardrails.py` (nuevo): 22 tests, repos git temporales.
- `REPORT-labx-guardrails.md`.
Nada de la app cambia (BUILD 412 es solo nominal de la pila; `sw.js` no se toca).

## Invocacion
```
python scripts/labx_guardrails.py --base <sha> --allow <glob> [--allow <glob> ...] [--allow-migrations <nombre>]
```
Sale 0 solo si todo pasa; una linea `PASS|FAIL|SKIP <chequeo>: detalle` por chequeo y `GUARDRAILS PASS|FAIL (...)` al final.
`--skip <chequeo>` existe solo para verificar historia y queda impreso como SKIP. REPORT-*.md y los dos scripts siempre estan permitidos. Los globs son fnmatch (un `*` cruza directorios).

## Comandos fijados
- **lint**: `make lint` NO se pudo fijar: no hay `make` en la PC y `flake8 api/ --max-line-length=120 --extend-ignore=E501,W503` da ~7300 avisos de estilo (E221/E251/E231...: alineacion intencional) sobre el HEAD limpio, ajeno a la pila. Se fijo, sin relajar nada, lo que corresponde:
  - `python -m flake8 api/ --exclude=api/tests/,__pycache__,api/migrations/ --select=E9,F63,F7,F821,F822,F823` (identico al job Lint del CI)
  - `python -m bandit -r api/ --skip B101,B601 --severity-level high -q` (el del Makefile; en minuscula porque el bandit local rechaza `HIGH`)
  - `python -m compileall -q api/`
  Los tres salen 0 sobre el HEAD limpio.
- **tests**: `python -m pytest api/tests/ -q --tb=short --cov=api --cov-report=term --cov-fail-under=70`. Corrida real sobre HEAD: **3722 passed, 1 skipped, cobertura 85.28%, exit 0** (30 min 35 s; el baseline 2516 del 31/10 quedo superado). Ojo: tarda ~30 min.
- **build**: `python scripts/build_www.py` (genera `www/` para Capacitor; la web no tiene build step). Exit 0.

## Chequeos y casos de prueba (pytest scripts/test_labx_guardrails.py -> 22 passed)
| Chequeo | PASS | FAIL |
|---|---|---|
| a lint+compilacion | `test_lint_pass` | `test_lint_fail_syntax_error` |
| b tests | `test_tests_pass` | `test_tests_fail` |
| c build | `test_build_pass` | `test_build_fail_missing_script` |
| d reporte con SHA | `test_report_pass` | `test_report_fail_without_sha`, `test_report_fail_no_report_file` |
| e alcance | `test_scope_pass` | `test_scope_fail_file_outside` |
| f migraciones | `test_migrations_pass_when_authorized` | `test_migrations_fail_when_not_authorized` |
| g secretos | `test_secrets_pass_clean_diff`, `test_secrets_ignores_removed_lines` | 5 patrones parametrizados + `test_secrets_fail_env_file` |
| CLI | `test_cli_exit_code_and_skip` (exit 0 / exit 1) | |

Decisiones: el chequeo d acepta el SHA corto de HEAD o de cualquier commit del rango base..HEAD (un reporte no puede contener el SHA de su propio commit). `.env.example` esta exento; lineas eliminadas no se escanean.

## Verificacion contra historia real (clon temporal en %TEMP%, base 70ac954, HEAD 11f38ab = BUILD 407)
- Alcance real (los 9 archivos del diff): lint PASS, build PASS, scope PASS, migrations PASS, secrets PASS -> **GUARDRAILS PASS (exit 0)**.
- Alcance sin `shell.html`: **FAIL scope: fuera de alcance: shell.html (exit 1)**.
- Linea sintetica de tipo contrasena (patron password + igual) anadida en un commit extra: **FAIL secrets: dashboard.html /password\s*=/ (exit 1)**.
- En esas corridas se uso `--skip tests --skip report`: tests porque la suite completa (30 min) se corrio aparte sobre HEAD, y report porque `REPORT-407.md` no contiene ningun SHA (el BUILD 407 es anterior al guardrail). Ambos quedan impresos como SKIP.

## Cableado en futuros run-labx-<pila>.cmd
Antes de escribir DONE (el flujo de lanzamiento no se toco en esta pila):
```
python scripts\labx_guardrails.py --base %BASE_SHA% --allow "<archivo1>" --allow "<archivo2>" >> labx-<pila>.log 2>&1
if errorlevel 1 (echo FAILED guardrails >> labx-<pila>.log & exit /b 1)
echo DONE-<PILA> %SHA% >> labx-<pila>.log
```
`%BASE_SHA%` = `git rev-parse HEAD` capturado al lanzar. Caveats: el chequeo de tests tarda ~30 min; los `api/tests/test_zz_*.py` sin rastrear que hay hoy en el arbol se ejecutan igual que el resto de la suite (corrieron en verde).
