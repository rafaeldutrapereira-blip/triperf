// CQ7 -- Mi Plan propio en servidor: lx-ownplan.js con un servidor falso en memoria.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { create } = require('../../lx-ownplan.js');

const ROOT = path.join(__dirname, '..', '..');

function makeEnv({ local = {}, server = [], failWrites = false } = {}) {
  const store = Object.assign({ lx_co_token: 'tok', kl_s: JSON.stringify({ user_id: 7 }) }, local);
  const srv = { sessions: server.slice(), calls: [], n: 100 };
  const env = {
    storage: {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = String(v); },
    },
    api: 'https://x.test/api',
    fetch: (url, opts) => {
      const p = url.replace('https://x.test/api/athlete/own-plan', '');
      const m = opts.method;
      const body = opts.body ? JSON.parse(opts.body) : null;
      srv.calls.push(m + ' ' + (p || '/'));
      const ok = (j) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(j) });
      if (failWrites && m !== 'GET') return Promise.resolve({ ok: false, status: 500, json: () => ({}) });
      if (m === 'GET') return ok({ sessions: srv.sessions });
      if (p === '/import') {
        let created = 0;
        body.sessions.forEach((s) => {
          if (s.api_assignment_id) return;
          if (srv.sessions.some((x) => x.legacy_id === s.id)) return;
          srv.sessions.push(Object.assign({}, s, { id: 'srv' + srv.n++, legacy_id: s.id }));
          created++;
        });
        return ok({ created, sessions: srv.sessions });
      }
      if (m === 'POST') {
        const dup = body.indoor_workout_id && srv.sessions.find((x) => x.indoor_workout_id === body.indoor_workout_id && x.date_iso === body.date_iso);
        if (dup) return ok(Object.assign({}, dup, { duplicate: true }));
        const s = Object.assign({}, body, { id: 'srv' + srv.n++ });
        srv.sessions.push(s);
        return ok(Object.assign({}, s, { duplicate: false }));
      }
      const id = decodeURIComponent(p.slice(1));
      if (m === 'PUT') {
        const s = srv.sessions.find((x) => x.id === id);
        Object.assign(s, body);
        return ok(s);
      }
      srv.sessions = srv.sessions.filter((x) => x.id !== id);
      return ok({ ok: true });
    },
  };
  return { api: create(env), store, srv };
}

const L = (id, extra) => Object.assign({ id, sport: 'run', name: 'Rodaje', date_iso: '2026-11-05', dur_min: 45 }, extra);

test('migracion: sube las locales una vez, sin las del coach, y las retira de localStorage', async () => {
  const local = [L('plan-1'), L('plan-2', { name: 'Fondo' }), L('api_9', { api_assignment_id: 9 })];
  const { api, store, srv } = makeEnv({ local: { kl_training_plan: JSON.stringify(local), kl_training_plan_owner: '7' } });
  const out = await api.load();
  assert.equal(out.length, 2);
  assert.equal(srv.sessions.length, 2);
  assert.deepEqual(JSON.parse(store.kl_training_plan).map((s) => s.id), ['api_9']); // solo cache del coach
  assert.equal(store['kl_own_plan_migrated:7'], '1');
  // segundo inicio: no vuelve a importar
  const before = srv.calls.filter((c) => c === 'POST /import').length;
  const api2 = create({ storage: { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } }, api: 'https://x.test/api', fetch: (u, o) => { srv.calls.push(o.method + ' ' + u.slice(-7)); return Promise.resolve({ ok: true, json: () => ({ sessions: srv.sessions }) }); } });
  await api2.load();
  assert.equal(before, 1);
  assert.equal(srv.calls.filter((c) => c.includes('import')).length, 1);
  assert.equal(srv.sessions.length, 2);
});

