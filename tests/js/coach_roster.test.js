// COACH-ROSTER: buscador, filtros, columna Objetivo/dias y paginacion del roster de coach.html
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const src = fs.readFileSync(path.join(__dirname, '..', '..', 'coach.html'), 'utf8');

function extract(name) {
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

const esc = (s) => (s == null ? '' : String(s));
const _t = (k, fb) => fb;
const code = [
  'var ROSTER_PAGE_SIZE = 50; var _roster = {wellness:{}};',
  extract('rosterH'),
  extract('rosterDays'),
  extract('rosterFilter'),
  extract('rosterPage'),
  extract('rosterRow'),
  'function _wellnessBadge(){return "W";} function planBadge(p){return p;}',
  'return {rosterDays, rosterFilter, rosterPage, rosterRow};',
].join('\n');
const api = new Function('esc', '_t', code)(esc, _t);

const TODAY = new Date(2026, 10, 8); // 2026-11-08
function mk(i, over) {
  return Object.assign(
    { id: 'u' + i, nombre: 'Atleta ' + i, email: 'a' + i + '@x.com', plan_nivel: 'pro', has_garmin: i % 2 === 0, race_goal_name: null, race_goal_date: null, _grps: [] },
    over || {},
  );
}
const list = [
  mk(1, { nombre: 'Ana Pérez', email: 'ana@x.com', _grps: ['Elite'], race_goal_name: 'Ironman 70.3', race_goal_date: '2026-12-08' }),
  mk(2, { nombre: 'Beto', email: 'beto@y.com', _grps: ['Elite', 'Run'], race_goal_name: 'Maratón', race_goal_date: '2027-06-01' }),
  mk(3, { nombre: 'Carla', email: 'carla@x.com', _grps: [], has_garmin: false }),
  mk(4, { nombre: 'Dani', email: 'dani@x.com', _grps: ['Run'], has_garmin: true, race_goal_name: 'Sin fecha' }),
];

test('rosterDays: dias reales o null', () => {
  assert.strictEqual(api.rosterDays('2026-12-08', TODAY), 30);
  assert.strictEqual(api.rosterDays('2026-11-08', TODAY), 0);
  assert.strictEqual(api.rosterDays(null, TODAY), null);
  assert.strictEqual(api.rosterDays('basura', TODAY), null);
});

test('buscador reduce filas por nombre y email', () => {
  assert.strictEqual(api.rosterFilter(list, { q: 'ana' }, TODAY).length, 1);
  assert.strictEqual(api.rosterFilter(list, { q: 'y.com' }, TODAY).length, 1);
  assert.strictEqual(api.rosterFilter(list, { q: 'x.com' }, TODAY).length, 3);
  assert.strictEqual(api.rosterFilter(list, { q: '' }, TODAY).length, 4);
});

test('filtros por grupo, garmin y objetivo', () => {
  const n = (f) => api.rosterFilter(list, f, TODAY).map((u) => u.id).join(',');
  assert.strictEqual(n({ group: 'Elite' }), 'u1,u2');
  assert.strictEqual(n({ group: '__none__' }), 'u3');
  assert.strictEqual(n({ garmin: 'yes' }), 'u2,u4');
  assert.strictEqual(n({ garmin: 'no' }), 'u1,u3');
  assert.strictEqual(n({ goal: 'soon' }), 'u1');
  assert.strictEqual(n({ goal: 'any' }), 'u1,u2,u4');
  assert.strictEqual(n({ goal: 'none' }), 'u3');
});

test('los filtros combinan con el buscador', () => {
  const r = api.rosterFilter(list, { q: 'x.com', group: 'Run', garmin: 'yes' }, TODAY);
  assert.deepStrictEqual(r.map((u) => u.id), ['u4']);
  assert.strictEqual(api.rosterFilter(list, { q: 'beto', goal: 'none' }, TODAY).length, 0);
});

test('columna Objetivo: nombre con dato, guion sin dato', () => {
  const withGoal = api.rosterRow(list[0]);
  assert.ok(withGoal.includes('Ironman 70.3'));
  assert.ok(withGoal.includes('30 d'));
  const noGoal = api.rosterRow(list[2]);
  assert.ok(noGoal.includes('—'));
  assert.ok(!/\d+ d</.test(noGoal));
  const noDate = api.rosterRow(list[3]);
  assert.ok(noDate.includes('Sin fecha'));
  assert.ok(noDate.includes('—'));
});

test('paginacion de 50: sin perdida ni duplicados, acciones en cada fila', () => {
  const many = [];
  for (let i = 0; i < 123; i++) many.push(mk(i, { has_garmin: true }));
  const seen = new Set();
  let total = 0;
  const p1 = api.rosterPage(many, 1);
  assert.strictEqual(p1.pages, 3);
  for (let p = 1; p <= p1.pages; p++) {
    const pg = api.rosterPage(many, p);
    pg.rows.forEach((u) => {
      seen.add(u.id);
      total++;
      const h = api.rosterRow(u);
      ['openAthletePlan', 'openAthleteNotes', 'openEditAthlete', 'openAddMemberFor', 'syncAthleteGarmin', 'deleteAthlete'].forEach((fn) =>
        assert.ok(h.includes(fn + "('" + u.id), fn + ' falta en ' + u.id),
      );
    });
  }
  assert.strictEqual(total, 123);
  assert.strictEqual(seen.size, 123);
  assert.strictEqual(api.rosterPage(many, 99).page, 3);
  assert.strictEqual(api.rosterPage([], 1).pages, 1);
});
