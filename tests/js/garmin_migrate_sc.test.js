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

// SYNC-HONESTO: legacy caido -> tarjeta no dice "conectado" y el banner cambia de texto
const hon = new Function(
  'var _t=function(k,f){return f};' +
    extract(web, 'garminCardModel') + extract(web, 'gmigText') +
    '; return { cardModel: garminCardModel, text: gmigText };',
)();
test('needs_reauth/never -> legacyDown, connected=false, status legacy_down, banner visible', () => {
  for (const s of ['needs_reauth', 'never']) {
    const m = hon.cardModel(true, 'not_connected', false, s);
    assert.strictEqual(m.legacyDown, true);
    assert.strictEqual(m.connected, false);
    assert.strictEqual(m.status, 'legacy_down');
    assert.strictEqual(visible(m, false), true);
  }
});
test('live/stale/sin dato -> como antes (conectado)', () => {
  for (const s of ['live', 'stale', undefined]) {
    const m = hon.cardModel(true, 'not_connected', false, s);
    assert.strictEqual(m.legacyDown, false);
    assert.strictEqual(m.connected, true);
    assert.strictEqual(m.status, 'connected');
  }
  assert.strictEqual(hon.cardModel(true, 'not_connected', false, 'stale').legacyStale, true);
});
test('oficial conectado manda sobre legacy caido', () => {
  const m = hon.cardModel(true, 'connected', false, 'needs_reauth');
  assert.strictEqual(m.legacyDown, false);
  assert.strictEqual(m.connected, true);
});
test('texto del banner: caido con y sin fecha; vivo = texto actual', () => {
  const down = hon.cardModel(true, 'not_connected', false, 'needs_reauth');
  assert.ok(hon.text(down, '2026-06-25').includes('guardados hasta el 2026-06-25'));
  assert.ok(!/hasta/.test(hon.text(down, null)));
  assert.ok(/volver a recibir datos/.test(hon.text(down, null)));
  const live = hon.cardModel(true, 'not_connected', false, 'live');
  assert.ok(/segura/.test(hon.text(live, '2026-06-25')));
});

// Franja de reloj (indoor_workout.html): invitacion desde cero solo sin tuberia ni datos
const iw = fs.readFileSync(path.join(__dirname, '..', '..', 'indoor_workout.html'), 'utf8');
const wm = new Function(extract(iw, 'iwWatchOffModel') + '; return iwWatchOffModel;')();
test('franja: sin tuberia ni datos -> invita; con datos -> frescura; con tuberia viva -> oculta', () => {
  assert.strictEqual(wm({}).mode, 'invite');
  const s = wm({ dataUntil: '2026-06-25' });
  assert.strictEqual(s.mode, 'stale');
  assert.strictEqual(s.dataUntil, '2026-06-25');
  for (const k of ['official', 'strava', 'legacyLive'])
    assert.strictEqual(wm({ [k]: true, dataUntil: '2026-06-25' }).mode, 'hidden', k);
});
