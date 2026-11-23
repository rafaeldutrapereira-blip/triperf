# REPORT-407 — ASISTENTE-CLARO (BUILD 407)

Solo local: commit en main, sin push, sin deploy, sin migraciones.

## Causa raíz
1. **Panel del Asistente IA** (`nav.js`, `#lx-ai-panel`): ya usa `var(--lxb-08121e,#08121E)`, `--lxt-*`, `--lxd-*` (patrón de la pila 396). Esos pares claros viven en `theme-light.css`, pero **`dashboard.html` y `shell.html` solo enlazan `theme-vars.css`** (las demás páginas con `nav.js` sí enlazan `theme-light.css`). En esas dos el panel caía al fallback oscuro. En Mi Plan, Estado, etc. ya se veía claro (verificado antes del cambio).
2. **Estado → Mental**: `.men-scope` fija su propia paleta oscura (`--card:#08121e`, `--card2`, `--sub`, `--acc`…) en un `:root` local, por lo que las tarjetas Mental Score y Tendencia 7 días (fondo del gráfico incluido) seguían oscuras.

## Cambios
- `theme-vars.css`: bloque `[data-theme='light'] #lx-ai-panel { --lxb-08121e, --lxb-06101a, --lxd-rgba_255_255_255_p04, --lxt-4a7a96, --lxt-rgba_232_244_248_p88, --lxt-e8f4f8, --lxt-fca5a5 }` con los **mismos valores** de `theme-light.css`, acotado al panel (no cambia otros usos de esas variables en el dashboard, p. ej. el modal de la línea ~7828).
- `estado.html`: `html[data-theme='light'] .men-scope { --card:#fff; --card2:#f0f2f5; --sub:#5b6b7a; --acc:#e8490a; --acc2:#8b3fd1; --yellow:#b7791f; --blue:#0b7fb3; --teal:#0b8aa3 }` dentro del bloque `lx-theme-light` existente.
- Cache-bust `theme-vars.css?v=373 → 407` en `dashboard.html`, `shell.html`, `estado.html`.
- `sw.js`: `BUILD_VERSION = '407'` + línea de changelog.
- `api/tests/test_asistente_claro_407.py` (4 tests).
- Espejos móviles regenerados con `build_www.py` + `node node_modules/@capacitor/cli/bin/capacitor sync`.
- No se tocó: comportamiento del panel, selector de tema, otras páginas, Garmin/intervals.

## Revisión de TODAS las pestañas de estado.html (claro)
Se recorrieron las 13 pestañas (Físico: Resumen, HRV, Sueño, Bienestar, Timeline, Correlaciones, Protocolos, Coach; Mental: Score, Protocolos, Respiración, Correlaciones, Pre-Carrera) con y sin datos sembrados en Mental. Las únicas tarjetas oscuras eran las dos de Mental (ambas comparten `.men-scope`, quedaron resueltas con el mismo bloque; las demás pestañas Mental también usaban `--card` y quedaron claras). **No apareció otra tarjeta oscura en otra pestaña.** Limitación: las pestañas se revisaron con respuestas de API vacías (mock), salvo el sembrado del Mental Score y las barras de tendencia; contenido que solo se pinta con datos reales de Físico no pudo verse.

## Capturas (`data/shots_asistente407/`, copia en `C:\Users\rafae\labx-overnight\shots_asistente407\`)
- `01_panel_dashboard_claro.png`, `02_panel_miplan_claro.png` — panel abierto en claro.
- `03_estado_mental_claro.png` — pestaña Mental en claro (score 76 y Tendencia 7 días).
- `04_panel_dashboard_oscuro.png`, `05_estado_mental_oscuro.png` — oscuro.
- `*_antes` / `*_despues` y `_tabs/` (todas las pestañas, claro y oscuro).

## Modo oscuro: sin cambios (confirmado)
Se capturaron antes (estado original vía `git stash`) y después: panel en Dashboard y Mi Plan, Estado en vista por defecto y las 13 pestañas. Comparación píxel a píxel (PIL `ImageChops.difference`): **16 capturas, 0 diferencias**.

## Tests
- Pytest: ver resultado en el resumen final del log (suite completa).
- Tests JS: el panel es una IIFE de `nav.js` que inyecta DOM/CSS sin funciones puras exportadas; el cambio es solo CSS (variables). No hay lógica nueva testeable en JS; se cubre con `test_asistente_claro_407.py` (estático) y con las capturas. `npm run test:js` se ejecutó igualmente (ver resultado abajo).
- Nota de proceso: el primer intento dejó el panel oscuro porque un comentario CSS contenía `*/` y cerraba el comentario antes de tiempo; el test lo cubre (`/*` y `*/` balanceados).

## Resultados de tests (finales)
- **Pytest completo** (`api/tests`, salida en `labx-overnight/asistente407_pytest.txt`): 3678 passed, 1 skipped, 2 failed en 27:47. Las 2 fallas eran aserciones de la versión de BUILD (`test_recuperacion_394::test_build_394_y_sello`, `test_tema_migracion_396::test_sellos_de_version`: esperaban `'406'`); se actualizaron a `'407'`, igual que hizo la pila 405 con `'404'→'405'`. Re-corridas: 31 passed (esas dos + los nuevos 4 + `test_menubar2_fuentes` + `test_w14_nicho`). Ningún otro fallo.
- **`npm run test:js`**: 313 pass / **9 fail, PREEXISTENTES** (idénticos con y sin mis cambios, verificado con `git stash`): son tests en `tests/js/*` (checkin_404, tema_396, raceday_397, perfil_398, gear_400, bloodlabs_391/392/393, garmin_return_395) que exigen literalmente `BUILD_VERSION = '404'`/`i18n.js?v=404` y ya fallaban con BUILD 406. No se tocaron ni se ocultan; conviene actualizarlos en una pila aparte.
