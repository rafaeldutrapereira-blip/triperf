// CARRERAS-DASHBOARD: franja de carreras del año del Dashboard (modelo y render)
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

function extract(src, name) {
  const i = src.indexOf('function ' + name + '(');
  assert.ok(i >= 0, name + ' no existe');
  const j = src.indexOf('{', src.indexOf(')', i));
  let depth = 0;
  for (let k = j; k < src.length; k++) {
    if (src[k] === '{') depth++;
    else if (src[k] === '}' && --depth === 0) return src.slice(i, k + 1);
  }
  throw new Error('sin cierre ' + name);
}
const root = path.join(__dirname, '..', '..');
const web = fs.readFileSync(path.join(root, 'dashboard.html'), 'utf8');
const a = web.indexOf('var _RACE_DIST = {');
const maps = web.slice(a, web.indexOf('function _raceDistLabel('));

function build(dict, lang) {
  const _t = (k, fb) => (dict[k] !== undefined ? dict[k] : fb);
  const _dashLoc = () => ({ es: 'es-CL', pt: 'pt-BR', en: 'en-US' })[lang];
  const src =
    maps +
    ['_raceDistLabel', '_raceShortDate', '_raceLongDate', 'raceStripModel', 'raceYearHtml', '_raceEsc']
      .map((n) => extract(web, n))
      .join('\n') +
    '; return {_raceDistLabel, _raceShortDate, _raceLongDate, raceStripModel, raceYearHtml, _raceEsc};';
  return new Function('_t', '_dashLoc', src)(_t, _dashLoc);
}
const ES = { prof_opt_703: '70.3 / Half (113 km)', prof_opt_ironman: 'Ironman (226 km)' };
const TODAY = '2026-11-07';
const R = (id, name, date_iso, o) =>
  Object.assign({ id, name, date_iso, distance: null, priority: null, is_goal_race: false, has_result: false }, o);

test('proxima + 3 del año con una pasada: la futura mas cercana va en grande', () => {
  const m = build(ES, 'es');
  const races = [
    R('c', 'Santiago', '2027-04-18'),
    R('a', 'Enero 10K', '2026-01-10', { has_result: true, priority: 'C' }),
    R('b', 'Valdivia 70.3', '2026-11-29', { distance: '70.3', priority: 'B' }),
    R('d', 'Pucon', '2026-12-06', { priority: 'A' }),
  ];
  const model = m.raceStripModel(races, TODAY);
  assert.strictEqual(model.featured.id, 'b');
  assert.deepStrictEqual(model.others.map((r) => r.id), ['a', 'd', 'c']);
  const html = m.raceYearHtml(model.others, TODAY, m._raceEsc);
  assert.strictEqual((html.match(/kc-ry past/g) || []).length, 1); // solo la pasada
  assert.ok(html.indexOf('✓') >= 0 && html.indexOf('✓') < html.indexOf('Enero 10K'));
  assert.ok(html.includes('kc-ry-prio">A<'));
  assert.ok(/6 dic.*Pucon/.test(html));
  assert.strictEqual(m._raceDistLabel('70.3'), '70.3 / Half (113 km)'); // etiqueta, no codigo
});

test('solo una carrera: sin lista del año', () => {
  const m = build(ES, 'es');
  const model = m.raceStripModel([R('a', 'Unica', '2026-12-01')], TODAY);
  assert.strictEqual(model.featured.id, 'a');
  assert.strictEqual(m.raceYearHtml(model.others, TODAY, m._raceEsc), '');
});

test('ninguna carrera: sin destacada ni lista (estado vacio)', () => {
  const m = build(ES, 'es');
  for (const empty of [[], null, undefined]) {
    const model = m.raceStripModel(empty, TODAY);
    assert.strictEqual(model.featured, null);
    assert.deepStrictEqual(model.others, []);
  }
});

test('principal marcada distinta de la mas cercana gana el lugar grande', () => {
  const m = build(ES, 'es');
  const model = m.raceStripModel(
    [R('near', 'Cercana', '2026-11-20'), R('main', 'Principal', '2027-02-01', { is_goal_race: true })],
    TODAY,
  );
  assert.strictEqual(model.featured.id, 'main');
  assert.deepStrictEqual(model.others.map((r) => r.id), ['near']);
});

test('principal ya corrida no ocupa el lugar grande; hoy cuenta como futura', () => {
  const m = build(ES, 'es');
  const past = m.raceStripModel(
    [R('p', 'Vieja', '2026-03-01', { is_goal_race: true }), R('n', 'Hoy', TODAY)],
    TODAY,
  );
  assert.strictEqual(past.featured.id, 'n');
  const onlyPast = m.raceStripModel([R('p', 'Vieja', '2026-03-01')], TODAY);
  assert.strictEqual(onlyPast.featured, null);
  assert.strictEqual(onlyPast.others.length, 1);
});

test('nombres se escapan y fechas siguen el idioma', () => {
  const m = build(ES, 'en');
  const html = m.raceYearHtml([R('x', '<b>x</b>', '2026-11-29')], TODAY, m._raceEsc);
  assert.ok(!html.includes('<b>x'));
  assert.ok(html.includes('Nov'));
  assert.ok(/November/.test(m._raceLongDate('2026-11-29')));
});

test('la franja no usa kl_next_race y las claves i18n existen en los 3 idiomas', () => {
  const block = web.slice(web.indexOf('function renderRaceStrip('), web.indexOf('function tick('));
  assert.ok(!block.includes('kl_next_race'));
  assert.ok(!web.includes('kl_next_race'));
  const i18n = fs.readFileSync(path.join(root, 'i18n.js'), 'utf8');
  for (const k of ['dash_races_title', 'dash_races_main', 'dash_races_today', 'dash_races_tomorrow', 'dash_races_days_to', 'dash_races_none_next', 'dash_races_add']) {
    assert.strictEqual(i18n.split('    ' + k + ':').length - 1, 3, k);
  }
});
