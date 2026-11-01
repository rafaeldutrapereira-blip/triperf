// S3 (2026-11-01) — registro de sesión en un gesto en Mi Plan.
// El código vive en un <script> inline de training_plan.html; se extrae el
// bloque "REGISTRO DE SESIÓN (S3)" y se ejecuta en un sandbox con mocks.
// Ejecutar: node --test tests/js/plan_log_s3.test.js
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const HTML = fs.readFileSync(path.join(__dirname, '..', '..', 'training_plan.html'), 'utf8');
const START = HTML.indexOf('REGISTRO DE SESIÓN (S3)');
const END = HTML.indexOf('COACH API INTEGRATION');
assert.ok(START > 0 && END > START, 'bloque S3 no encontrado');
const BLOCK = HTML.slice(START, END);

function setup({ plan, fetchImpl, token = 'tok' }) {
  const store = { kl_training_plan: JSON.stringify(plan) };
  if (token) store.lx_co_token = token;
  const fetchCalls = [];
  const closed = [];
  let renders = 0;
  const toasts = [];
  const els = {};
  const el = (id) => (els[id] = els[id] || { style: {}, textContent: '', value: '', classList: { add() {} } });
  const win = { location: { protocol: 'https:', origin: 'https://x.test' } };
  const ctx = {
    window: win,
    localStorage: {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = v; },
    },
    document: { getElementById: el, addEventListener() {} },
    setTimeout: () => 0,
    Promise, JSON, Math, parseInt, parseFloat, Error,
    fetch: (url, opts) => { fetchCalls.push({ url, body: JSON.parse(opts.body) }); return fetchImpl(url, opts); },
    getPlanned: () => JSON.parse(store.kl_training_plan || '[]'),
    savePlanned: (a) => { store.kl_training_plan = JSON.stringify(a); },
    closeModal: (id) => closed.push(id),
    render: () => { renders++; },
    _t: (k, fb) => fb,
    rpeLabels: undefined,
  };
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  // El bloque incluye rpeLabels/RPE_COLORS con _t y "var"; se envuelve en función.
  vm.runInContext('(function(){' + BLOCK.slice(BLOCK.indexOf('\n')) + '\n})()', ctx);
  return {
    win, fetchCalls, closed, els,
    status: (id) => JSON.parse(store.kl_training_plan).find((p) => p.id === id),
    renders: () => renders,
    toast: () => els['t-rs-msg'] && els['t-rs-msg'].textContent,
  };
}

const PLAN = () => [
  { id: 'api_7', api_assignment_id: 7, name: 'Bici', dur_min: 90, dist_km: 40, tss: 75, status: 'planned' },
  { id: 'p1', name: 'Rodaje', dur_min: 55, dist_km: 10, tss: 60, status: 'planned' },
];
const ok = () => Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({ id: 1 }) });

test('Hecha: UN POST /athlete/log con los valores del plan y la sesión queda hecha', async () => {
  const t = setup({ plan: PLAN(), fetchImpl: ok });
  const r = await t.win.tpMarkDone('api_7');
  assert.equal(r, true);
  assert.equal(t.fetchCalls.length, 1);
  assert.equal(t.fetchCalls[0].url, 'https://x.test/api/athlete/log');
  assert.deepEqual(t.fetchCalls[0].body, {
    assignment_id: 7, tss_real: 75, dist_real: 40, dur_real: 90,
    rpe: null, notas: null, completado: true,
  });
  const s = t.status('api_7');
  assert.equal(s.status, 'done');
  assert.equal(s.dur_real, 90);
  assert.equal(t.renders(), 1);
});

test('POST con error del servidor: NO se marca hecha y hay aviso', async () => {
  const t = setup({ plan: PLAN(), fetchImpl: () => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) }) });
  const r = await t.win.tpMarkDone('api_7');
  assert.equal(r, false);
  assert.equal(t.status('api_7').status, 'planned');
  assert.equal(t.renders(), 0);
  assert.match(t.toast(), /No se pudo registrar/);
});

test('POST con error de red: NO se marca hecha', async () => {
  const t = setup({ plan: PLAN(), fetchImpl: () => Promise.reject(new Error('net')) });
  assert.equal(await t.win.tpMarkDone('api_7'), false);
  assert.equal(t.status('api_7').status, 'planned');
});

test('sin token una sesión del coach no se marca hecha', async () => {
  const t = setup({ plan: PLAN(), fetchImpl: ok, token: null });
  assert.equal(await t.win.tpMarkDone('api_7'), false);
  assert.equal(t.fetchCalls.length, 0);
  assert.equal(t.status('api_7').status, 'planned');
});

test('sesión local: se marca hecha sin POST (no hay assignment en el servidor)', async () => {
  const t = setup({ plan: PLAN(), fetchImpl: ok });
  assert.equal(await t.win.tpMarkDone('p1'), true);
  assert.equal(t.fetchCalls.length, 0);
  assert.equal(t.status('p1').status, 'done');
});

test('doble toque no duplica el POST', async () => {
  const t = setup({ plan: PLAN(), fetchImpl: ok });
  const a = t.win.tpMarkDone('api_7');
  const b = t.win.tpMarkDone('api_7');
  assert.deepEqual([await a, await b], [true, false]);
  assert.equal(t.fetchCalls.length, 1);
});

test('formulario completo (Editar detalle): precarga el plan y envía lo editado', async () => {
  const t = setup({ plan: PLAN(), fetchImpl: ok });
  t.win.openLogModal('api_7');
  assert.equal(t.els['log-tss'].value, 75);
  assert.equal(t.els['log-dist'].value, 40);
  assert.equal(t.els['log-dur'].value, 90);
  t.els['log-dur'].value = '80';
  t.els['log-tss'].value = '70';
  t.els['log-dist'].value = '38.5';
  t.els['log-rpe'].value = '7';
  t.els['log-notas'].value = ' bien ';
  t.win.submitLog();
  await new Promise((r) => setImmediate(r));
  assert.equal(t.fetchCalls.length, 1);
  assert.deepEqual(t.fetchCalls[0].body, {
    assignment_id: 7, tss_real: 70, dist_real: 38.5, dur_real: 80,
    rpe: 7, notas: 'bien', completado: true,
  });
  assert.equal(t.status('api_7').status, 'done');
});

test('el botón y las claves i18n existen en ES/PT/EN', () => {
  assert.match(HTML, /tpMarkDone\(/);
  assert.match(HTML, /tp_edit_detail/);
  const i18n = fs.readFileSync(path.join(__dirname, '..', '..', 'i18n.js'), 'utf8');
  for (const k of ['tp_done_btn', 'tp_edit_detail', 'tp_log_ok', 'tp_log_fail']) {
    assert.equal((i18n.match(new RegExp('\\b' + k + ':', 'g')) || []).length, 3, k);
  }
});
