// PROGRAMAS (383): la seccion lista, detalla, crea y asigna contra los endpoints reales de
// /coach/templates, sin inventar datos y escapando HTML.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const src = fs.readFileSync(path.join(__dirname, '..', '..', 'coach.html'), 'utf8');

function extract(name) {
  const re = new RegExp('(async )?function ' + name + '\\(');
  const m = re.exec(src);
  assert.ok(m, name + ' no existe');
  const i = m.index;
  const j = src.indexOf('{', src.indexOf(')', i));
  let depth = 0;
  for (let k = j; k < src.length; k++) {
    if (src[k] === '{') depth++;
    else if (src[k] === '}' && --depth === 0) return src.slice(i, k + 1);
  }
  throw new Error('sin cierre ' + name);
}

const NAMES = ['pgFmt', 'pgSport', 'pgPhase', 'pgDiff', 'pgDist', 'pgNum', 'pgReq', 'pgParseSessions',
  'pgSessionsToText', 'pgSessionLine', 'pgRenderList', 'pgRenderDetail', 'pgLoad', 'pgOpen', 'pgClose',
  'pgNextMonday', 'pgIsMonday', 'pgOpenAssign', 'pgAssignSummary', 'pgSubmitAssign', 'pgToast'];
const esc = (s) => (s == null ? '' : String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'));
const _t = (k, fb) => fb;

function build(env) {
  const code =
    "var _pgList=[],_pgCur=null,_pgAssignId=null,_pgEditId=null;\n" +
    "var _pgSessSports=['swim','bike','run','str','brick'];\n" +
    NAMES.map(extract).join('\n') +
    '\nreturn {' + NAMES.join(',') + ', set:(k,v)=>{ if(k==="cur")_pgCur=v; if(k==="assign")_pgAssignId=v; }, get:()=>({list:_pgList,cur:_pgCur}) };';
  return new Function('esc', '_t', 'API', 'fetch', 'localStorage', 'document', 'openModal', 'closeModal',
    'switchTab', 'window', 'toast', code)(
    esc, _t, '/api', env.fetch, { getItem: () => 'tok' }, env.document || fakeDoc(), () => {}, () => {}, () => {},
    env.window || {}, () => {});
}

const fakeEl = () => ({ innerHTML: '', textContent: '', value: '', style: {}, disabled: false, children: [],
  appendChild(c) { this.children.push(c); }, selectedOptions: [{ textContent: 'Ana' }] });
function fakeDoc() {
  const els = {};
  ['pg-list', 'pg-d-name', 'pg-d-meta', 'pg-d-desc', 'pg-d-edit', 'pg-d-delete', 'pg-d-weeks', 'pg-list-card',
    'pg-detail', 'pg-as-athlete', 'pg-as-start', 'pg-as-result', 'pg-as-go', 'ap-start', 'ap-end']
    .forEach((id) => (els[id] = fakeEl()));
  return { els, getElementById: (id) => els[id], createElement: () => fakeEl() };
}
const jsonRes = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });

const LIST = [
  { id: 'builtin-703-12w', name: 'Ironman 70.3 — 12 semanas', sport: 'triathlon', distance_type: '70.3', weeks: 12,
    difficulty: 'intermediate', is_public: true, is_builtin: true },
  { id: 'p1', name: 'Mi <b>plan</b>', sport: 'run', distance_type: null, weeks: 4, difficulty: null,
    is_public: false, is_builtin: false },
];

test('la lista muestra integrados y propios con deporte, distancia, semanas, dificultad y compartido', () => {
  const a = build({});
  const h = a.pgRenderList(LIST);
  assert.match(h, /Ironman 70\.3/);
  assert.match(h, /triathlon/); // sin diccionario en el test: cae al codigo
  assert.match(h, /Integrado/);
  assert.match(h, /Propio/);
  assert.match(h, />12</);
  assert.match(h, /intermediate/);
  assert.ok(h.includes('pgOpen(\'builtin-703-12w\')'));
});

test('HTML del usuario escapado y campos vacios sin inventar cifras', () => {
  const a = build({});
  const h = a.pgRenderList(LIST);
  assert.ok(!h.includes('<b>plan</b>'));
  assert.ok(h.includes('&lt;b&gt;plan&lt;/b&gt;'));
  assert.strictEqual(a.pgNum(null), '—');
  assert.strictEqual(a.pgNum(0), '0'); // el 0 es un valor real
  assert.strictEqual(a.pgDist(null), '—');
  assert.strictEqual(a.pgDiff(''), '—');
});

