// P11-A — diccionario de términos (i18n) y componente LXTerm (lx-info.js).
// Ejecutar: node --test tests/js/
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const I18N_SRC = fs.readFileSync(path.join(ROOT, 'i18n.js'), 'utf8');
const LXT_SRC = fs.readFileSync(path.join(ROOT, 'lx-info.js'), 'utf8');

const LANGS = ['es', 'pt', 'en'];
const IDS = [
  'ctl', 'atl', 'tsb', 'acwr', 'tss', 'hrv', 'recovery_score', 'readiness',
  'body_battery', 'fatiga_mental', 'ftp', 'css', 'vo2max', 'rpe',
  'compliance', 'tapering',
  'resting_hr', 'fatiga_muscular', 'sueno',
  'ctl_projected', 'goal_race_ctl', 'injury_risk',
  'wkg', 'cp', 'wprime',
];

// Extrae el literal `var DICT = {...}` de i18n.js respetando strings y comentarios.
function extractDictLiteral(src) {
  const start = src.indexOf('var DICT');
  assert.notEqual(start, -1, 'no se encontró var DICT en i18n.js');
  const open = src.indexOf('{', start);
  let depth = 0;
  let quote = null;
  let escaped = false;
  let lineComment = false;
  let blockComment = false;

  for (let i = open; i < src.length; i++) {
    const ch = src[i];
    const next = src[i + 1];

    if (lineComment) {
      if (ch === '\n') lineComment = false;
      continue;
    }
    if (blockComment) {
      if (ch === '*' && next === '/') { blockComment = false; i++; }
      continue;
    }
    if (quote) {
      if (escaped) { escaped = false; continue; }
      if (ch === '\\') { escaped = true; continue; }
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === '/' && next === '/') { lineComment = true; i++; continue; }
    if (ch === '/' && next === '*') { blockComment = true; i++; continue; }
    if (ch === "'" || ch === '"' || ch === '`') { quote = ch; continue; }
    if (ch === '{') depth++;
    if (ch === '}') {
      depth--;
      if (depth === 0) return src.slice(open, i + 1);
    }
  }
  throw new Error('no se pudo balancear el literal de DICT');
}

const DICT = new Function('return (' + extractDictLiteral(I18N_SRC) + ')')();

// Carga lx-info.js en un contexto aislado con un DOM mínimo: alcanza para
// data()/render() (no abre tarjetas). Se usa vm para que `window` sea el
// propio global — el archivo hace `window.lxInfo = ...` y después usa `lxInfo`.
function loadLXTerm() {
  const vm = require('node:vm');
  const noop = () => {};
  const fakeEl = () => ({
    style: {}, textContent: '', innerHTML: '',
    setAttribute: noop, getAttribute: () => null,
    appendChild: noop, addEventListener: noop, focus: noop,
    querySelector: () => null, querySelectorAll: () => [],
    classList: { add: noop, remove: noop },
  });
  const doc = {
    readyState: 'complete',
    head: fakeEl(),
    body: fakeEl(),
    documentElement: Object.assign(fakeEl(), { lang: 'es' }),
    addEventListener: noop,
    removeEventListener: noop,
    querySelectorAll: () => [],
    querySelector: () => null,
    getElementById: () => null,
    createElement: () => fakeEl(),
  };
  const state = { lang: 'es' };
  const sandbox = {
    document: doc,
    innerWidth: 1280,
    innerHeight: 800,
    setTimeout,
    console,
    i18n: { t: (k) => (DICT[state.lang] && DICT[state.lang][k]) || k },
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(LXT_SRC, sandbox, { filename: 'lx-info.js' });
  return { LXTerm: sandbox.LXTerm, state };
}

const { LXTerm, state } = loadLXTerm();

test('LXTerm expone los 16 términos del plan', () => {
  assert.ok(LXTerm, 'window.LXTerm no se definió');
  assert.deepEqual([...LXTerm.ids].sort(), [...IDS].sort());
});

test('cada término tiene name, short y action en ES, PT y EN', () => {
  const faltantes = [];
  for (const lang of LANGS) {
    state.lang = lang;
    for (const id of IDS) {
      const d = LXTerm.data(id);
      const prefijo = `[${lang}] ${id}`;
      if (!d.name || d.name === `term_${id}_name`) faltantes.push(prefijo + ' name');
      if (!d.short || d.short === `term_${id}_short`) faltantes.push(prefijo + ' short');
      if (!d.action || d.action === `term_${id}_action`) faltantes.push(prefijo + ' action');
    }
  }
  state.lang = 'es';
  assert.deepEqual(faltantes, [], 'claves faltantes: ' + faltantes.join(', '));
});

test('el diccionario tiene las mismas claves term_* en los 3 idiomas', () => {
  const claves = (lang) => Object.keys(DICT[lang]).filter((k) => k.startsWith('term_'));
  const base = claves('es').sort();
  assert.equal(base.length, IDS.length * 3 + 3, 'se esperan 48 + 3 claves de UI');
  assert.deepEqual(claves('pt').sort(), base);
  assert.deepEqual(claves('en').sort(), base);
});

test('cada término tiene una sigla distinta y no vacía', () => {
  const siglas = IDS.map((id) => LXTerm.siglas[id]);
  assert.ok(siglas.every((s) => typeof s === 'string' && s.length > 0));
  assert.equal(new Set(siglas).size, siglas.length, 'hay siglas repetidas');
});

test('render() usa un <button> accesible, no un div clickeable', () => {
  const html = LXTerm.render('ctl');
  assert.match(html, /<button[^>]*class="lx-term-info"/);
  assert.match(html, /type="button"/);
  assert.match(html, /aria-expanded="false"/);
  assert.match(html, /aria-controls="lx-term-card-ctl"/);
  assert.doesNotMatch(html, /<div/, 'el disparador no debe ser un div');
  assert.match(html, /lx-term-name">Forma</, 'debe mostrar el nombre simple (DASHBOARD-EJECUTIVO: Forma + sigla entre paréntesis por CSS)');
  assert.match(html, /<span class="lx-term-sigla">CTL<\/span>/, 'la sigla va como subtítulo');
});

test('data() cae a la sigla si i18n no tiene la clave', () => {
  const d = LXTerm.data('termino_inexistente');
  assert.equal(d.name, 'TERMINO_INEXISTENTE');
  assert.equal(d.short, '');
  assert.equal(d.action, '');
});
