// COACH-DESTINO-MULTIPLE: selector de destino múltiple, troceo y reportes por atleta de coach.html
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

const esc = (s) => String(s == null ? '' : s).replace(/</g, '&lt;');
const names = ['destFilter', 'destUnion', 'destWithout', 'destChunk', 'destSummary', 'destErrMsg',
  'destBatchItems', 'destBatchReport', 'destApplyReport', 'destReportHtml'];
const code = names.map(extract).join('\n') + '\nreturn {' + names.join(',') + '};';
const api = new Function('esc', code)(esc);

const athletes = [
  { id: 'a1', nombre: 'Ana', email: 'ana@x.com' },
  { id: 'a2', nombre: 'Beto', email: 'beto@y.com' },
  { id: 'a3', nombre: 'Carla', email: 'carla@x.com' },
];
const groups = [{ id: 'g1', members: [{ athlete_id: 'a1' }, { athlete_id: 'a3' }] }];

test('destFilter respeta buscador y grupo (base de "seleccionar visibles")', () => {
  assert.strictEqual(api.destFilter(athletes, { q: '' }, groups).length, 3);
  assert.strictEqual(api.destFilter(athletes, { q: 'x.com' }, groups).length, 2);
  assert.deepStrictEqual(api.destFilter(athletes, { group: 'g1' }, groups).map((u) => u.id), ['a1', 'a3']);
  assert.deepStrictEqual(api.destFilter(athletes, { q: 'carla', group: 'g1' }, groups).map((u) => u.id), ['a3']);
  assert.strictEqual(api.destFilter(athletes, { q: 'beto', group: 'g1' }, groups).length, 0);
});

test('destUnion y destWithout: sin duplicados y conservando orden', () => {
  assert.deepStrictEqual(api.destUnion(['a1'], ['a3', 'a1', 'a2']), ['a1', 'a3', 'a2']);
  assert.deepStrictEqual(api.destWithout(['a1', 'a2', 'a3'], ['a2']), ['a1', 'a3']);
});

test('destChunk trocea 60 en trozos de 25 y 1200 en 500/500/200 sin perder ni repetir', () => {
  const ids60 = Array.from({ length: 60 }, (_, i) => 'u' + i);
  assert.deepStrictEqual(api.destChunk(ids60, 25).map((c) => c.length), [25, 25, 10]);
  assert.deepStrictEqual(api.destChunk(ids60, 25).flat(), ids60);
  const big = Array.from({ length: 1200 }, (_, i) => 'u' + i);
  assert.deepStrictEqual(api.destChunk(big, 500).map((c) => c.length), [500, 500, 200]);
});

test('destSummary lista los primeros y cuenta el resto', () => {
  const nameOf = (id) => id.toUpperCase();
  assert.strictEqual(api.destSummary(['a', 'b'], nameOf, 6), 'A, B');
  assert.strictEqual(api.destSummary(['a', 'b', 'c', 'd'], nameOf, 2), 'A, B y 2 más');
});

test('destBatchItems arma un ítem por atleta', () => {
  const it = api.destBatchItems(['a1', 'a2'], 't1', '2026-11-10', 'n');
  assert.deepStrictEqual(it, [
    { template_id: 't1', athlete_id: 'a1', date_iso: '2026-11-10', notas: 'n' },
    { template_id: 't1', athlete_id: 'a2', date_iso: '2026-11-10', notas: 'n' },
  ]);
});

test('destBatchReport: parcial por atleta, trozo caído y silencio del servidor = fallo', () => {
  const rep = api.destBatchReport([
    { ids: ['a1', 'a2', 'a3'], resp: { detail: { created: [{ index: 0, id: 'w1' }, { index: 2, id: 'w3' }], errors: [{ index: 1, reason: 'El atleta no pertenece a este coach' }] } } },
    { ids: ['b1', 'b2'], error: 'timeout' },
    { ids: ['c1'], resp: { detail: { created: [], errors: [] } } },
  ]);
  assert.deepStrictEqual(rep.ok.map((o) => o.id), ['a1', 'a3']);
  assert.strictEqual(rep.ok[0].assign_id, 'w1');
  assert.deepStrictEqual(rep.failed.map((f) => f.id), ['a2', 'b1', 'b2', 'c1']);
  assert.strictEqual(rep.failed[0].reason, 'El atleta no pertenece a este coach');
  assert.strictEqual(rep.failed[3].reason, 'Sin confirmación del servidor');
});

test('destApplyReport lee results[] por atleta y marca los ausentes como fallo', () => {
  const rep = api.destApplyReport([
    { ids: ['a1', 'a2', 'a3'], resp: { results: [
      { athlete_id: 'a1', ok: true, created: 3 },
      { athlete_id: 'a2', ok: false, created: 0, error: 'ajeno' },
    ] } },
  ]);
  assert.deepStrictEqual(rep.ok, [{ id: 'a1', created: 3 }]);
  assert.deepStrictEqual(rep.failed.map((f) => f.id), ['a2', 'a3']);
});

test('destReportHtml nunca dice éxito global si hay fallos, y escapa nombres', () => {
  const html = api.destReportHtml(
    { ok: [{ id: 'a1' }], failed: [{ id: 'a2', reason: 'ajeno' }] },
    (id) => (id === 'a2' ? '<b>Beto' : id), 'sesiones');
  assert.match(html, /class="bad"/);
  assert.match(html, /1 de 2 atletas/);
  assert.match(html, /&lt;b>Beto — ajeno/);
  assert.doesNotMatch(html, /class="ok"/);
  assert.match(api.destReportHtml({ ok: [{ id: 'a1' }], failed: [] }, (x) => x), /class="ok"/);
});

test('destErrMsg extrae el mensaje del envelope de error', () => {
  assert.strictEqual(api.destErrMsg(new Error('{"ok":false,"errors":[{"message":"boom"}]}')), 'boom');
  assert.strictEqual(api.destErrMsg(new Error('{"detail":"mal"}')), 'mal');
  assert.strictEqual(api.destErrMsg(new Error('texto')), 'texto');
});

test('los tres flujos montan el selector y ya no usan los selects de un solo atleta', () => {
  for (const pfx of ['asgn', 'wta', 'mca']) {
    assert.ok(src.includes('id="' + pfx + '-dest"'), pfx + ' sin contenedor');
    assert.ok(!src.includes('id="' + pfx + '-athlete"'), pfx + ' conserva select singular');
  }
  assert.ok(src.includes("'/coach/assign/batch'"));
  assert.ok(src.includes('athlete_ids: parts[i]'));
});