test('si el servidor falla, se siguen viendo las locales y no se pierden', async () => {
  const { api, store } = makeEnv({ local: { kl_training_plan: JSON.stringify([L('plan-1')]), kl_training_plan_owner: '7' } });
  api.onError = () => {};
  const env2 = makeEnv({ local: { kl_training_plan: JSON.stringify([L('plan-1')]), kl_training_plan_owner: '7' } });
  env2.api; // sin uso: el fallo se simula con fetch rechazado abajo
  const failing = create({ storage: { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } }, fetch: () => Promise.reject(new Error('red')), api: 'x' });
  failing.onError = () => {};
  const out = await failing.load();
  assert.equal(out.length, 1);
  assert.equal(JSON.parse(store.kl_training_plan).length, 1); // intacto
  assert.ok(!store['kl_own_plan_migrated:7']);
});

test('sync: crear, editar y borrar viajan al servidor; el id temporal pasa al del servidor', async () => {
  const { api, srv } = makeEnv({ local: { 'kl_own_plan_migrated:7': '1' } });
  await api.load();
  assert.equal(await api.sync([L('plan-9')]), true);
  assert.equal(srv.sessions.length, 1);
  assert.equal(srv.sessions[0].legacy_id, 'plan-9');
  const sid = srv.sessions[0].id;
  assert.equal(api.cached()[0].id, sid);
  await api.sync([Object.assign({}, api.cached()[0], { date_iso: '2026-11-08' })]);
  assert.equal(srv.sessions[0].date_iso, '2026-11-08');
  await api.sync([]);
  assert.equal(srv.sessions.length, 0);
});

test('editar antes de que responda el alta usa el id del servidor', async () => {
  const { api, srv } = makeEnv({ local: { 'kl_own_plan_migrated:7': '1' } });
  await api.load();
  const p1 = api.sync([L('plan-7')]);
  const p2 = api.sync([L('plan-7', { name: 'Editado' })]); // aun con id temporal
  await Promise.all([p1, p2]);
  assert.equal(srv.sessions.length, 1);
  assert.equal(srv.sessions[0].name, 'Editado');
});

test('write fallido: avisa, recarga del servidor y no deja la sesion fantasma', async () => {
  const { api, srv } = makeEnv({ local: { 'kl_own_plan_migrated:7': '1' }, failWrites: true });
  let err = null;
  api.onError = (e) => { err = e; };
  await api.load();
  assert.equal(await api.sync([L('plan-1')]), false);
  assert.ok(err);
  assert.equal(api.cached().length, 0);
  assert.equal(srv.sessions.length, 0);
});

test('add (Indoor + Mi Plan) escribe en servidor y no duplica el mismo workout/dia', async () => {
  const { api, srv } = makeEnv({ local: { 'kl_own_plan_migrated:7': '1' } });
  const body = { sport: 'bike', name: 'SS', date_iso: '2026-11-05', indoor_workout_id: 'iw1' };
  const a = await api.add(body);
  const b = await api.add(body);
  assert.equal(a.duplicate, false);
  assert.equal(b.duplicate, true);
  assert.equal(srv.sessions.length, 1);
  assert.equal(api.cached().length, 1);
});

