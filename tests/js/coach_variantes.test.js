// COACH-VARIANTES: control de factor de volumen de coach.html
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

const names = ['volParse', 'volFactorFor', 'volOverrides', 'volLabel', 'destBatchItems'];
const code =
  'var VOL_MIN = 0.5, VOL_MAX = 1.5;\n' + names.map(extract).join('\n') + '\nreturn {' + names.join(',') + '};';
const api = new Function(code)();

test('volParse acepta 0.5–1.5 (coma o punto) y rechaza el resto', () => {
  assert.strictEqual(api.volParse('0.8'), 0.8);
  assert.strictEqual(api.volParse('1,25'), 1.25);
  assert.strictEqual(api.volParse(1), 1);
  assert.strictEqual(api.volParse('0.49'), null);
  assert.strictEqual(api.volParse('1.51'), null);
  assert.strictEqual(api.volParse(''), null);
  assert.strictEqual(api.volParse('abc'), null);
});

test('volFactorFor: override por atleta pisa al general; inválido cae al general', () => {
  const st = { vol: 0.8, vf: { a2: '1.2', a3: '9' } };
  assert.strictEqual(api.volFactorFor(st, 'a1'), 0.8);
  assert.strictEqual(api.volFactorFor(st, 'a2'), 1.2);
  assert.strictEqual(api.volFactorFor(st, 'a3'), 0.8);
  assert.strictEqual(api.volFactorFor({ vol: 1, vf: {} }, 'a1'), 1);
});

test('volOverrides solo incluye valores distintos del general y válidos', () => {
  const st = { vol: 0.8, vf: { a1: '0.8', a2: '1.2', a3: '9' } };
  assert.deepStrictEqual(api.volOverrides(st, ['a1', 'a2', 'a3']), { a2: 1.2 });
});

test('destBatchItems: con factor 1.0 el ítem es idéntico al de antes (sin volume_factor)', () => {
  const sin = api.destBatchItems(['a1'], 't', '2026-11-10', null);
  assert.deepStrictEqual(sin, [{ template_id: 't', athlete_id: 'a1', date_iso: '2026-11-10', notas: null }]);
  const f = api.destBatchItems(['a1', 'a2'], 't', '2026-11-10', null, (id) => (id === 'a1' ? 0.8 : 1));
  assert.strictEqual(f[0].volume_factor, 0.8);
  assert.ok(!('volume_factor' in f[1]));
});

test('volLabel y badge de Ver Plan', () => {
  assert.strictEqual(api.volLabel(0.8), 'Volumen ×0.8');
  assert.ok(src.includes("volLabel(a.volume_factor)"));
  assert.ok(src.includes('id="asgn-vol"') && src.includes('id="wta-vol"') && src.includes('id="mca-vol"'));
});
