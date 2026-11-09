// COACH-ALTAS: parseo de correos pegados y presencia de la UI en coach.html
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

const { bulkParseEmails } = new Function(extract('bulkParseEmails') + '; return {bulkParseEmails};')();
const st = (r) => r.map((x) => x.email + ':' + x.status);

test('parsea lineas, comas, dedupe y roster', () => {
  const r = bulkParseEmails('a@x.com\nb@x.com, c@x.com\nmala\nA@x.com\nexiste@x.com', ['Existe@x.com']);
  assert.deepStrictEqual(st(r), [
    'a@x.com:ok', 'b@x.com:ok', 'c@x.com:ok', 'mala:invalid', 'a@x.com:dup_list', 'existe@x.com:dup_roster',
  ]);
});

test('email;nombre usa el nombre y acepta tab de planilla', () => {
  const r = bulkParseEmails('ana@x.com;Ana Paz\nbeto@x.com\tBeto Ruiz\n\n  \nx@y.com;');
  assert.strictEqual(r[0].nombre, 'Ana Paz');
  assert.strictEqual(r[1].nombre, 'Beto Ruiz');
  assert.strictEqual(r[2].email, 'x@y.com');
  assert.strictEqual(r.length, 3);
});

test('vacio y espacios no generan filas', () => {
  assert.deepStrictEqual(bulkParseEmails('  \n\n,,'), []);
});

test('UI: boton, modales y barra de seleccion presentes; singulares intactos', () => {
  for (const id of ['btn-bulk-invite', 'modal-bulk-invite', 'modal-bulk-group', 'roster-selbar', 'roster-addgroup'])
    assert.ok(src.includes('id="' + id + '"'), id);
  assert.ok(src.includes('/coach/athletes/bulk') && src.includes('/members/bulk') && src.includes('/groups/with-members'));
  assert.ok(src.includes('id="modal-add-member"') && src.includes('id="modal-new-athlete"'));
});
