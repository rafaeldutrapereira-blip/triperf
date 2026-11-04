// CQ3 — estimador de TSS unico (lx-tss.js).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { estimate } = require('../../lx-tss.js');

const ROOT = path.join(__dirname, '..', '..');
const run = { sport: 'run', dur_min: 60, avg_hr: 150, date_iso: '2026-11-03' };
const ctx = { ftp: 250, fcmax: 190 };

test('sin FTP/FCmax/FC devuelve null (no 0)', () => {
  assert.equal(estimate(run, {}), null);
  assert.equal(estimate({ sport: 'run', dur_min: 60, date_iso: 'x' }, ctx), null);
  assert.equal(estimate({ sport: 'bike', dur_min: 60, avg_power: 200 }, {}), null);
  assert.equal(estimate({ sport: 'other', dur_min: 60 }, ctx), null);
});

test('con datos da un valor concreto y estable', () => {
  const v = estimate(run, ctx);
  assert.equal(v, Math.round(1 * Math.pow(150 / (0.89 * 190), 2) * 100));
  assert.equal(estimate({ sport: 'bike', dur_min: 60, avg_power: 250 }, ctx), 100);
});

test('el TSS del servidor manda sobre el estimado', () => {
  assert.equal(estimate({ ...run, tss: 77.4 }, {}), 77);
});

test('fuerza sin RPE => null; con RPE => sRPE', () => {
  const s = { sport: 'gym', dur_min: 60, date_iso: '2026-11-03' };
  assert.equal(estimate(s, ctx), null);
  assert.equal(estimate({ ...s, sport: 'strength' }, ctx), null);
  assert.equal(estimate(s, { ...ctx, rpeByDate: { '2026-11-03': 7 } }), 70);
});

test('las 3 paginas cargan el helper y usan LXTss', () => {
  for (const f of ['dashboard.html', 'training_plan.html', 'detalle.html']) {
    const h = fs.readFileSync(path.join(ROOT, f), 'utf8');
    assert.match(h, /<script src="lx-tss\.js\?v=1"><\/script>/, f);
    assert.match(h, /window\.LXTss\.estimate\(/, f);
  }
});

test('sin valores por defecto inventados en los estimadores', () => {
  for (const f of ['dashboard.html', 'training_plan.html', 'detalle.html', 'lx-tss.js']) {
    const h = fs.readFileSync(path.join(ROOT, f), 'utf8');
    assert.doesNotMatch(h, /_athleteFTP\s*\|\|\s*240/, f);
    assert.doesNotMatch(h, /_athleteFCMax\s*\|\|\s*180/, f);
    assert.doesNotMatch(h, /profile\.ftp\s*\|\|\s*240|profile\.fcmax\s*\|\|\s*180/, f);
    assert.doesNotMatch(h, /return Math\.round\(h \* 50\)/, f);
    assert.doesNotMatch(h, /avg_hr \|\| (120|140|110)/, f);
  }
});
