// Fix sesión (2026-11-01) — el 401 limpia la sesión y redirige sin bucle,
// más revalidación al volver a la pestaña. Ver diagnóstico en
// labx-overnight/diagnostico-sesion.md.
// Ejecutar: node --test tests/js/
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const AUTH_SRC = fs.readFileSync(path.join(__dirname, '..', '..', 'auth.js'), 'utf8');
const NAV_SRC = fs.readFileSync(path.join(__dirname, '..', '..', 'nav.js'), 'utf8');

function makeStorage(initial) {
  const data = Object.assign({}, initial);
  return {
    _data: data,
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = v; },
    removeItem: (k) => { delete data[k]; },
  };
}

// Carga auth.js tal como lo hace el navegador (IIFE sobre `window`), con
// document/location/fetch mockeados para inspeccionar sin un DOM real.
function loadAuth({ pathname = '/dashboard.html', origin = 'https://labxperformanceapp.com',
                     protocol = 'https:', sessionData = null, fetchImpl } = {}) {
  const redirects = [];
  const storage = makeStorage(sessionData ? { kl_s: JSON.stringify(sessionData) } : {});
  const docListeners = {};
  const winListeners = {};
  const doc = {
    visibilityState: 'visible',
    addEventListener(ev, fn) { docListeners[ev] = fn; },
  };
  const win = {
    location: { pathname, origin, protocol, replace(url) { redirects.push(url); } },
    addEventListener(ev, fn) { winListeners[ev] = fn; },
  };
  const fetchCalls = [];
  const fetchFn = fetchImpl || (() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) }));
  function fetchMock(url, opts) {
    fetchCalls.push({ url, opts });
    return fetchFn(url, opts);
  }
  new Function('window', 'document', 'localStorage', 'sessionStorage', 'fetch', AUTH_SRC)(
    win, doc, storage, storage, fetchMock,
  );
  return { KL: win.KL, redirects, storage, docListeners, winListeners, fetchCalls };
}

const SOME_SESSION = { username: 'rafael', api_rol: 'atleta', plan: 'basic' };

test('auth.js: clearSession borra kl_s y los tokens de la Coach API', () => {
  const { KL, storage } = loadAuth({ sessionData: SOME_SESSION });
  storage.setItem('lx_co_token', 'tok123');
  KL.clearSession();
  assert.equal(storage.getItem('kl_s'), null);
  assert.equal(storage.getItem('lx_co_token'), null);
});

test('auth.js: logout llama a API_BASE (origin real), no al fallback localhost', async () => {
  const { KL, fetchCalls } = loadAuth({ origin: 'https://labxperformanceapp.com' });
  KL.logout();
  // logout() es fire-and-forget (fetch + finally); esperar un tick.
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(fetchCalls.length, 1);
  assert.match(fetchCalls[0].url, /^https:\/\/labxperformanceapp\.com\/api\/auth\/logout$/);
});

test('revalidación: sin sesión local no llama a /auth/me', () => {
  const { docListeners, fetchCalls } = loadAuth({ sessionData: null });
  docListeners.visibilitychange();
  assert.equal(fetchCalls.length, 0);
});

test('revalidación: en login.html/landing.html no revalida aunque haya sesión', () => {
  const a = loadAuth({ pathname: '/login.html', sessionData: SOME_SESSION });
  a.docListeners.visibilitychange();
  assert.equal(a.fetchCalls.length, 0);

  const b = loadAuth({ pathname: '/landing.html', sessionData: SOME_SESSION });
  b.docListeners.visibilitychange();
  assert.equal(b.fetchCalls.length, 0);
});

test('revalidación: 401 explícito en /auth/me limpia la sesión y redirige a login', async () => {
  const { storage, redirects, docListeners, fetchCalls } = loadAuth({
    sessionData: SOME_SESSION,
    fetchImpl: () => Promise.resolve({ ok: false, status: 401 }),
  });
  docListeners.visibilitychange();
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(fetchCalls.length, 1);
  assert.match(fetchCalls[0].url, /\/auth\/me$/);
  assert.equal(storage.getItem('kl_s'), null);
  assert.deepEqual(redirects, ['login.html']);
});

