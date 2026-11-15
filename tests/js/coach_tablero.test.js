// COACH-TABLERO: el Tablero pide los endpoints reales y renderiza sin inventar cifras.
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

const NAMES = ['tbFmt', 'tbNum', 'tbStatus', 'tbRisk', 'tbPill', 'tbPct', 'tbAlertsCell', 'tbRow', 'tbHead',
  'tbBoard', 'tbSummary', 'tbSquad', 'tbIntel', 'tbGet', 'tbLoadGroups', 'tbLoad', 'tbOpen', 'tbCloseDrill'];
const esc = (s) => (s == null ? '' : String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'));
const _t = (k, fb) => fb;

function build(env) {
  const code = 'var _tbGroupsLoaded = false;\n' + NAMES.map(extract).join('\n') +
    '\nreturn {' + NAMES.join(',') + '};';
  return new Function('esc', '_t', 'API', 'fetch', 'localStorage', 'document', code)(
    esc, _t, '/api', env.fetch, { getItem: () => 'tok' }, env.document);
}

const fakeEl = () => ({ innerHTML: '', value: '', style: {}, children: [], appendChild(c) { this.children.push(c); } });
function fakeDoc() {
  const els = {};
  ['tb-board', 'tb-squad', 'tb-summary', 'tb-group', 'tb-drill'].forEach((id) => (els[id] = fakeEl()));
  return { els, getElementById: (id) => els[id], createElement: () => ({}) };
}

const ROW_FULL = {
  athlete_id: 'u1', nombre: 'Ana <b>', email: 'a@x.com', status: 'critical', ctl: 55.5, atl: 60, tsb: -4.5,
  acwr: 1.6, readiness: 41, hrv: 62, body_battery: 30, injury_risk: 0.7, days_to_race: 0,
  compliance_pct: 0, alerts: [{ title: 'HRV baja', severity: 'warning', type: 'low_hrv' }],
};
const ROW_EMPTY = {
  athlete_id: 'u2', nombre: 'Beto', email: 'b@x.com', status: 'unknown', ctl: null, atl: null, tsb: null,
  acwr: null, readiness: null, hrv: null, body_battery: null, injury_risk: null, days_to_race: null,
  compliance_pct: null, alerts: [],
};

test('estado en palabras, no solo el codigo', () => {
  const a = build({});
  assert.strictEqual(a.tbStatus('optimal').label, 'Bien');
  assert.strictEqual(a.tbStatus('caution').label, 'Atención');
  assert.strictEqual(a.tbStatus('critical').label, 'Cuidado');
  assert.strictEqual(a.tbStatus('unknown').label, 'Sin datos');
  assert.strictEqual(a.tbStatus('raro').label, 'Sin datos');
});

test('null/undefined => Sin datos; el 0 es un dato real', () => {
  const a = build({});
  assert.strictEqual(a.tbNum(null), 'Sin datos');
  assert.strictEqual(a.tbNum(undefined), 'Sin datos');
  assert.strictEqual(a.tbNum(0), '0');
  assert.strictEqual(a.tbNum(0, '%'), '0%');
  assert.strictEqual(a.tbPct(null), 'Sin datos');
  assert.strictEqual(a.tbPct(0.7), '70%');
});

test('fila completa muestra las cifras reales; fila vacia solo Sin datos (nada inventado)', () => {
  const a = build({});
  const full = a.tbRow(ROW_FULL, false) + a.tbRow(ROW_FULL, true);
  assert.ok(full.includes('Cuidado') && full.includes('41') && full.includes('55.5') && full.includes('70%'));
  assert.ok(full.includes('HRV baja'));
  assert.ok(full.includes('&lt;b&gt;'), 'el nombre se escapa');
  const empty = a.tbRow(ROW_EMPTY, false) + a.tbRow(ROW_EMPTY, true);
  assert.ok(!/>\s*0(%|\.0)?\s*</.test(empty), 'sin ceros inventados');
  assert.ok(empty.includes('Sin datos'));
  assert.ok(!/NaN|undefined|null/.test(empty));
});

test('tablero vacio => mensaje honesto; resumen cuenta por estado', () => {
  const a = build({});
  assert.ok(a.tbBoard([]).includes('Sin atletas todavía'));
  assert.strictEqual(a.tbSummary([]), '');
  const s = a.tbSummary([ROW_FULL, ROW_EMPTY, { status: 'optimal' }, { status: 'caution' }]);
  assert.ok(s.includes('4 atletas') && s.includes('1 en Cuidado') && s.includes('1 en Atención'));
});

test('capas: detalle tecnico plegado en <details>, filas clicables', () => {
  const a = build({});
  const h = a.tbBoard([ROW_FULL]);
  assert.ok(h.includes('<details') && h.includes('Ver el detalle técnico'));
  assert.ok(h.includes("tbOpen('u1')"));
});

test('squad-overview: respeta el orden del backend y no inventa', () => {
  const a = build({});
  const h = a.tbSquad({ athletes: [
    { athlete_id: 'z', name: 'Zeta', risk: 'critical', ctl: null, acwr: 1.7, recovery_score: 0, mental_score: null,
      compliance_pct: null, days_to_race: null, blood_critical: true, rx_missed: 2 },
    { athlete_id: 'y', name: 'Yara', risk: 'ok', ctl: 40 },
  ] });
  assert.ok(h.indexOf('Zeta') < h.indexOf('Yara'));
  assert.ok(h.includes('Cuidado') && h.includes('Bien') && h.includes('Sin datos'));
  assert.ok(h.includes('Laboratorio con valores críticos'));
  assert.ok(a.tbSquad({ athletes: [] }).includes('Sin atletas todavía'));
});

test('drill-down 360: renderiza el snapshot y rotula lo ausente', () => {
  const a = build({});
  const h = a.tbIntel({
    athlete_name: 'Ana', training: { ctl: 50, atl: 55, tsb: -5, acwr: 1.1, tss_7d: 0, tss_28d: 300 },
    recovery: { latest_score: null, avg_7d: null }, mental: {}, blood_labs: { has_labs: false },
    prescriptions: { pending_count: 0 }, alerts: [],
  });
  assert.ok(h.includes('Vista 360° de Ana') && h.includes('Sin exámenes cargados') && h.includes('Sin alertas'));
  assert.ok(h.includes('Sin datos'));
  assert.ok(!/NaN|undefined|null/.test(h));
});

test('tbLoad pide status-board y squad-overview; el filtro por grupo va en ?group_id= y recorta el squad', async () => {
  const calls = [];
  const doc = fakeDoc();
  const fetch = async (url) => {
    calls.push(url);
    const body = url.includes('/coach/groups') ? [{ id: 'g1', nombre: 'Elite' }]
      : url.includes('status-board') ? [ROW_FULL]
      : { athletes: [{ athlete_id: 'u1', name: 'Ana', risk: 'critical' }, { athlete_id: 'otro', name: 'Fuera', risk: 'ok' }] };
    return { ok: true, json: async () => body };
  };
  const a = build({ fetch, document: doc });
  await a.tbLoad();
  assert.ok(calls.some((u) => u === '/api/coach/status-board'));
  assert.ok(calls.some((u) => u === '/api/coach/squad-overview'));
  assert.ok(doc.els['tb-board'].innerHTML.includes('Cuidado'));
  assert.strictEqual(doc.els['tb-group'].children.length, 1);
  doc.els['tb-group'].value = 'g1';
  await a.tbLoad();
  assert.ok(calls.some((u) => u === '/api/coach/status-board?group_id=g1'));
  assert.ok(doc.els['tb-squad'].innerHTML.includes('Ana') && !doc.els['tb-squad'].innerHTML.includes('Fuera'));
});

test('tbLoad con error de red => mensaje, sin cifras', async () => {
  const doc = fakeDoc();
  const fetch = async () => ({ ok: false, status: 500, json: async () => ({}) });
  const a = build({ fetch, document: doc });
  await a.tbLoad();
  assert.ok(doc.els['tb-board'].innerHTML.includes('No se pudo cargar'));
});

test('tbOpen pide /athletes/{id}/intelligence', async () => {
  const calls = [];
  const doc = fakeDoc();
  const fetch = async (url) => {
    calls.push(url);
    return { ok: true, json: async () => ({ athlete_name: 'Ana', training: {}, alerts: [] }) };
  };
  const a = build({ fetch, document: doc });
  await a.tbOpen('u1');
  assert.deepStrictEqual(calls, ['/api/coach/athletes/u1/intelligence']);
  assert.ok(doc.els['tb-drill'].innerHTML.includes('Vista 360° de Ana'));
  a.tbCloseDrill();
  assert.strictEqual(doc.els['tb-drill'].style.display, 'none');
});

test('UI aditiva: pestanas previas intactas y reglas dentro del panel de alertas', () => {
  for (const t of ['overview', 'athletes', 'groups', 'workouts', 'mi-atleta', 'assign', 'plan', 'adherence', 'gantt', 'report', 'adp-coach', 'rec-coach', 'tablero']) {
    assert.ok(src.includes('data-tab="' + t + '"'), t);
  }
  const panel = src.slice(src.indexOf('id="alert-panel"'), src.indexOf('id="sb-overlay"'));
  assert.ok(panel.includes('id="alert-list"') && panel.includes('id="alert-rules"') && panel.includes('saveAlertRules'));
  assert.ok(src.includes("'/coach/alert-rules'") && src.includes('/coach/alerts'));
});
