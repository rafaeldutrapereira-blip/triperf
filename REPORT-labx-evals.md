# REPORT — EVALS (BUILD 415)

Base: `01afe47` (WORKTREES, BUILD 414, ya en origin/main; sin secuencia 408-411 corriendo). Codigo en `18ed2f9`. Sin push, sin migraciones, sin cambios de app, sin tocar BD de produccion ni cuentas e2e_*/onb_*/qa_*.

ALLOW: scripts/labx_eval_pile.py, scripts/test_labx_eval_pile.py, REPORT-labx-evals.md

Archivos del diff: `scripts/labx_eval_pile.py`, `scripts/test_labx_eval_pile.py`, `REPORT-labx-evals.md`.

## 1. El evaluador: `scripts/labx_eval_pile.py`

`python scripts/labx_eval_pile.py --base <sha> --head <sha> --report <ruta> [--allow <glob>...] [--allow-migrations <n>...] [--pytest-log <archivo>]`

Salida: una linea `PASS|FAIL <n> <punto>: detalle` por punto y `EVAL: n/6 PASS|FAIL`. Exit 0 solo con 6/6. Solo lee; reutiliza `labx_guardrails.py` (importa `check_migrations`, `check_secrets`, `ALWAYS_ALLOWED`, y lo invoca como proceso para el punto 4).

| # | Punto | Regla |
|---|-------|-------|
| 1 | alcance | Todo archivo de `base...head` calza con `--allow` o con las lineas `ALLOW: a, b` / `--allow <glob>` del reporte (+ `REPORT-*.md` y los archivos del guardrail/evaluador). Sin alcance declarado = FAIL. |
| 2 | reporte | El reporte nombra cada archivo del diff (ruta, nombre o nombre sin `.py`) y cita un SHA de la pila. |
| 3 | tests | El reporte declara un conteo `N passed` y una corrida real de pytest da 0 failed/errors (`--pytest-log` reutiliza la salida de una corrida real ya hecha: la suite tarda ~24 min). |
| 4 | guardrails | `labx_guardrails.py` en verde sobre la pila. |
| 5 | e2e | Si el diff toca `.html/.css/.js`, `api/` (no tests), `alembic/` o `e2e/`, el reporte debe decir que el gate corrio y paso, o por que no aplica; si no lo toca, el punto no aplica y pasa. No corre el gate. |
| 6 | seguridad | Chequeos [f] y [g] del guardrail: migraciones no autorizadas y secretos. |

Pilas viejas (`head != HEAD`): worktree temporal detached en `head` (se borra siempre) para los puntos 1, 2, 4, 5, 6. **Limitacion:** el worktree no tiene el entorno instalado, asi que el punto 3 corre pytest sobre el arbol ACTUAL, no sobre ese commit, y el punto 4 omite `tests` y `build` del guardrail (queda declarado en el detalle: `[AVISO: ...]`, `omitidos por pila vieja`).

Desviacion consciente del enunciado: el punto 2 acepta el SHA del head **o de cualquier commit de la pila** (como el guardrail). Un reporte versionado en el commit head no puede citar el SHA de su propio commit; exigir solo el head hace fallar para siempre a las pilas de un commit. Si se quiere exigir estrictamente el head, el reporte debe ir en un commit posterior al codigo (como esta pila).

Limites honestos: el punto 2 solo comprueba reporte -> diff (los reportes mencionan archivos "no tocados", asi que el sentido inverso daria falsos rojos); el punto 3 toma el ultimo `N passed` del reporte, que en reportes con varias corridas (407) es el de la re-corrida parcial, no el de la suite completa; el punto 5 es lectura de texto, no verificacion.

## 2. Tests: `scripts/test_labx_eval_pile.py`

17 tests en repos git temporales con runners falsos de pytest/guardrails (no tocan el repo real): pila buena = 6/6; por punto, FAIL de alcance (archivo fuera / sin allow; PASS con ALLOW leido del reporte), reporte (archivo sin nombrar / sin SHA), tests (suite roja / sin conteo; PASS con `--pytest-log`), guardrails (FAIL propagado), e2e (UI sin mencion / "no corrio" = FAIL; "no aplica" y diff sin UI = PASS), seguridad (migracion no autorizada / secreto), pila vieja con worktree limpiado, y exit code de `main`. Resultado: `17 passed`.

## 3. Verificacion contra pilas reales

Corrida real de pytest sobre el arbol actual (`01afe47` + 2 archivos nuevos de scripts): **3722 passed, 0 failed** en 24:13 (`C:\Users\rafae\labx-evals-pytest.txt`, excluidos los dos `test_zz_*` sin versionar). Todas las corridas de abajo usaron esa salida via `--pytest-log`.

