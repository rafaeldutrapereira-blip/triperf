# REPORT-390 — ALERT-BOTON (BUILD 390)

## Causa
En `coach.html` el panel `#alert-panel` nace con `display:none`, y el unico boton con
`onclick="toggleAlertPanel()"` estaba dentro de su cabecera (boton de cierre): inalcanzable.
Ademas `#alert-badge` no existia en el HTML (el JS, con guarda `if (badge)`, nunca mostraba el contador).

## Cambios
- `coach.html`: boton `#alert-btn` en `.coach-header` (fuera del panel, siempre visible, `onclick="toggleAlertPanel()"`),
  con el contador `#alert-badge` dentro (oculto hasta que el JS lo actualiza). Estilo solo con `var(--...)`.
  Sello `i18n.js?v=390`.
- `i18n.js`: clave nueva `coach_alert_btn` en ES/PT/EN ("🔔 Alertas" / "🔔 Alertas" / "🔔 Alerts").
- `sw.js`: `BUILD_VERSION = '390'`, linea "Anterior 389..." con ALERT-BOTON; precache `/i18n.js?v=390`.
- `tests/js/coach_tablero.test.js`: test nuevo (boton fuera del panel que llama a toggleAlertPanel, `#alert-badge` en el markup, i18n, sin colores fijos, clave en 3 idiomas).
- Sello `i18n.js?v=389` -> `390` en las demas paginas (convencion de builds anteriores) y en
  `api/tests/test_bloodlabs_ejecutiva.py` (assert del sello, que fijaba 389).
- Backend y copias `www/`, `android/`, `ios/` sin tocar.

## Desviaciones / notas
- "Topbar": `.sb-topbar` es un header vacio que llena nav.js (movil); el boton se puso en `.coach-header`, visible en todas las pestanas (incluida Tablero).
- Las pestanas de coach no usan `data-tab` en el boton, asi que `switchTab` no lo afecta.

## Verificacion
- `node --test tests/js/coach_tablero.test.js`: 12/12 pasan.
- `pytest api/tests`: **3646 passed, 1 skipped, 2 failed** (27:53).
  Fallos: `test_i18n.py::test_mobile_mirrors_match_root_i18n` y `::test_mobile_mirrors_match_root_sw`.
  Ambos comparan `i18n.js`/`sw.js` de la raiz con las copias gitignoradas de android/ios/www, que estan
  desactualizadas por este cambio y se regeneran con `python scripts/build_www.py && npx cap sync` (fuera del alcance). No se corrio ese build, asi que NO estan en verde.
- Logs: `C:\Users\rafae\labx-overnight\alert390_pytest.log` (el `tee` a `alert390.log` fallo con "Device or resource busy").

## Commit
Solo local en main, sin push ni deploy. Hash: ver `git log -1`.
