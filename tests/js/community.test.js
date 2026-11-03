'use strict';
// CC2: modulo unico de Comunidad (community.js). Sin DOM: contenedor falso + fetch inyectado.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const C = require('../../community.js');

const ROOT = path.join(__dirname, '..', '..');
const SRC = fs.readFileSync(path.join(ROOT, 'community.js'), 'utf8');
const I18N = fs.readFileSync(path.join(ROOT, 'i18n.js'), 'utf8');

const EVIL = '<img src=x onerror=alert(1)>';

function fakeContainer() {
  const h = {};
  return {
    innerHTML: '',
    addEventListener(t, fn) { h[t] = fn; },
    removeEventListener() {},
    _h: h,
  };
}

function fakeFetch(calls) {
  return async (url, init) => {
    calls.push({ url, method: (init && init.method) || 'GET' });
    const j = (body, ok = true, status = 200) => ({ ok, status, json: async () => body });
    if (url.includes('/community/activity-feed')) {
      return j({ feed: [card()], has_more: false, next_offset: null, following_count: 1 });
    }
    if (url.includes('/community/suggestions')) return j([{ user_id: 'u9', nombre: EVIL, reason: 'x' }]);
    if (url.includes('/community/leaderboard')) {
      return j({ leaderboard: [{ rank: 1, value: 120, is_me: true, hours_week: 4, user: { id: 'u1', name: EVIL } }] });
    }
    if (url.includes('/community/groups')) {
      return j({ items: [{ id: 'g1', name: EVIL, sport: 'running', n_members: 3, is_member: false, is_private: false, owner_id: 'o' }] });
    }
    return j({});
  };
}

function card(over) {
  return Object.assign({
    id: 'p1', activity_id: 'a1', kudo_count: 2, my_kudo: null, n_comments: 1,
    caption: EVIL, user: { id: 'u2', name: EVIL, avatar_initial: 'X' },
    sport: 'run', sport_emoji: '🏃', name: EVIL, date_iso: '2026-11-01',
    distance_km: 10.2, duration_min: 55, tss: 70, avg_hr: 150,
    route_preview: [[-34.6, -58.4], [-34.61, -58.41], [-34.62, -58.4]],
    photos: [
      { url: 'javascript:alert(1)', photo_id: null, deletable: false },
      { url: '/api/athlete/activities/a1/photos/9', photo_id: '9', deletable: true },
    ],
    can_add_photos: true,
  }, over || {});
}

test('esc() neutraliza HTML y comillas', () => {
  assert.equal(C.esc(EVIL), '&lt;img src=x onerror=alert(1)&gt;');
  assert.equal(C.esc('"a\'b"'), '&quot;a&#39;b&quot;');
  assert.equal(C.esc(null), '');
});

