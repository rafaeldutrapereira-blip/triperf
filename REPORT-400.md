# REPORT-400 — GEAR (BUILD 400)

Base: d0a3ebf (BUILD 398). Árbol rastreado limpio al inicio.

## Dónde vive Gear
- Página: `gear.html` (ruta `gear`, `KL.guard('gear')`). Backend sin cambios: `api/routes/gear_routes.py`, `api/services/gear_service.py`.
- Datos: `GET /gear/shoes`, `/gear/bikes` (tarjetas) y `GET /gear/summary` (alertas, `life_pct`, km acumulados/meta).

## Diagnóstico de capas (antes)
- Capa 1 (respuesta en palabras): YA EXISTÍA — banner «¿Qué necesita atención?» (`#alert-banner`, `#alert-text`).
- Capa 2 (porqué): YA EXISTÍA — `#gear-attn-list` (km restantes o % de vida útil por equipo, ordenado por urgencia, `gearAttentionItems`).
- Capa 3 (técnico plegado): FALTABA — pestañas, tarjetas de zapatillas/bicicletas, barras de vida útil, componentes y acciones estaban siempre abiertos.

## Aplicado
- Pestañas Zapatillas/Bicicletas y sus paneles, envueltos en `<details class="gear-fold" id="gear-l3-detail">` plegado por defecto, con resumen i18n `gear_l3_detail`. IDs, handlers y modales intactos.
- `gearOpenDetail()`: el detalle se abre solo si no hay nada que avisar (p. ej. sin equipo, para poder agregar el primero) o si falla `/gear/summary`.
- CSS con variables de tema (`--border`), sin colores fijos oscuros.
- Sin cifras nuevas, sin cambios de fuente ni de backend.

## Mantenido
Todo el contenido, alertas, barras, componentes, acciones y modales.

## Archivos
`gear.html`, `i18n.js` (1 clave ES/PT/EN: `gear_l3_detail`), `sw.js` (BUILD 400 + changelog), sello `i18n.js?v=398→400` en páginas y tests que lo fijan, `package.json` (test agregado a `test:js`), `tests/js/gear_400.test.js`.

## Verificación
- `tests/js/gear_400.test.js`: en la base sin el cambio 1 pasa / 4 fallan; con el cambio pasa 5/5.
- `npm run test:js`: 314 tests, 314 pass, 0 fail (309 + 5 nuevos).
- Espejos móviles regenerados con `build_www.py` + `cap sync` (gitignorados, fuera del commit).
- pytest `api/tests`: ver abajo.
- pytest `api/tests`: 3659 passed, 1 skipped, 0 failed, 0 errors (28 min). Los espejos móviles pasan. test_calendario_vivo_375 no falló esta vez.
- Log: `C:\Users\rafae\labx-overnight\gear400-pytest.log` (el `tee` a `gear400.log` falló con "Device or resource busy").

## Commit
Local en main, sin push, sin deploy, sin migraciones: `feat(gear): capa ejecutiva en Gear (GEAR, BUILD 400)`.
