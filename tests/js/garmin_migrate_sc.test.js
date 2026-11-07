// S-C: banner de migracion a Garmin oficial -- condicion de visibilidad y descarte
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
const web = fs.readFileSync(path.join(__dirname, '..', '..', 'athlete_profile.html'), 'utf8');
const { cardModel, visible } = new Function(
  extract(web, 'garminCardModel') + extract(web, 'gmigVisible') +
    '; return { cardModel: garminCardModel, visible: gmigVisible };',
)();
const show = (legacy, off, dismissed) => visible(cardModel(legacy, off, false), !!dismissed);

test('legacy si + oficial no -> se ve', () => {
  assert.strictEqual(show(true, 'not_connected'), true);
});
test('oficial conectado (con o sin legacy) -> no se ve', () => {
  assert.strictEqual(show(true, 'connected'), false);
  assert.strictEqual(show(false, 'connected'), false);
});
test('sin legacy -> no se ve', () => {
  assert.strictEqual(show(false, 'not_connected'), false);
  assert.strictEqual(show(null, 'not_connected'), false);
});
test('oficial no disponible / con error / sin consultar -> no se ve (no ofrecer un callejon sin salida)', () => {
  for (const st of ['unavailable', 'error', null, '']) assert.strictEqual(show(true, st), false, String(st));
});
test('descartado -> no se ve; al conectar oficial desaparece aunque no se haya descartado', () => {
  assert.strictEqual(show(true, 'not_connected', true), false);
  assert.strictEqual(show(true, 'connected', false), false);
});
test('descarte por usuario en localStorage', () => {
  const store = {};
  const ls = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => (store[k] = v) };
  const code = 'var _profile={id:"u7"};function gmigRender(){}' + extract(web, 'gmigKey') +
    extract(web, 'gmigDismissed') + extract(web, 'gmigDismiss') +
    'var a=gmigDismissed(); gmigDismiss(); return [gmigKey(), a, gmigDismissed()];';
  const [key, before, after] = new Function('localStorage', code)(ls);
  assert.strictEqual(key, 'lx_garmin_migrate_dismissed:u7');
  assert.strictEqual(before, false);
  assert.strictEqual(after, true);
});
test('el boton primario usa el OAuth oficial existente', () => {
  const i = web.indexOf('id="garmin-migrate-banner"');
  assert.ok(i > web.indexOf('id="tab-conexiones"'));
  assert.ok(web.slice(i, i + 1500).includes('garminOfficialConnect()'));
});
