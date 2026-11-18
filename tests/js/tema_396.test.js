// MIGRACION-TEMA (BUILD 396): el adaptador de canvas traduce colores del tema oscuro al claro.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const NAV = fs.readFileSync(path.join(__dirname, '..', '..', 'nav.js'), 'utf8');
const SW = fs.readFileSync(path.join(__dirname, '..', '..', 'sw.js'), 'utf8');

function load(theme) {
  const start = NAV.indexOf('var LXCanvasTheme = window.LXCanvasTheme');
  assert.ok(start > 0, 'nav.js debe definir LXCanvasTheme');
  const end = NAV.indexOf('var LXTheme = window.LXTheme', start);
  const src = NAV.slice(start, end);
  const calls = [];
  class Ctx {
    set fillStyle(v) { this._f = v; }
    get fillStyle() { return this._f; }
    set strokeStyle(v) { this._s = v; }
    get strokeStyle() { return this._s; }
    set shadowColor(v) { this._sh = v; }
    get shadowColor() { return this._sh; }
  }
  class Grad { addColorStop(o, c) { calls.push(c); } }
  const win = { CanvasRenderingContext2D: Ctx, CanvasGradient: Grad };
  const sandbox = {
    window: win, document: { documentElement: { getAttribute: () => theme } },
    CanvasRenderingContext2D: Ctx, CanvasGradient: Grad, Object, parseFloat, Event: class {},
    CustomEvent: class {}, Chart: undefined,
  };
  win.document = sandbox.document;
  vm.runInNewContext(src, sandbox);
  return { api: win.LXCanvasTheme, Ctx, Grad, calls };
}

test('tema claro: textos de eje y grillas de fondo oscuro pasan a su par claro', () => {
  const { api } = load('light');
  assert.strictEqual(api.map('#7FB3CC'), '#346a83');
  assert.strictEqual(api.map('#3D6880'), '#4f6b7d');
  assert.strictEqual(api.map('rgba(148,163,184,.6)'), 'rgba(75,91,113,.6)');
  assert.strictEqual(api.map('rgba(255,255,255,.05)'), 'rgba(10,37,64,.05)');
  assert.strictEqual(api.map('#04141F'), '#ffffff'); // fondo de tooltip oscuro
});

test('tema claro: colores de datos y blanco solido no se tocan', () => {
  const { api } = load('light');
  assert.strictEqual(api.map('#10B981'), '#10B981');
  assert.strictEqual(api.map('rgba(8,116,174,.06)'), 'rgba(8,116,174,.06)');
  assert.strictEqual(api.map('#fff'), '#fff');
  assert.strictEqual(api.map('rgba(255,255,255,1)'), 'rgba(255,255,255,1)');
});

test('tema oscuro: no cambia nada', () => {
  const { api } = load('dark');
  assert.strictEqual(api.map('#7FB3CC'), '#7FB3CC');
  assert.strictEqual(api.map('rgba(255,255,255,.05)'), 'rgba(255,255,255,.05)');
});

test('el contexto 2D intercepta fillStyle/strokeStyle y los gradientes', () => {
  const { Ctx, Grad, calls } = load('light');
  const c = new Ctx();
  c.fillStyle = '#7FB3CC';
  c.strokeStyle = 'rgba(255,255,255,.05)';
  assert.strictEqual(c.fillStyle, '#346a83');
  assert.strictEqual(c.strokeStyle, 'rgba(10,37,64,.05)');
  new Grad().addColorStop(0, '#94a3b8');
  assert.deepStrictEqual(calls, ['#4b5b71']);
});

test('BUILD 396 y sello i18n.js?v=402', () => {
  assert.match(SW, /var BUILD_VERSION = '402'/);
  assert.ok(SW.includes("'/i18n.js?v=402'"));
});
