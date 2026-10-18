// B1 — gating de plan en el cliente (routes.config.js).
// Ejecutar: node --test tests/js/
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const SRC = fs.readFileSync(path.join(__dirname, '..', '..', 'routes.config.js'), 'utf8');

// Carga routes.config.js tal como lo hace el navegador (IIFE sobre `window`).
function load(pathname = '/dashboard.html', sess = null) {
  const redirects = [];
  const win = {
    location: {
      pathname,
      replace(url) { redirects.push(url); },
    },
  };
  const storage = {
    getItem: () => (sess ? JSON.stringify(sess) : null),
    setItem() {},
    removeItem() {},
  };
  new Function('window', 'sessionStorage', 'localStorage', SRC)(win, storage, storage);
  return { routes: win.LX_ROUTES, redirects };
}

const athleteBasic = { api_rol: 'atleta', plan: 'basico' };
const athleteAg = { api_rol: 'atleta', plan: 'agegroup' };
const athleteElite = { api_rol: 'atleta', plan: 'elite' };

test('normPlan unifica basico y basic', () => {
  const { routes } = load();
  assert.equal(routes.normPlan('basico'), 'basic');
  assert.equal(routes.normPlan('BASICO'), 'basic');
  assert.equal(routes.normPlan('basic'), 'basic');
  assert.equal(routes.normPlan('elite'), 'elite');
});

test('plan basico (BD) da el mismo acceso que basic (catálogo)', () => {
  const { routes } = load();
  assert.deepEqual(
    routes.allowedForPlan('basico').slice().sort(),
    routes.allowedForPlan('basic').slice().sort(),
  );
  assert.equal(routes.canAccess(athleteBasic, 'performance'), true);
  assert.equal(routes.canAccess(athleteBasic, 'race_day'), false);
});

test('detalle.html tiene plan mínimo basic', () => {
  const { routes } = load();
  assert.equal(routes.byId.detalle.minPlan, 'basic');
  assert.equal(routes.byFile['detalle.html'].minPlan, 'basic');
});

test('Sesión (training_detail, sidebar:false) exige elite', () => {
  const { routes } = load();
  assert.equal(routes.canAccess(athleteBasic, 'training_detail'), false);
  assert.equal(routes.canAccess(athleteAg, 'training_detail'), false);
  assert.equal(routes.canAccess(athleteElite, 'training_detail'), true);
});

test('guard redirige a basico fuera de Sesión', () => {
  const { routes, redirects } = load('/training_detail.html', athleteBasic);
  routes.guard();
  assert.deepEqual(redirects, ['dashboard.html?locked=training_detail']);
});

test('guard deja pasar a elite en Sesión', () => {
  const { routes, redirects } = load('/training_detail.html', athleteElite);
  routes.guard();
  assert.deepEqual(redirects, []);
});

test('guard bloquea detalle.html (Rendimiento) sin plan válido', () => {
  // Sin sesión el guard manda a login; con sesión basic debe pasar (plan mínimo basic).
  const noSess = load('/detalle.html', null);
  noSess.routes.guard();
  assert.deepEqual(noSess.redirects, ['login.html']);

  const basic = load('/detalle.html', athleteBasic);
  basic.routes.guard();
  assert.deepEqual(basic.redirects, []);
});

test('guard bloquea Race Day a basico (plan agegroup)', () => {
  const { routes, redirects } = load('/race_day.html', athleteBasic);
  routes.guard();
  assert.deepEqual(redirects, ['dashboard.html?locked=race_day']);
});

test('App Móvil sigue accesible para basico', () => {
  const { routes, redirects } = load('/athlete-app.html', athleteBasic);
  routes.guard();
  assert.deepEqual(redirects, []);
});