test('las paginas leen del servidor y localStorage no es fuente', () => {
  const dash = fs.readFileSync(path.join(ROOT, 'dashboard.html'), 'utf8');
  const tp = fs.readFileSync(path.join(ROOT, 'training_plan.html'), 'utf8');
  const iw = fs.readFileSync(path.join(ROOT, 'indoor_workout.html'), 'utf8');
  for (const h of [dash, tp, iw]) assert.match(h, /lx-ownplan\.js\?v=2/);
  assert.doesNotMatch(dash, /localStorage\.getItem\('kl_training_plan'\)/);
  assert.doesNotMatch(iw, /kl_training_plan/);
  assert.match(iw, /LXOwnPlan\.add\(/);
  assert.match(tp, /LXOwnPlan\.sync\(/);
  assert.match(tp, /LXOwnPlan\.load\(\)/);
});

test('dashboard: suma propio + Garmin/coach sin duplicar', () => {
  const dash = fs.readFileSync(path.join(ROOT, 'dashboard.html'), 'utf8');
  const m = dash.match(/function mergeToday\(ext, own\) \{[\s\S]*?\r?\n        \}\r?\n/);
  assert.ok(m, 'mergeToday no encontrada');
  const mergeToday = new Function(m[0] + '; return mergeToday;')();
  const g = { src: 'garmin', sport: 'bike', name: 'Sweet Spot' };
  const dupOwn = { src: 'own', sport: 'bike', name: ' sweet spot ' };
  const other = { src: 'own', sport: 'run', name: 'Rodaje' };
  const out = mergeToday([g], [dupOwn, other]);
  assert.deepEqual(out.map((x) => x.src), ['garmin', 'own']);
  assert.equal(out[1].name, 'Rodaje');
});

// ---- CQ13: la importacion del plan local es por usuario ----
const sess = (id) => JSON.stringify({ user_id: id });
const imports = (srv) => srv.calls.filter((c) => c === 'POST /import').length;

test('CQ13: misma cuenta importa una vez, con marca por usuario y sin duplicar', async () => {
  const local = { kl_training_plan: JSON.stringify([L('plan-1')]), kl_training_plan_owner: '7' };
  const { api, store, srv } = makeEnv({ local });
  await api.load();
  assert.equal(imports(srv), 1);
  assert.equal(srv.sessions.length, 1);
  assert.equal(store['kl_own_plan_migrated:7'], '1');
  assert.ok(!store.kl_training_plan_owner);
  await api.load();
  assert.equal(imports(srv), 1);
  assert.equal(srv.sessions.length, 1);
});

test('CQ13: cuenta distinta no importa ni borra el plan local, y ve el del servidor', async () => {
  const local = { kl_s: sess(8), kl_training_plan: JSON.stringify([L('plan-1')]), kl_training_plan_owner: '7' };
  const { api, store, srv } = makeEnv({ local, server: [{ id: 'srvA', name: 'De B', date_iso: '2026-11-06' }] });
  const logs = [];
  const orig = console.info;
  console.info = (m) => logs.push(m);
  let out;
  try { out = await api.load(); } finally { console.info = orig; }
  assert.equal(imports(srv), 0);
  assert.deepEqual(out.map((s) => s.id), ['srvA']);
  assert.equal(JSON.parse(store.kl_training_plan).length, 1);
  assert.equal(store.kl_training_plan_owner, '7');
  assert.ok(!store['kl_own_plan_migrated:8']);
  assert.ok(logs.some((m) => /LXOwnPlan/.test(m)));
});

test('CQ13: plan local sin duenio conocido no se atribuye a nadie', async () => {
  const { api, store, srv } = makeEnv({ local: { kl_training_plan: JSON.stringify([L('plan-1')]) } });
  await api.load();
  assert.equal(imports(srv), 0);
  assert.equal(JSON.parse(store.kl_training_plan).length, 1);
});

test('CQ13: sin sesion no importa ni marca nada', async () => {
  const { api, store, srv } = makeEnv({ local: { kl_s: null, kl_training_plan: JSON.stringify([L('plan-1')]), kl_training_plan_owner: '7' } });
  await api.load();
  assert.equal(imports(srv), 0);
  assert.equal(JSON.parse(store.kl_training_plan).length, 1);
  assert.ok(!Object.keys(store).some((k) => k.startsWith('kl_own_plan_migrated')));
});

test('CQ13: la marca de una cuenta no cuenta para otra en el mismo navegador', async () => {
  const { api, store } = makeEnv({ local: { kl_s: sess(8), 'kl_own_plan_migrated:7': '1' } });
  await api.load();
  assert.equal(store['kl_own_plan_migrated:8'], '1');
  assert.equal(store['kl_own_plan_migrated:7'], '1');
});