test('revalidación: error de red (offline) NO limpia la sesión', async () => {
  const { storage, redirects, docListeners } = loadAuth({
    sessionData: SOME_SESSION,
    fetchImpl: () => Promise.reject(new Error('offline')),
  });
  docListeners.visibilitychange();
  await new Promise((r) => setTimeout(r, 0));
  assert.notEqual(storage.getItem('kl_s'), null);
  assert.deepEqual(redirects, []);
});

test('revalidación: respuesta ok (sesión vigente) no toca nada', async () => {
  const { storage, redirects, docListeners } = loadAuth({
    sessionData: SOME_SESSION,
    fetchImpl: () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) }),
  });
  docListeners.visibilitychange();
  await new Promise((r) => setTimeout(r, 0));
  assert.notEqual(storage.getItem('kl_s'), null);
  assert.deepEqual(redirects, []);
});

test('revalidación: pageshow con persisted:true también revalida', async () => {
  const { storage, redirects, winListeners } = loadAuth({
    sessionData: SOME_SESSION,
    fetchImpl: () => Promise.resolve({ ok: false, status: 401 }),
  });
  winListeners.pageshow({ persisted: true });
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(storage.getItem('kl_s'), null);
  assert.deepEqual(redirects, ['login.html']);
});

test('revalidación: pageshow sin persisted no hace nada', () => {
  const { fetchCalls, winListeners } = loadAuth({ sessionData: SOME_SESSION });
  winListeners.pageshow({ persisted: false });
  assert.equal(fetchCalls.length, 0);
});

// ── nav.js: parche global de fetch, bloque "9. FETCH PATCH" ──────────────
// Se extrae por texto (mismo método que test_backend_i18n_mapping.py usa
// para lx-info.js) porque nav.js completo no se puede cargar en un sandbox
// sin DOM (inyecta widgets, etc.) — este bloque es autocontenido.
function _fetchPatchBlock() {
  const anchor = NAV_SRC.indexOf('var _f=window.fetch;');
  assert.ok(anchor > -1, 'no se encontró "var _f=window.fetch;" en nav.js (¿cambió el texto?)');
  const start = NAV_SRC.lastIndexOf('(function(){', anchor);
  assert.ok(start > -1, 'no se encontró el IIFE que envuelve el FETCH PATCH en nav.js');
  const end = NAV_SRC.indexOf('})();', anchor) + '})();'.length;
  return NAV_SRC.slice(start, end);
}

function loadFetchPatch({ fetchImpl, hasKL = true } = {}) {
  const block = _fetchPatchBlock();
  const toasts = [];
  const storage = makeStorage();
  const clearSessionCalls = [];
  const redirects = [];
  const win = {
    fetch: fetchImpl,
    KL: hasKL ? { clearSession: () => clearSessionCalls.push(1) } : undefined,
    location: { href: 'https://labxperformanceapp.com/dashboard.html' },
  };
  const lxToast = {
    warn: (m) => toasts.push(['warn', m]),
    error: (m) => toasts.push(['error', m]),
  };
  const location = {
    replace: (url) => redirects.push(url),
  };
  const fn = new Function('window', 'lxToast', 'sessionStorage', 'setTimeout', 'location', block);
  // setTimeout real pero expuesto, para poder adelantarlo con await de un tick
  fn(win, lxToast, storage, setTimeout, location);
  return { win, toasts, storage, clearSessionCalls, redirects };
}

test('nav.js FETCH PATCH: 401 limpia la sesión vía KL.clearSession antes de redirigir', async () => {
  const { win, clearSessionCalls } = loadFetchPatch({
    fetchImpl: () => Promise.resolve({ status: 401 }),
  });
  await win.fetch('/api/athlete/dashboard');
  assert.equal(clearSessionCalls.length, 1);
});

test('nav.js FETCH PATCH: sin KL (página sin auth.js) no explota', async () => {
  const { win } = loadFetchPatch({
    fetchImpl: () => Promise.resolve({ status: 401 }),
    hasKL: false,
  });
  await assert.doesNotReject(() => win.fetch('/api/athlete/dashboard'));
});

test('nav.js FETCH PATCH: 200 no limpia sesión ni redirige', async () => {
  const { win, clearSessionCalls, redirects } = loadFetchPatch({
    fetchImpl: () => Promise.resolve({ status: 200 }),
  });
  await win.fetch('/api/athlete/dashboard');
  assert.equal(clearSessionCalls.length, 0);
  assert.deepEqual(redirects, []);
});
