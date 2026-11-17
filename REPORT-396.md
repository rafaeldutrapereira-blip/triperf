# REPORT-396 — MIGRACION-TEMA (BUILD 396)

Base: `a5e4ca2` (BUILD 395). Arbol rastreado limpio al empezar. Commit solo local, sin push ni deploy, sin migraciones, sin backend.

## 1. Diagnostico del tema (hecho en el codigo)

**Mecanismo.** `localStorage.labx_theme` (`dark|light`, oscuro por defecto). Un script inline en el `<head>` de cada pagina pone `<html data-theme>` antes del primer pintado. `LXTheme` (nav.js) expone `get/set/apply`, actualiza los botones del menu, los iframes de la shell y otras pestanas (evento `storage`).

**Variables.**
- `theme-vars.css` (30 paginas): fuente de verdad, define `:root`/`[data-theme=dark]` y `[data-theme=light]` con `--bg --card --surface --surface2 --border --border2 --text --text2 --muted --dim --faint --accent --ok --warn --bad --orange --gold --cyan --green --red --purple`, sidebar, overlay, etc.
- `theme-light.css` (31 paginas): para paginas que no enlazan theme-vars; repite los valores claros y define los pares claros de colores fijos: `--lxt-<hex>` (texto), `--lxb-<hex>` (fondos) y `--lxd-rgba_*` (superposiciones). Convencion (fijada por `test_tema_resto_349`): la clave del nombre es el color del fallback, `var(--lxt-7fb3cc,#7fb3cc)`, asi el tema oscuro no cambia.
- `style.css` (4 paginas: ai_coach, analytics, athlete-app, athlete_profile, race_day segun el caso) trae su propio `:root` oscuro; `theme-light.css` lo pisa con `html[data-theme=light]` (mayor especificidad).

**Donde quedaban colores oscuros fijos (hex/rgb en vez de var) en modo claro:**

| Lugar | Problema |
|---|---|
| `nav.css` `#lx-upgrade-wall`, `.lx-uw-box/title/sub/back` | fondo `#08121e`, overlay `rgba(4,8,15,.9)`, textos `#f0f9ff/#7fb3cc/#3d6880` fijos: el muro de plan salia como bloque oscuro |
| `nav.js` toast (`lxToast`) | fondo `#08121E`, texto `#F0F9FF`, iconos `#FCA5A5/#6EE7B7/#7FB3CC/#FCD34D`, cerrar `#3D6880` |
| `nav.js` widget IA (coach/admin) | panel `#08121E`, form `#06101A`, textos `#E8F4F8/#4A7A96`, input blanco translucido |
| `nav.js` `lxUI` (cargando/error/vacio) | texto `#7FB3CC`, error `#FCA5A5` |
| `auth.js` aviso «modulo no incluido» | fondo `#08121E`, textos `#F0F9FF/#7FB3CC` |
| `dashboard.html` modal de upgrade (inline) | panel `#08121e`, textos `#7fb3cc/#3d6880` |
| `style.css .btn-p`, `dash-header.js` insignia campana, `community.js` borrar foto | el texto «blanco» usaba `--lxt-fff`, que en claro vale `#121212`: texto casi negro sobre naranja / sobre fondo negro (bug) |
| **Canvas** (Chart.js y dibujo a mano) | colores como cadenas JS no alcanzables por CSS: ejes/etiquetas `#7FB3CC`, `#3D6880`, `rgba(148,163,184,.6)`, grillas `rgba(255,255,255,.05)`, tooltips `#04141F/#07111D` con texto claro. Paginas con canvas: analytics (3), detalle (6), nutrition (3), blood_labs (3), coach (2), ai_coach (1). En claro: ejes casi invisibles sobre blanco |

**Lo que se verifico limpio (no se toco):** bloques `<style>` de todas las paginas (scan estatico: 0 fondos oscuros fijos fuera de var(), salvo `web-handoff.html`); `lx-info.js`, `lx-upgrade.js`, `gdpr-banner.js`, `lx-delete-account.js`, `lx-audit.js`, `footer.js`, `community.js`, `dash-header.js` (solo fondos de acento/overlay, ya cubiertos por `test_tema_resto_349`); `blood_labs.html` ya lee variables CSS en sus graficos.

## 2. Cambios