test('tarjeta: nombre, titulo y caption con HTML salen escapados (sin <img> inyectado)', () => {
  const html = C.cardHtml(card(), { t: (k, f) => f, canWrite: true });
  assert.ok(!html.includes('<img src=x'), 'no debe haber HTML de usuario sin escapar');
  assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;'));
  assert.ok(!/src="javascript:/i.test(html), 'urls javascript: descartadas');
  assert.ok(html.includes('<svg'), 'mini-mapa SVG presente');
  assert.ok(html.includes('data-act="open-activity"'), 'toque abre detalle por callback');
  assert.ok(html.includes('data-act="kudo"'));
});

test('tarjeta en modo lectura: sin kudo, sin fotos nuevas, sin borrar foto', () => {
  const html = C.cardHtml(card(), { t: (k, f) => f, canWrite: false });
  assert.ok(!html.includes('data-act="kudo"'));
  assert.ok(!html.includes('photo-file'));
  assert.ok(!html.includes('photo-del'));
  assert.ok(html.includes('lxc-act ro'), 'conserva el conteo de fuegos');
});

test('safeUrl solo admite http(s) y rutas del mismo origen', () => {
  assert.equal(C.safeUrl('https://x.com/a.jpg'), 'https://x.com/a.jpg');
  assert.equal(C.safeUrl('/api/x'), '/api/x');
  assert.equal(C.safeUrl('//evil.com/x'), '');
  assert.equal(C.safeUrl('javascript:alert(1)'), '');
  assert.equal(C.safeUrl('data:text/html,x'), '');
});

for (const view of ['feed', 'ranking', 'clubs']) {
  test(`la vista ${view} monta, pide su endpoint y escapa nombres de usuario`, async () => {
    const calls = [];
    const el = fakeContainer();
    const ctl = C.mount(el, { view, canWrite: true, fetch: fakeFetch(calls), getToken: () => 't' });
    await ctl.ready;
    assert.ok(el.innerHTML.includes('data-view="' + view + '"'));
    assert.ok(!el.innerHTML.includes('<img src=x'), 'sin HTML inyectado');
    const urls = calls.map((c) => c.url).join(' ');
    if (view === 'feed') assert.match(urls, /\/community\/activity-feed\?limit=10&offset=0/);
    if (view === 'ranking') assert.match(urls, /\/community\/leaderboard\?metric=tss/);
    if (view === 'clubs') assert.match(urls, /\/community\/groups\?mine=true/);
    ctl.destroy();
  });
}

test('feed: sugerencias "A quien seguir" al final del feed, escapadas, sin pestana extra', async () => {
  const el = fakeContainer();
  const ctl = C.mount(el, { view: 'feed', canWrite: true, fetch: fakeFetch([]), getToken: () => 't' });
  await ctl.ready;
  assert.ok(el.innerHTML.includes('data-lxc="suggestions"'));
  assert.ok(el.innerHTML.includes('data-act="search-toggle"'));
  assert.equal((el.innerHTML.match(/data-act="tab"/g) || []).length, 3, 'solo 3 pestanas');
});

test('toque en la tarjeta dispara onOpenActivity con la tarjeta', async () => {
  const el = fakeContainer();
  let got = null;
  const ctl = C.mount(el, { view: 'feed', canWrite: true, fetch: fakeFetch([]), getToken: () => 't', onOpenActivity: (c) => { got = c; } });
  await ctl.ready;
  const node = { getAttribute: (k) => ({ 'data-act': 'open-activity', 'data-id': 'p1' }[k]) };
  el._h.click({ target: { closest: (s) => (s === '[data-act]' ? node : null) } });
  assert.equal(got && got.activity_id, 'a1');
});

test('usuario en modo lectura: no ve acciones de escritura en ninguna vista y si la nota', async () => {
  const writeActs = ['share-toggle', 'follow', 'kudo', 'comment-send', 'club-join', 'club-form', 'club-create', 'chal-create', 'share-send'];
  for (const view of ['feed', 'ranking', 'clubs']) {
    const el = fakeContainer();
    const ctl = C.mount(el, { view, canWrite: false, fetch: fakeFetch([]), getToken: () => 't', onUpgrade() {} });
    await ctl.ready;
    assert.ok(el.innerHTML.includes('data-lxc="readonly"'), view + ': nota de plan');
    assert.ok(el.innerHTML.includes('data-act="upgrade"'));
    for (const a of writeActs) assert.ok(!el.innerHTML.includes('data-act="' + a + '"'), `${view}: no debe mostrar ${a}`);
  }
});

test('modo lectura: un clic forzado en una accion de escritura no llama al backend', async () => {
  const calls = [];
  const el = fakeContainer();
  const ctl = C.mount(el, { view: 'feed', canWrite: false, fetch: fakeFetch(calls), getToken: () => 't' });
  await ctl.ready;
  const n = calls.length;
  const node = { getAttribute: (k) => ({ 'data-act': 'kudo', 'data-id': 'p1' }[k]) };
  el._h.click({ target: { closest: (s) => (s === '[data-act]' ? node : null) } });
  assert.equal(calls.length, n);
});

test('con permiso de escritura aparecen publicar, crear club y unirse con un toque', async () => {
  let el = fakeContainer();
  let ctl = C.mount(el, { view: 'feed', canWrite: true, fetch: fakeFetch([]), getToken: () => 't' });
  await ctl.ready;
  assert.ok(el.innerHTML.includes('data-act="share-toggle"'));
  assert.ok(!el.innerHTML.includes('data-lxc="readonly"'));
  el = fakeContainer();
  ctl = C.mount(el, { view: 'clubs', canWrite: true, fetch: fakeFetch([]), getToken: () => 't' });
  await ctl.ready;
  assert.ok(el.innerHTML.includes('data-act="club-form"'));
  assert.ok(el.innerHTML.includes('data-act="club-join"'));
});

test('ranking: exactamente 2 selectores y la metrica TSS fija', async () => {
  const el = fakeContainer();
  const ctl = C.mount(el, { view: 'ranking', canWrite: true, fetch: fakeFetch([]), getToken: () => 't' });
  await ctl.ready;
  assert.equal((el.innerHTML.match(/<select/g) || []).length, 2);
  assert.ok(el.innerHTML.includes('data-act="rank-scope"') && el.innerHTML.includes('data-act="rank-period"'));
});

test('crear club envia los campos reales del backend (sport / is_private)', async () => {
  const bodies = [];
  const base = fakeFetch([]);
  const f = async (url, init) => { if (init && init.method === 'POST') bodies.push(JSON.parse(init.body)); return base(url, init); };
  const el = fakeContainer();
  const ctl = C.mount(el, { view: 'clubs', canWrite: true, fetch: f, getToken: () => 't' });
  await ctl.ready;
  Object.assign(ctl.state.drafts, { 'club-name': 'Club Test', 'club-sport': 'cycling', 'club-private': true });
  const node = { getAttribute: (k) => ({ 'data-act': 'club-create' }[k]) };
  await el._h.click({ target: { closest: (s) => (s === '[data-act]' ? node : null) } });
  assert.deepEqual(bodies[0], { name: 'Club Test', sport: 'cycling', is_private: true });
});

test('i18n: todas las claves com_* usadas existen en ES, PT y EN', () => {
  const used = new Set((SRC.match(/'com_[a-z_]+'/g) || []).map((s) => s.slice(1, -1)));
  const dyn = {
    com_tab_: ['feed', 'ranking', 'clubs'],
    com_sport_: ['triathlon', 'running', 'cycling', 'swimming'],
    com_metric_: ['km', 'tss', 'activities', 'hours'],
    com_vis_: ['followers', 'public', 'private'],
    com_scope_: ['social', 'club', 'country', 'global'],
    com_period_: ['week', 'month', 'year'],
  };
  for (const p of Object.keys(dyn)) { used.delete(p); dyn[p].forEach((s) => used.add(p + s)); }
  const e = I18N.indexOf('\n  es: {'), p = I18N.indexOf('\n  pt: {'), n = I18N.indexOf('\n  en: {');
  const blocks = { es: I18N.slice(e, p), pt: I18N.slice(p, n), en: I18N.slice(n) };
  for (const lang of Object.keys(blocks)) {
    for (const k of used) assert.ok(new RegExp('\\b' + k + ':').test(blocks[lang]), `${lang} sin ${k}`);
  }
});

test('el modulo no depende de la cascara ni usa endpoints nuevos', () => {
  assert.ok(!/_loadActivityDetail|showCommunityActivityDetail|apiFetch\(/.test(SRC));
  const paths = (SRC.match(/'\/(community|athlete)\/[^']*/g) || []).map((s) => s.slice(1));
  for (const p of paths) assert.match(p, /^\/(community|athlete\/activities)/);
});
