'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const HTML = fs.readFileSync(path.join(__dirname, '..', '..', 'recovery.html'), 'utf8');

test('403/error de coach-view no deja la vista en "Cargando"', () => {
  assert.ok(!/r\.status === 403\) return null/.test(HTML));
  assert.match(HTML, /if \(!r\.ok\) throw new Error\('coach-view '/);
  assert.match(HTML, /\.catch\(function \(\) \{[\s\S]{0,200}coach-view-content[\s\S]{0,300}rcw_load_error/);
});

test('la vista pinta atletas desde la respuesta real', () => {
  assert.match(HTML, /fetch\(API \+ '\/recovery\/coach-view'/);
  assert.match(HTML, /d\.athletes \|\| \[\]/);
  assert.match(HTML, /el\.innerHTML = html/);
});
