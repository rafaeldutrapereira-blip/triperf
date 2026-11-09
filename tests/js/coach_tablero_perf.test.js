// COACH-TABLERO-PERF: el Gantt del equipo hace UNA peticion, no una por atleta
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const src = fs.readFileSync(path.join(__dirname, '..', '..', 'coach.html'), 'utf8');
const i = src.indexOf('window.loadGantt = async function');
assert.ok(i >= 0, 'loadGantt no existe');
const body = src.slice(i, src.indexOf('// Init week picker on load', i));

test('loadGantt usa el endpoint agregado del equipo', () => {
  assert.ok(body.includes("'/coach/assignments/team?start='"));
});

test('loadGantt ya no itera fetches por atleta', () => {
  assert.ok(!body.includes('/coach/assignments/athlete/'));
  assert.ok(!body.includes("'/coach/athletes'"));
  assert.ok(!/Promise\.all/.test(body));
  assert.strictEqual((body.match(/fetch\(/g) || []).length, 1);
});
