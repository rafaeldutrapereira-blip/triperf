// A4: checklist "Primeros pasos" -- modelo de visibilidad
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
const web = fs.readFileSync(path.join(__dirname, '..', '..', 'dashboard.html'), 'utf8');
const steps = web.slice(web.indexOf('var ONB_STEPS'), web.indexOf('];', web.indexOf('var ONB_STEPS')) + 2);
const model = new Function(steps + extract(web, 'onbModel') + '; return onbModel;')();
const st = (o) => ({ steps: Object.assign({ connect: false, history: false, plan: false, profile: false }, o) });

test('sin estado (fallo de red) no se muestra', () => {
  assert.strictEqual(model(null, {}).visible, false);
});
test('atleta nuevo: visible con 0 de 4', () => {
  const m = model(st({}), {});
  assert.strictEqual(m.visible, true);
  assert.strictEqual(m.done, 0);
  assert.strictEqual(m.items.length, 4);
});
test('parcial: marca solo los completos', () => {
  const m = model(st({ connect: true, profile: true }), {});
  assert.deepStrictEqual(m.items.map((i) => i.done), [true, false, false, true]);
  assert.strictEqual(m.visible, true);
});
test('todo completo: desaparece sola', () => {
  assert.strictEqual(model(st({ connect: true, history: true, plan: true, profile: true }), {}).visible, false);
});
test('descartada: no se muestra aunque falte algo', () => {
  assert.strictEqual(model(st({}), { dismissed: true }).visible, false);
});
test('historial descartado/hecho en S-B cuenta como completo', () => {
  assert.strictEqual(model(st({}), { historyDismissed: true }).items[1].done, true);
  assert.strictEqual(model(st({}), { historyDone: true }).items[1].done, true);
  // y puede completar la lista
  const m = model(st({ connect: true, plan: true, profile: true }), { historyDismissed: true });
  assert.strictEqual(m.visible, false);
});
test('enlaces a Conexiones, Mi Plan y Perfil', () => {
  const m = model(st({}), {});
  assert.deepStrictEqual(m.items.map((i) => i.href),
    ['athlete_profile.html', 'athlete_profile.html', 'training_plan.html', 'athlete_profile.html']);
});
