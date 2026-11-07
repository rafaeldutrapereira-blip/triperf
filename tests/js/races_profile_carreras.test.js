// CARRERAS-PERFIL: lista «Mis carreras del año» del perfil (render y etiquetas)
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

function extract(src, name) {
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
const root = path.join(__dirname, '..', '..');
const web = fs.readFileSync(path.join(root, 'athlete_profile.html'), 'utf8');

function block(from, to) {
  const a = web.indexOf(from);
  assert.ok(a >= 0, from);
  return web.slice(a, web.indexOf(to, a));
}
const maps = block('var RACE_DIST = {', 'var _races = [];');

function build(dict, lang) {
  const _t = (k, fb) => (dict[k] !== undefined ? dict[k] : fb);
  const esc = (s) => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const window = { i18n: { lang } };
  const src =
    maps +
    extract(web, 'raceDistLabel') +
    extract(web, 'raceDateLabel') +
    extract(web, 'raceRowHtml') +
    '; return {raceDistLabel, raceDateLabel, raceRowHtml};';
  return new Function('_t', 'esc', 'window', src)(_t, esc, window);
}

const ES = {
  prof_opt_703: '70.3 / Half (113 km)',
  prof_opt_ironman: 'Ironman (226 km)',
  prof_race_badge_main: 'Principal',
  prof_race_badge_done: 'Realizada',
  prof_race_btn_make_main: 'Hacer principal',
};
const R = [
  { id: 'a', name: 'Pucon', date_iso: '2026-12-06', distance: '70.3', location: 'Chile', priority: 'A', is_goal_race: true, has_result: false },
  { id: 'b', name: 'Santiago', date_iso: '2027-04-18', distance: '42k', priority: null, is_goal_race: false, has_result: false },
  { id: 'c', name: 'Enero 10K', date_iso: '2026-01-10', distance: '10k', priority: 'C', is_goal_race: false, has_result: true },
];
const TODAY = '2026-11-07';

test('70.3 muestra su etiqueta completa, nunca el codigo crudo', () => {
  const m = build(ES, 'es');
  assert.strictEqual(m.raceDistLabel('70.3'), '70.3 / Half (113 km)');
  assert.strictEqual(m.raceDistLabel('703'), '70.3 / Half (113 km)'); // alias legacy
  assert.strictEqual(m.raceDistLabel('full'), 'Ironman (226 km)');
  assert.strictEqual(m.raceDistLabel('zzz'), 'Otro'); // desconocido -> Otro, no el codigo
  assert.strictEqual(m.raceDistLabel(null), '');
});

test('lista de 3 carreras: principal, prioridad, pasada con resultado', () => {
  const m = build(ES, 'es');
  const html = R.map((r) => m.raceRowHtml(r, TODAY));
  assert.ok(html[0].includes('70.3 / Half (113 km)') && !html[0].includes('>70.3<'));
  assert.ok(html[0].includes('Principal') && html[0].includes('>A</span>'));
  assert.ok(html[0].includes('Chile'));
  assert.ok(!html[0].includes('data-act="main"')); // la principal no ofrece «Hacer principal»
  assert.ok(html[1].includes('data-act="main"')); // futura no principal si
  assert.ok(!html[1].includes('Principal</span>'));
  assert.ok(html[2].includes('race-row past'));
  assert.ok(html[2].includes('Realizada'));
  assert.ok(!html[2].includes('data-act="main"')); // pasada no ofrece principal
  assert.ok(html[2].includes('data-act="edit"') && html[2].includes('data-act="del"'));
});

test('escapa el nombre de la carrera', () => {
  const m = build(ES, 'es');
  const h = m.raceRowHtml({ ...R[1], name: '<img onerror=x>' }, TODAY);
  assert.ok(!h.includes('<img'));
  assert.ok(h.includes('&lt;img'));
});

test('fecha segun idioma activo', () => {
  const es = build(ES, 'es').raceDateLabel('2026-12-06');
  const en = build(ES, 'en').raceDateLabel('2026-12-06');
  assert.ok(/dic/i.test(es), es);
  assert.ok(/dec/i.test(en), en);
});

test('perfil: sin inputs viejos y sin race_goal_* en el guardado', () => {
  assert.ok(!web.includes('id="p-race-name"'));
  const save = extract(web, 'saveProfile');
  assert.ok(!save.includes('race_goal'));
  assert.ok(web.includes('id="races-list"') && web.includes('id="rc-save"'));
});

test('claves i18n nuevas existen en ES, PT y EN', () => {
  const i18n = fs.readFileSync(path.join(root, 'i18n.js'), 'utf8');
  const keys = [...new Set([...web.matchAll(/'(prof_race[a-z_]*|prof_races_empty|prof_card_my_races)'/g)].map((m) => m[1]))];
  assert.ok(keys.length >= 12, String(keys.length));
  for (const k of [...keys, 'prof_card_my_races', 'prof_race_label_name']) {
    const n = i18n.split(new RegExp('\\b' + k + ':')).length - 1;
    assert.ok(n >= 3, k + ' esta en ' + n + ' diccionarios');
  }
});
