// FLOW-INTEGRA: la pagina de planes muestra Esencial comprable y Completo como "Pronto"
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..', '..');
const html = fs.readFileSync(path.join(root, 'planes.html'), 'utf8');

test('planes.html usa solo endpoints /api/flow y el token general', () => {
  assert.ok(html.includes("'/api/flow' + path"));
  assert.ok(html.includes("'/checkout'") && html.includes("'/cancel'") && html.includes("'/config'"));
  assert.ok(html.includes("localStorage.getItem('lx_co_token')"));
});

test('Completo no tiene checkout: se pinta deshabilitado como Pronto', () => {
  assert.ok(html.includes("if (!p.available) { btn.textContent = 'Pronto'; btn.disabled = true; }"));
});

test('el retorno del navegador no activa nada: aviso de confirmacion por Flow', () => {
  assert.ok(html.includes('cuando Flow confirma el pago'));
});

test('sw.js precachea planes.html y usa el tema global', () => {
  assert.ok(fs.readFileSync(path.join(root, 'sw.js'), 'utf8').includes("'/planes.html'"));
  assert.ok(html.includes('theme-vars.css'));
});