test('el detalle trae semana, fase, TSS objetivo, horas y sesiones', () => {
  const a = build({});
  const h = a.pgRenderDetail({ plan_weeks: [
    { week_num: 1, phase_type: 'base', label: 'Base 1', tss_target: 300, hours_target: 8.5,
      sessions: [{ sport: 'bike', title: 'Rodaje <i>', duration_min: 100, tss: 60, zone: 'Z2' }] },
    { week_num: 2, phase_type: 'taper', tss_target: null, hours_target: null, sessions: [] },
  ] });
  assert.match(h, /Base 1/);
  assert.match(h, />300</);
  assert.match(h, />8\.5</);
  assert.match(h, /100 min/);
  assert.match(h, /Z2/);
  assert.match(h, /TSS 60/);
  assert.ok(h.includes('Rodaje &lt;i&gt;'));
  assert.match(h, /Sin sesiones/);
  assert.match(h, /Carga objetivo \(TSS\)/); // nombre primero + sigla entre parentesis
});

test('parser de sesiones: formato valido, vacios opcionales y linea invalida reportada', () => {
  const a = build({});
  const ok = a.pgParseSessions('bike | Rodaje | 90 | 55 | z2\n\nrun | Suave | | |');
  assert.strictEqual(ok.bad, null);
  assert.deepStrictEqual(ok.sessions[0], { sport: 'bike', title: 'Rodaje', duration_min: 90, tss: 55, zone: 'Z2' });
  assert.deepStrictEqual(ok.sessions[1], { sport: 'run', title: 'Suave' });
  assert.strictEqual(a.pgParseSessions('golf | x').bad, 'golf | x');
  assert.strictEqual(a.pgParseSessions('bike').bad, 'bike');
  assert.strictEqual(a.pgParseSessions('bike | x | abc').bad, 'bike | x | abc');
  const rt = a.pgParseSessions(a.pgSessionsToText(ok.sessions));
  assert.deepStrictEqual(rt.sessions, ok.sessions); // ida y vuelta (duplicar)
});

test('pgLoad pide GET /coach/templates y pinta la lista', async () => {
  const calls = [];
  const doc = fakeDoc();
  const a = build({ document: doc, fetch: async (url, opt) => { calls.push([url, opt.method]); return jsonRes(LIST); } });
  await a.pgLoad();
  assert.deepStrictEqual(calls[0], ['/api/coach/templates', 'GET']);
  assert.match(doc.els['pg-list'].innerHTML, /Mi &lt;b&gt;plan/);
  assert.strictEqual(a.get().list.length, 2);
});

test('pgLoad con error no inventa programas', async () => {
  const doc = fakeDoc();
  const a = build({ document: doc, fetch: async () => jsonRes({ ok: false, errors: [{ message: 'x' }] }, 500) });
  await a.pgLoad();
  assert.match(doc.els['pg-list'].innerHTML, /No se pudieron cargar/);
  assert.ok(!/<table/.test(doc.els['pg-list'].innerHTML));
});

test('pgOpen pide el detalle y oculta editar/eliminar en integrados', async () => {
  const doc = fakeDoc();
  const det = { id: 'builtin-703-12w', name: '70.3', sport: 'triathlon', weeks: 12, is_builtin: true, plan_weeks: [] };
  const a = build({ document: doc, fetch: async (url) => { assert.ok(url.endsWith('/coach/templates/builtin-703-12w')); return jsonRes(det); } });
  await a.pgOpen('builtin-703-12w');
  assert.strictEqual(doc.els['pg-d-edit'].style.display, 'none');
  assert.strictEqual(doc.els['pg-d-delete'].style.display, 'none');
  assert.strictEqual(doc.els['pg-detail'].style.display, '');
  assert.strictEqual(doc.els['pg-list-card'].style.display, 'none');
  a.pgClose();
  assert.strictEqual(doc.els['pg-list-card'].style.display, '');
});

