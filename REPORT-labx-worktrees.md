# REPORT — WORKTREES (BUILD 414)

Base: `0107261` (E2E-GATE, BUILD 413). Sin push, sin migraciones, sin cambios de app, sin tocar BD de produccion ni cuentas e2e_*/onb_*/qa_*.

## 1. Los dos scripts

Se ejecutan con `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\<x>.ps1 ...` (la politica de ejecucion de la PC bloquea `.ps1` sin firmar; igual que los `launch-*.ps1`).

**`scripts/new-labx-worktree.ps1 -Pila <slug> -Build <N> -Base <sha>`**
- Crea `C:\Users\rafae\projects\LabX-<slug>` con la rama `pila-<N>-<slug>` desde `<sha>`; imprime `BRANCH=... BASE=...` y la ruta.
- Falla SIN borrar nada si la carpeta, la rama o un worktree registrado ya existen, si la base no resuelve a un commit o si el slug es invalido. Probado: reintento con la misma pila y base `deadbeef` -> exit 1, nada tocado.
- Prepara el arbol: comprueba que `import api` resuelva al worktree (no a otro arbol) y que esten fastapi/sqlalchemy/alembic/pytest/uvicorn.

**`scripts/merge-labx-worktree.ps1 -Pila <slug> -Build <N> -Sha <sha>`**
- Exige main sin cambios en archivos rastreados, rama apuntando EXACTAMENTE a `-Sha` (si alguien commiteo despues de verificar, se niega) y worktree limpio.
- Fast-forward si se puede; si no, `merge --no-ff -m "merge:pila-<N>-<slug>"`. Verifica: ff -> `HEAD == Sha`; merge -> `HEAD^2 == Sha`. Solo entonces borra worktree y rama. Conflicto -> `merge --abort`. **Nunca hace push.**

## 2. Entorno Python: decision y prueba

**Decision: Python del sistema, sin venv por worktree.** En LabX no hay venv (el repo corre con el Python 3.12 del sistema) y el paquete `api` NO esta instalado (`pip -e`), asi que `python -m pytest` / `python scripts/...` importan `api` desde el cwd = el worktree. Un venv por worktree costaria minutos y cientos de MB por pila sin aportar aislamiento extra; el riesgo equivalente al junction de node_modules de InvestX no existe porque no hay build con restricciones de raiz.

Prueba (no supuesto): en `LabX-wt-a` y `LabX-wt-b`, `python -c "import api; print(api.__file__)"` imprimio `...\LabX-wt-a\api\__init__.py` y `...\LabX-wt-b\api\__init__.py`; y la suite completa + `build_www.py` corrio en ambos sin dependencias propias y **sin `.env`** (no se copia: es secreto y los tests/E2E usan BD temporal). Si algun dia se hace `pip install -e .`, el script de creacion lo detecta y aborta.

Cuidados: `data/` rastreado viaja en el checkout (~2140 archivos, ~5 s); `.env`, BD locales y `www/`/`node_modules` NO. Si una pila necesita deps nuevas, instalarlas en el Python del sistema afecta a todos los worktrees a la vez (aceptable: requirements-api.txt es unico).

## 3. Verificacion con 2 worktrees reales

1. Dos worktrees (`wt-a`, `wt-b`) desde `0107261`; un comentario distinto en `scripts/repair_training_load.py` (a) y `scripts/create_review_demo_account.py` (b), un commit en cada uno.
2. `labx_guardrails.py` corrido **a la vez** en ambos (suite pytest completa con cobertura): ambos `GUARDRAILS PASS` (lint, tests, build, scope, migrations, secrets; `report` declarado SKIP porque el cambio trivial no lleva reporte). Sin interferencia observada (BD temporal por corrida, mismos resultados).
3. Merge con SHA equivocado -> rechazado, main intacta. Merge de a (fast-forward, HEAD == sha) y de b (merge real `merge:pila-414-wt-b`, `HEAD^2 == sha`): ambos verificados; worktrees y ramas borrados.
4. Limpieza: main se devolvio con `git reset --hard 0107261` (solo commits temporales propios, tree rastreado limpio); no quedan worktrees `LabX-wt-*`, ni ramas `pila-414-*`, ni archivos temporales.

Limite honesto: el paralelo se probo con 2 suites simultaneas; no se probaron 2 servidores uvicorn a la vez (el E2E gate usa puerto propio — si dos pilas corren el gate a la vez, chocan salvo que el gate elija puerto libre; revisar en la proxima pila de E2E).

## 4. Patron nuevo (y que cambia)

Patron actual: una pila a la vez en `C:\Users\rafae\projects\LabX`, lanzada con `launch-*.ps1`/WMI + `run-*.cmd`; el arbol compartido obliga a la secuencia.

Patron con worktree:
1. **Crear**: `new-labx-worktree.ps1 -Pila <slug> -Build <N> -Base <sha de main>`.
2. **Copiar prompt/run**: copiar `prompt-<...>.txt` y el `run-*.cmd` al worktree (o apuntarlos con ruta absoluta) y ajustar su `cd` a `LabX-<slug>`; los `launch-*.ps1` actuales NO se tocan en esta pila.
3. **Lanzar**: el agente trabaja solo dentro de `LabX-<slug>` (rama `pila-<N>-<slug>`); commits locales.
4. **Verificar**: `python scripts/labx_guardrails.py --base <sha> --allow ...` (y E2E gate) DENTRO del worktree.
5. **Merge**: `merge-labx-worktree.ps1 -Pila <slug> -Build <N> -Sha <sha verificado>` desde el repo principal en main (pilas en paralelo: una tras otra; la segunda sera merge no-ff y conviene re-correr guardrail sobre main si tocaron areas cercanas).
6. **Push**: lo hace Pocoyo por SSH con el ok de Rafael. Los scripts nunca empujan.

Cambia: aislamiento de arbol por pila (2-3 simultaneas), rama por pila, merge verificado por SHA. No cambia: guardrail, E2E gate, convencion de commit, regla de no-push.

Commit de la pila: `93e1fe6` (scripts + este reporte).
