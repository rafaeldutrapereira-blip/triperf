# REPORT-404 — UNIFICAR-CHECKIN (BUILD 404)

## Causa
El dashboard (M2) tenia su propia encuesta de 4 campos (POST /athlete/health/checkin -> GarminHealthDaily) que no alimenta ningun score, ademas del check-in de Estado (S28: /recovery/wellness + /mental/checkin) que si alimenta Recuperacion, Mental y readiness. El atleta contestaba dos veces lo mismo.

## Cambio
- `dashboard.html`: se quita `#lx-checkin` (markup, `_ckRender`, `saveCheckin`, `loadCheckin` viejo). La tarjeta "Como te sientes" conserva posicion, carcasa y titulo; ahora muestra `#lx-checkin-status`: "Check-in de hoy: hecho/pendiente", resumen (Energia/Animo/Piernas n/5) y enlace a `estado.html#est-reg` ("Editar" / "Completar check-in"). Lee `GET /recovery/wellness/{fecha local}` y `GET /mental/dashboard?date_iso=` (los de estado.html); no escribe. "Hecho" = wellness registrado O check-in mental del dia; un fallo de red cuenta como pendiente. Fila `#kc-mental` intacta. Solo variables CSS del tema.
- `i18n.js`: se retiran `ckin_*` (solo se usaban en dashboard) y se agrega `dash_ck_cta` ES/PT/EN; se reutilizan `est_checkin_*` y `rcw_*_short`. `i18n.js?v` 402 -> 404 en todas las paginas.
- `sw.js`: BUILD_VERSION '404' + changelog. Espejos moviles regenerados (`build_www.py` + `npx cap sync`).
- Sin cambios en backend: endpoint POST /athlete/health/checkin y columnas de GarminHealthDaily intactos, sin migraciones.
- Tests: nuevo `tests/js/checkin_404.test.js` (en `test:js`); actualizados `api/tests/test_m2_wellness_checkin.py` y `test_dashboard_ejecutivo_344.py` (afirmaban `#lx-checkin`/`ckin_*`) y los pines de BUILD/i18n en tests existentes (los JS de 391-400 y test_recuperacion_394, test_tema_migracion_396, test_bloodlabs_ejecutiva).

## Verificacion
- `npm run test:js`: 322 pasan, 0 fallan (8 nuevos).
- `pytest api/tests` (sin los dos `test_zz_*` sin rastrear): primera corrida 3663 passed, 2 failed (`test_i18n.py::test_mobile_mirrors_match_root_i18n` y `..._root_sw`) porque los espejos iOS/Android no estaban sincronizados; tras `npx cap sync` `test_i18n.py` da 10 passed. No se re-corrio la suite completa tras el sync (27 min); fallos preexistentes: ninguno detectado. Log: `C:\Users\rafae\labx-overnight\checkin404_pytest.log` (`checkin404.log` estaba bloqueado por el run script).
- Capturas en `data/shots_checkin404/`: `como_te_sientes_{pendiente,hecho}_{dark,light}.png` (API mockeada; la fila Fatiga Mental sale oculta porque el mock no trae datos de mental). Script: `C:\Users\rafae\labx-overnight\_shots_checkin404.py`.

## Notas
- Los datos del check-in viejo ya guardados quedan en GarminHealthDaily sin leerse.
- athlete-app.html tiene su propio `saveCheckin` (hoja de Estado), no afectado.
