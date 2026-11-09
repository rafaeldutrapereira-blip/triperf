// CUENTA-BORRADO: modal compartido, enlaces y pagina publica
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..', '..');
const read = (f) => fs.readFileSync(path.join(root, f), 'utf8');

function load() {
  const win = { location: { protocol: 'https:', origin: 'https://x' }, i18n: null };
  win.window = win;
  vm.runInNewContext(read('lx-delete-account.js'), { window: win, document: {}, localStorage: { getItem: () => null } });
  return win.LXDeleteAccount;
}

test('el modal tiene ES/PT/EN con las mismas claves', () => {
  const tx = load()._tx;
  const keys = Object.keys(tx.es).sort();
  assert.ok(keys.length >= 15);
  for (const l of ['pt', 'en']) assert.deepStrictEqual(Object.keys(tx[l]).sort(), keys);
});

test('explica que se borra, que se conserva anonimo y el plazo maximo de 30 dias', () => {
  const tx = load()._tx;
  for (const l of ['es', 'pt', 'en']) {
    assert.ok(tx[l].keep.length > 40 && tx[l].del.length > 40);
    assert.ok(/30/.test(tx[l].when));
  }
});

test('llama al endpoint unico con la contrasena y sin id de usuario', () => {
  const src = read('lx-delete-account.js');
  assert.ok(src.includes("'/account/deletion-request'"));
  assert.ok(src.includes('JSON.stringify({ password: pw.value })'));
  assert.ok(!/user_id|athlete_id/.test(src));
});

test('perfil web y app montan el modal; la app tiene su boton', () => {
  const prof = read('athlete_profile.html');
  assert.ok(prof.includes('lx-delete-account.js') && prof.includes('LXDeleteAccount.open()'));
  assert.ok(prof.includes('id="zona-peligro"'));
  assert.ok(!prof.includes('Escribe DELETE'));
  const app = read('athlete-app.html');
  assert.ok(app.includes('lx-delete-account.js') && app.includes('id="pf-delete-account"'));
  const i18n = read('i18n.js');
  assert.strictEqual((i18n.match(/app_profile_delete_account:/g) || []).length, 3);
});

test('pagina publica: correo, enlace al flujo con sesion, sin guard, precacheada', () => {
  const html = read('eliminar-cuenta.html');
  assert.ok(html.includes('partnerships@labxperformanceapp.com'));
  assert.ok(html.includes('athlete_profile.html#zona-peligro'));
  assert.ok(!html.includes('auth.js') && !html.includes('routes.config.js'));
  const sw = read('sw.js');
  assert.ok(sw.includes("'/eliminar-cuenta.html'") && sw.includes("'/lx-delete-account.js?v=373'"));
  assert.ok(read('privacy.html').includes('href="eliminar-cuenta.html"'));
});
