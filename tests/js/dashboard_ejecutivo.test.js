// DASHBOARD-EJECUTIVO (BUILD 344): bandas i18n, regla de siglas y sistema de tema (JS real).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.join(__dirname, '..', '..');
const I18N_SRC = fs.readFileSync(path.join(ROOT, 'i18n.js'), 'utf8');
const NAV_SRC = fs.readFileSync(path.join(ROOT, 'nav.js'), 'utf8');

function extractDictLiteral(src) {
  const start = src.indexOf('var DICT');
  const open = src.indexOf('{', start);
  let depth = 0, quote = null, escaped = false, lc = false, bc = false;
  for (let i = open; i < src.length; i++) {
    const ch = src[i], next = src[i + 1];
    if (lc) { if (ch === '\n') lc = false; continue; }
    if (bc) { if (ch === '*' && next === '/') { bc = false; i++; } continue; }
    if (quote) {
      if (escaped) { escaped = false; continue; }
      if (ch === '\\') { escaped = true; continue; }
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === '/' && next === '/') { lc = true; i++; continue; }
    if (ch === '/' && next === '*') { bc = true; i++; continue; }
    if (ch === "'" || ch === '"' || ch === '`') { quote = ch; continue; }
    if (ch === '{') depth++;
    if (ch === '}' && --depth === 0) return src.slice(open, i + 1);
  }
  throw new Error('DICT sin cierre');
}
const DICT = new Function('return (' + extractDictLiteral(I18N_SRC) + ')')();

test('las tres preguntas existen en ES/PT/EN con el texto literal del SPEC', () => {
  const want = {
    dash_q_today: ['¿Cómo estoy hoy?', 'Como estou hoje?', 'How am I today?'],
    dash_q_load: ['¿Cómo está mi carga?', 'Como está minha carga?', 'How is my load?'],
    dash_q_where: ['¿Para dónde voy?', 'Para onde estou indo?', 'Where am I headed?'],
  };
  ['es', 'pt', 'en'].forEach((lang, i) => {
    for (const k of Object.keys(want)) assert.equal(DICT[lang][k], want[k][i], lang + ':' + k);
    for (const k of ['dash_q_today_sub', 'dash_q_load_sub', 'dash_q_where_sub'])
      assert.ok(DICT[lang][k] && DICT[lang][k].length > 10, lang + ':' + k);
  });
});

test('selector de tema: etiquetas Tema/Oscuro/Claro en ES/PT/EN', () => {
  const want = { es: ['Tema', 'Oscuro', 'Claro'], pt: ['Tema', 'Escuro', 'Claro'], en: ['Theme', 'Dark', 'Light'] };
  for (const lang of Object.keys(want)) {
    assert.deepEqual([DICT[lang].theme_label, DICT[lang].theme_dark, DICT[lang].theme_light], want[lang]);
  }
});

test('regla de siglas: ninguna etiqueta del dashboard queda con la sigla sola', () => {
  const keys = [
    'dash_ctl_label', 'dash_atl_label', 'dash_tsb_label', 'dash_acwr_load', 'dash_acwr_swim',
    'dash_acwr_bike', 'dash_acwr_run', 'dash_acwr_str', 'dash_hrv_label', 'dash_rhr',
    'dash_tss_week', 'dash_tss_total', 'dash_readiness_label',
  ];
  for (const lang of ['es', 'pt', 'en']) {
    for (const k of keys) {
      const v = DICT[lang][k];
      assert.ok(v, lang + ':' + k);
      // nombre primero, sigla entre parentesis (o nombre sin sigla, como "LabX Readiness")
      assert.ok(!/^(CTL|ATL|TSB|ACWR|TSS|HRV|FC)\b/.test(v), lang + ':' + k + ' = ' + v);
    }
  }
  assert.equal(DICT.es.dash_ctl_label, 'Forma (CTL)');
  assert.equal(DICT.es.dash_atl_label, 'Fatiga (ATL)');
  assert.equal(DICT.es.dash_tsb_label, 'Equilibrio (TSB)');
  assert.equal(DICT.es.dash_tss_total, 'Carga total (TSS)');
  assert.equal(DICT.es.dash_hrv_label, 'Variabilidad cardíaca (HRV)');
  assert.equal(DICT.es.dash_rhr, 'Pulsos en reposo (FC)');
  assert.match(DICT.es.dash_readiness_label, /^Preparación \(Readiness\)/);
});

function loadTheme(stored) {
  const i = NAV_SRC.indexOf('var LXTheme = window.LXTheme = (function(){');
  assert.ok(i >= 0, 'LXTheme no esta en nav.js');
  const j = NAV_SRC.indexOf('})();', i) + 5;
  const store = Object.assign({}, stored);
  const attrs = {};
  const sandbox = {
    window: {},
    localStorage: {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = String(v); },
    },
    document: {
      documentElement: { setAttribute: (k, v) => { attrs[k] = v; } },
      querySelectorAll: () => [],
    },
  };
  sandbox.window.addEventListener = () => {};
  sandbox.window.localStorage = sandbox.localStorage;
  vm.createContext(sandbox);
  vm.runInContext(
    'var window = this.window; window.addEventListener = function(){};' + NAV_SRC.slice(i, j) + ';this.T = window.LXTheme;',
    sandbox,
  );
  return { T: sandbox.T, store, attrs };
}

test('LXTheme: oscuro por defecto, persiste en labx_theme y aplica data-theme', () => {
  let { T, store, attrs } = loadTheme({});
  assert.equal(T.get(), 'dark');
  assert.equal(attrs['data-theme'], 'dark');
  T.set('light');
  assert.equal(store.labx_theme, 'light');
  assert.equal(attrs['data-theme'], 'light');
  assert.equal(T.get(), 'light');
  T.set('cualquier-cosa');
  assert.equal(store.labx_theme, 'dark');
});

test('nav.js compila completo (el selector de tema no rompe el menu)', () => {
  assert.doesNotThrow(() => new vm.Script(NAV_SRC, { filename: 'nav.js' }));
  assert.ok(NAV_SRC.includes("LXTheme.set(\\'dark\\')"));
  assert.ok(NAV_SRC.includes("LXTheme.set(\\'light\\')"));
});

test('LXTheme: respeta la eleccion guardada al cargar', () => {
  const { T, attrs } = loadTheme({ labx_theme: 'light' });
  assert.equal(T.get(), 'light');
  assert.equal(attrs['data-theme'], 'light');
});