test('lunes: proximo lunes y validacion', () => {
  const a = build({});
  assert.strictEqual(a.pgNextMonday('2026-11-15'), '2026-11-16'); // domingo -> lunes
  assert.strictEqual(a.pgNextMonday('2026-11-16'), '2026-11-16'); // lunes -> hoy
  assert.strictEqual(a.pgNextMonday('2026-11-17'), '2026-11-23');
  assert.ok(a.pgIsMonday('2026-12-07'));
  assert.ok(!a.pgIsMonday('2026-12-08'));
  assert.ok(!a.pgIsMonday(''));
});

test('asignar: valida atleta y lunes antes de llamar; POST con athlete_id + start_date', async () => {
  const doc = fakeDoc();
  let n = 0;
  const posted = [];
  const a = build({ document: doc, window: { openAthletePlan() {}, loadAthletePlan() {} }, fetch: async (url, opt) => {
    n++;
    posted.push([url, opt.method, JSON.parse(opt.body)]);
    return jsonRes({ assigned_created: 44, weeks: 12, start_date: '2026-12-07', end_date: '2027-02-28',
      phases_created: 4, with_structure: 32, without_structure: 12, assignment_ids: [] }, 201);
  } });
  a.set('assign', 'builtin-703-12w');
  doc.els['pg-as-athlete'].value = '';
  await a.pgSubmitAssign();
  assert.strictEqual(n, 0);
  assert.match(doc.els['pg-as-result'].textContent, /Elige un atleta/);
  doc.els['pg-as-athlete'].value = 'u1';
  doc.els['pg-as-start'].value = '2026-12-08';
  await a.pgSubmitAssign();
  assert.strictEqual(n, 0);
  assert.match(doc.els['pg-as-result'].textContent, /lunes/);
  doc.els['pg-as-start'].value = '2026-12-07';
  await a.pgSubmitAssign();
  assert.deepStrictEqual(posted[0], ['/api/coach/templates/builtin-703-12w/assign', 'POST',
    { athlete_id: 'u1', start_date: '2026-12-07' }]);
  const out = doc.els['pg-as-result'].innerHTML;
  assert.match(out, /44 sesiones asignadas en 12 semanas/);
  assert.match(out, /4 fases/);
  assert.match(out, /32 con estructura/);
  assert.match(out, /12 sin estructura/);
  assert.match(out, /Ver plan y estado de envío/);
  assert.ok(!/prescri/i.test(out));
});

test('asignar: solape (409) se explica y no se muestra como exito', async () => {
  const doc = fakeDoc();
  const a = build({ document: doc, fetch: async () => jsonRes(
    { ok: false, errors: [{ code: 'program_overlap', message: 'El atleta ya tiene sesiones...' }] }, 409) });
  a.set('assign', 'builtin-sprint-8w');
  doc.els['pg-as-athlete'].value = 'u1';
  doc.els['pg-as-start'].value = '2026-12-07';
  await a.pgSubmitAssign();
  assert.match(doc.els['pg-as-result'].textContent, /No se asignó nada/);
  assert.strictEqual(doc.els['pg-as-go'].disabled, false);
  assert.ok(!/sesiones asignadas/.test(doc.els['pg-as-result'].innerHTML));
});

test('pgReq: 204 devuelve null y los errores exponen status y code', async () => {
  const ok = build({ fetch: async () => ({ ok: true, status: 204 }) });
  assert.strictEqual(await ok.pgReq('DELETE', '/x'), null);
  const bad = build({ fetch: async () => jsonRes({ errors: [{ code: 'program_overlap', message: 'm' }] }, 409) });
  await assert.rejects(() => bad.pgReq('POST', '/x', {}), (e) => e.status === 409 && e.code === 'program_overlap' && e.message === 'm');
});

test('la seccion es aditiva: pestaña, panel, modales y carga perezosa', () => {
  assert.match(src, /data-tab="programas"/);
  assert.match(src, /id="tab-programas"/);
  assert.match(src, /id="modal-pg-assign"/);
  assert.match(src, /id="modal-pg-edit"/);
  assert.match(src, /if \(name === 'programas'\) pgLoad\(\)/);
  for (const t of ['overview', 'athletes', 'groups', 'workouts', 'mi-atleta', 'assign', 'plan', 'adherence',
    'gantt', 'report', 'adp-coach', 'rec-coach', 'tablero']) {
    assert.ok(src.includes('data-tab="' + t + '"'), t);
  }
});