- `nav.css`: muro de plan con `var(--lxb-08121e)`, `var(--lxb-rgba_4_8_15_p9)`, `var(--lxt-…)` (fallback = color original).
- `nav.js`: toast, widget IA y `lxUI` con variables; **`LXCanvasTheme`** nuevo: en tema claro intercepta `fillStyle/strokeStyle/shadowColor` y `addColorStop` y traduce solo los colores pensados para fondo oscuro a su par claro (mismos valores que `--lxt-*`); fondos de tooltip oscuros → blanco; colores de datos, `#fff` y azul de grilla no se tocan; en oscuro no hace nada. Al cambiar de tema repinta: `Chart.instances[].update('none')`, evento `lxthemechange` y `resize` (analytics ya redibuja con resize).
- `auth.js`: aviso de plan con variables.
- `dashboard.html`: modal de upgrade con variables.
- `style.css`, `dash-header.js`, `community.js`: texto sobre acento usa `var(--on-accent,#fff)` (definida `#fff` en `theme-light.css`).
- `theme-light.css`: nuevas `--lxt-3d6880/4a7a96/6ee7b7/fcd34d/rgba_232_244_248_p88/e8f4f8`, `--lxb-06101a`, `--lxb-rgba_4_8_15_p9`, `--on-accent`.
- Sellos: `BUILD_VERSION '396'` + changelog en `sw.js`; `i18n.js?v=396`, `theme-light.css?v=396`, `nav.js?v=11`, `nav.css?v=9`, `auth.js?v=374` en las paginas y en `sw.js`. Tests que fijaban 395/349/10 actualizados (bloodlabs_ejecutiva, dashboard_ejecutivo_344, nutrition_race_b6, recuperacion_394, tema_resto_349, cq2_cero_falsos, y 4 JS de 391/392/393/395).
- Sin claves i18n nuevas (no hay texto nuevo visible). Sin cifras ni contenido tocados.

**Tests nuevos:** `api/tests/test_tema_migracion_396.py` (7) y `tests/js/tema_396.test.js` (5). Verificado: en la base (con `git stash`) fallan 6/7 y 5/5; con el arreglo pasan.

## 3. Que queda (honesto)

- **No verificado visualmente en navegador**: el adaptador de canvas esta probado con un contexto 2D simulado y los guardianes son estaticos. Hace falta revisar a ojo analytics/detalle/nutricion/coach en claro.
- Graficos pintados antes de que cargue `nav.js` se corrigen solo al siguiente repintado (resize o cambio de tema).
- Si una pagina dibuja a mano un canvas con color oscuro de datos o `#fff` como texto sobre fondo claro, el adaptador no lo toca (por diseno).
- Chips oscuros intencionales sin migrar: banner offline y tooltip PMC de `dashboard.html`, toast de `training_plan.html` (texto claro sobre fondo oscuro propio, consistentes).
- `web-handoff.html` (pagina de canje de token, fondo `#0b1220` fijo, sin sistema de tema): fuera de la fundacion; pendiente.
- Texto fijo en espanol preexistente en `auth.js` («Modulo no incluido…», «Ver Planes») y `nav.js` («Reintentar»): no se tocaron (fuera del alcance de tema).
- Las 5 paginas (Race Day, Perfil, Labs, Gear, Comunidad) no se redisenaron, como se pidio.
- `test:js`: se agregaron al script los de 393, 394, 395 y el nuevo 396.

## 4. Verificacion

- `npm run test:js`: **299 tests, 299 pass, 0 fail** (antes del script: faltaban 393/394/395; ahora incluidos junto con el nuevo 396).
- `pytest api/tests` (suite completa, 28 min): primera pasada 3657 passed, 1 skipped, **2 failed**, ambos consecuencia de los nuevos sellos y ya corregidos:
  - `test_shell1_cascara::test_version_de_nav_uniforme_en_todas_las_paginas` (fijaba nav.js v=10 / nav.css v=8) -> actualizado a 11 / 9.
  - `test_i18n::test_mobile_mirrors_match_root_sw` (copias gitignoradas de sw.js desfasadas): resuelto regenerando www/android/ios con `scripts/build_www.py` + `npx cap sync` (gitignorado, no entra al commit).
  - Re-corrida de los archivos afectados (i18n, shell1, tema 396/349, cq2): pasan. No se re-corrio la suite completa tras esos dos arreglos de sello.
  - Los 2 fallos intermitentes de `test_calendario_vivo_375` no reaparecieron.

## 5. Commit

Commit local en main: `feat(theme): migracion de tema modo claro consistente (MIGRACION-TEMA, BUILD 396)` (hash: `git log -1`; sin push, sin deploy). Salida de pytest: `labx-overnight/pytest396.txt`.
