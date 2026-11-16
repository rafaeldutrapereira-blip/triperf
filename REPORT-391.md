# REPORT-391 — BLOODLABS-SIMPLE (BUILD 391)

## Causa
En el Resumen de `blood_labs.html` la primera pantalla mezclaba la frase en llano, las alertas,
el TRS, las variaciones, el "Impacto en Entrenamiento" (`clinical-summary`) y el bloque
"Tus marcadores por sistema" (`bl-systems`). Solo KPIs, radar, IA y tabla estaban plegados
(`<details id="bl-ver-todo">`, "Ver todo").

## Cambio
- Un unico `<details class="bl-all" id="bl-ver-todo">` cerrado, con `<summary data-i18n="bl_see_detail">Ver detalle</summary>`.
  Dentro: impacto clinico, sistemas, KPIs, radar, interpretacion IA y tabla completa.
  Se conservo el id `bl-ver-todo`, asi el redibujo del radar al abrir (evento `toggle`) sigue funcionando.
- Primera pantalla: frase en llano (+ chips), alertas, lectura del TRS y variaciones entre examenes.
- Intactos y visibles: selectores `sel-exam` / `sel-comp`, bloque de variaciones, pestanas Tendencias y Garmin (y Registrar).
- i18n: clave nueva `bl_see_detail` (ES "Ver detalle", PT "Ver detalhe", EN "See details"). Sin texto fijo propio ni colores fijos (el estilo reutiliza `.bl-all > summary`, sin colores).
- `bl_see_all` queda en i18n.js (sin uso en la pagina; no se borro por no tocar mas de lo pedido).
- BUILD_VERSION '391' + linea de changelog en `sw.js`; sello `i18n.js?v=390` -> `391` en todas las paginas HTML raiz que lo llevaban y en el precache de `sw.js` (los historiales de changelog viejos no se tocaron).

## Archivos cambiados
blood_labs.html, i18n.js, sw.js, 30 paginas HTML con el sello (adaptive, ai_coach, analytics, athlete-app, athlete_profile, coach, community, dashboard, detalle, estado, gear, huella, indoor_workout, landing, login, nutrition, onboarding, race_day, recovery, registro, shell, training_detail, training_plan, 404, etc.),
package.json (suma el test nuevo a `test:js`), `tests/js/bloodlabs_simple_391.test.js` (nuevo),
`api/tests/test_bloodlabs_ejecutiva.py` (sello 391), `api/tests/test_w14_nicho.py` y
`api/tests/test_labs_capas_352.py` (ajustados: impacto clinico y sistemas ahora van DENTRO del pliegue).
No se toco backend, carga/lectura de examenes, datos, ni www/ android/ ios/.

## Verificacion
- `npm run test:js`: 275 pass / 0 fail (corrida con el test nuevo, 7 tests propios). Nota: se sumo el test nuevo a package.json despues; el test nuevo corrido solo: 7/7.
- `pytest api/tests` completo (excluyendo 2 archivos scratch sin versionar `test_zz_perf_measure.py`, `test_zz_repro.py`): 3645 passed, 3 failed.
  - `test_labs_capas_352::test_orden_de_capas`: lo causaba este cambio (assert del orden anterior); corregido. Re-corrida de test_labs_capas_352, test_w14_nicho y test_bloodlabs_ejecutiva: 42 passed.
  - `test_i18n::test_mobile_mirrors_match_root_i18n` y `..._root_sw`: fallan por las copias gitignoradas de `www/`, `android/` e `ios/`, que ya estaban desactualizadas respecto de HEAD (verificado con cmp contra `git show HEAD:i18n.js`) antes de mi cambio. Se regeneran con `scripts/build_www.py` + `npx cap sync`; en CI se omiten. NO se tocaron por instruccion. Quedan fallando en este equipo.
- Sin verificacion visual en navegador (no se levanto la app).

## Observaciones
- La rama local `main` estaba 14 commits atras de origin/main; se avanzo con `--ff-only` a f6b0a7d antes de trabajar. El checkout inicial estaba en `legal-closeout-g13-b4` (mismo commit).
- Arbol con archivos sin versionar previos (scripts `_*.py`, etc.): no incluidos en el commit.
- El log pedido `C:\Users\rafae\labx-overnight\blood391.log` estaba bloqueado ("Device or resource busy"); el resumen de pytest se guardo en `blood391-result.txt` en esa misma carpeta.

## Commit
Local en main, sin push/deploy/migraciones: "feat(blood-labs): vista ejecutiva simple con detalle plegado (BLOODLABS-SIMPLE, BUILD 391)".