### BUILD 406 (base `b964893`, head `70ac954`) — **3/6 FAIL**
(con `--allow` = los 5 archivos que el propio reporte dice tocar; **sin `--allow` da 2/6**: el punto 1 FALLA con "sin alcance declarado", porque ni el reporte ni el SPEC dejaron el alcance en forma legible por maquina, y el punto 4 tambien falla por `scope`)
- PASS 1 alcance.
- FAIL 2 reporte: no cita ningun SHA de la pila (`70ac954`). Nombra los 5 archivos.
- PASS 3 tests: reporte 3676 passed; corrida real 3722 passed, 0 failed (aviso: arbol actual).
- FAIL 4 guardrails: `report` — ningun REPORT del diff contiene un SHA de `b964893..70ac954` (tests/build omitidos por pila vieja).
- FAIL 5 e2e: el diff toca `blood_lab_parser.py` (API) y el reporte no menciona el gate E2E.
- PASS 6 seguridad.

### BUILD 407 (base `70ac954`, head `11f38ab`) — **3/6 FAIL**
(`--allow` = los 8 archivos del reporte)
- PASS 1 alcance.
- FAIL 2 reporte: no cita ningun SHA de la pila (`11f38ab`).
- PASS 3 tests: el reporte declara "31 passed" (la re-corrida parcial, ver limites); corrida real 3722 passed, 0 failed.
- FAIL 4 guardrails: `report` — sin SHA en el reporte.
- FAIL 5 e2e: el diff toca 5 archivos UI (`dashboard.html`, `estado.html`, `shell.html`, `theme-vars.css`, `sw.js`) y el reporte no menciona el gate E2E (usa capturas y `npm run test:js`; el gate E2E no existia aun: nacio en BUILD 413).
- PASS 6 seguridad.

Lectura: los dos fallos coinciden y son reglas reales ya conocidas, no del evaluador: (a) los reportes 406/407 no citan SHA (el guardrail de BUILD 412+ ya lo exige; hoy esas pilas no lo pasarian); (b) ninguna de las dos corrio el E2E gate porque no existia. Que 406 y 407 den lo mismo es esperable: son de la misma epoca y proceso.

### Caso sintetico malo — **3/6 FAIL, hallazgo 1 confirmado**
Commit temporal (rama `tmp-eval-malo` en un worktree aparte, ya borrados; main intacta) sobre `01afe47` que toca `scripts/repair_training_load.py` (encargado, `--allow`) y **`sw.js` (fuera de encargo)**:
- **FAIL 1 alcance: fuera de alcance: sw.js**
- FAIL 2 reporte: sin SHA. PASS 3 tests. FAIL 4 guardrails: `report` y `scope: sw.js` (el guardrail coincide con el punto 1). PASS 5 (el reporte sintetico dice "E2E: no aplica"). PASS 6.
`EVAL: 3/6 FAIL`, exit 1.

## 4. Retroalimentacion a las reglas (proceso, no automatizado)

Esta pila **solo documenta** el proceso; no escribe en `AGENTS.md` (workspace de Pocoyo) ni en `CLAUDE.md` (repo).

1. **Cuando:** tras cada pila que cierre con menos de 6/6 en el evaluador (corrido por Pocoyo al recibir DONE: `python scripts/labx_eval_pile.py --base <base> --head <sha DONE> --report <REPORT> --pytest-log <salida real>`). Con 6/6 no se anota nada.
2. **Quien anota:** Pocoyo, nunca la pila evaluada ni el evaluador.
3. **Que se anota** (una entrada por punto en FAIL, solo si el fallo es una regla que faltaba o no se cumplio, no un bug puntual):
   - Punto 1 -> falta/ambiguo el alcance en el encargo: regla "el reporte lleva una linea `ALLOW: ...`" (ya reconocida por el evaluador). O la pila toco algo que no debia: regla de escalacion en `AGENTS.md`.
   - Punto 2 -> regla de reporte: nombrar cada archivo y citar SHA (reporte en commit posterior al codigo).
   - Punto 3 -> regla de verificacion: conteo real en el reporte con la corrida completa, no la parcial.
   - Punto 4 -> la regla que dijo el guardrail (ya impresa en su salida).
   - Punto 5 -> regla "UI/API tocada => correr `labx_e2e_gate.py` o escribir por que no aplica".
   - Punto 6 -> regla de migraciones/secretos (ya escrita; si falla, escalar).
4. **Donde:** reglas operativas de Pocoyo -> `AGENTS.md`; hechos del repo y gotchas -> `CLAUDE.md` (via una pila que lo edite, en el mismo commit que el cambio, segun su regla de oro). Cada entrada cita pila, punto y hallazgo.
5. **Poda:** si una regla anotada lleva 5 pilas seguidas en 6/6 sin dispararse y el evaluador ya la comprueba, se marca "cubierta por evaluador" o se elimina de `AGENTS.md`; si dos reglas se contradicen, el evaluador gana al texto (es lo unico que se ejecuta).
6. **Cierre del ciclo:** corregida la regla, se vuelve a evaluar la pila (o la siguiente del mismo tipo); si sigue < 6/6, la regla estaba mal escrita.

## 5. Verificacion general

- Suite pytest completa: 3722 passed, 0 failed (arriba). `scripts/test_labx_eval_pile.py`: 17 passed.
- `python scripts/build_www.py`: exit 0.
- `make lint` no existe en esta PC (sin make): se uso el guardrail, que fija el equivalente (flake8 errores reales + bandit HIGH + compileall) — ver resultado en el log del marcador.
- Guardrail de la pila: resultado en `labx-evals.log`.
