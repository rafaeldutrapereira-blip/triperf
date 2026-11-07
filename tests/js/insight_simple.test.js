// INSIGHT-SIMPLE: renderInsight / toggleInsightWhy del Insight del dia (vista simple vs expandida)
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
const web = fs.readFileSync(path.join(__dirname, '..', '..', 'dashboard.html'), 'utf8');

function el() {
  const cls = new Set();
  return {
    textContent: '',
    innerHTML: '',
    style: {},
    className: '',
    href: '',
    classList: {
      add: (c) => cls.add(c),
      remove: (c) => cls.delete(c),
      contains: (c) => cls.has(c),
      toggle(c, force) {
        const on = force === undefined ? !cls.has(c) : force;
        if (on) cls.add(c);
        else cls.delete(c);
        return on;
      },
    },
  };
}

function build() {
  const ids = [
    'insight-severity', 'insight-sev-word', 'insight-headline', 'insight-message', 'insight-action',
    'insight-why-toggle', 'insight-technical', 'insight-detail', 'insight-why-label',
    'insight-drivers', 'insight-cta', 'insight-cta-label',
  ];
  const els = {};
  ids.forEach((i) => (els[i] = el()));
  const document = { getElementById: (i) => els[i] };
  const window = {};
  const _t = (k, fb) => fb;
  const src =
    ['_escInsight', '_insightSevWord', 'renderInsight', 'toggleInsightWhy'].map((n) => extract(web, n)).join('\n') +
    '; return {renderInsight, toggleInsightWhy};';
  const api = new Function('document', 'window', '_t', src)(document, window, _t);
  return { els, ...api };
}

const INS = {
  severity: 'caution',
  headline: 'Carga alta esta semana',
  message_bullets: ['Tu fatiga subio.', 'Dormiste poco.', 'Hoy: rodaje suave de 40 min.'],
  message_technical: ['TSB -18', 'ACWR 1.4'],
  drivers: [{ label: 'TSB', value: '-18', delta: '-3', tone: 'bad' }],
  cta_label: 'Ver plan',
  cta_href: 'training_plan.html',
};

test('vista simple por defecto: palabra de severidad, titular, accion = ultimo bullet, CTA; detalle plegado', () => {
  const m = build();
  m.renderInsight(INS);
  assert.strictEqual(m.els['insight-sev-word'].textContent, 'Precaución');
  assert.ok(m.els['insight-severity'].className.includes('sev-caution'));
  assert.strictEqual(m.els['insight-headline'].textContent, 'Carga alta esta semana');
  assert.strictEqual(m.els['insight-action'].textContent, 'Hoy: rodaje suave de 40 min.');
  assert.strictEqual(m.els['insight-cta'].style.display, 'inline-flex');
  assert.strictEqual(m.els['insight-cta'].href, 'training_plan.html');
  assert.strictEqual(m.els['insight-detail'].classList.contains('open'), false); // drivers NO visibles
  assert.strictEqual(m.els['insight-why-toggle'].style.display, 'inline-flex');
  assert.strictEqual(m.els['insight-why-label'].textContent, 'Ver por qué');
});

test('expandido: bullets completos + drivers + tecnica dentro de la region plegable', () => {
  const m = build();
  m.renderInsight(INS);
  m.toggleInsightWhy();
  assert.strictEqual(m.els['insight-detail'].classList.contains('open'), true);
  assert.strictEqual((m.els['insight-message'].innerHTML.match(/<li>/g) || []).length, 3);
  assert.ok(m.els['insight-message'].innerHTML.includes('Tu fatiga subio.'));
  assert.ok(m.els['insight-drivers'].innerHTML.includes('insight-driver-lbl'));
  assert.strictEqual((m.els['insight-technical'].innerHTML.match(/<li>/g) || []).length, 2);
  assert.strictEqual(m.els['insight-why-label'].textContent, 'Ocultar detalle');
  m.toggleInsightWhy(); // vuelve a plegar
  assert.strictEqual(m.els['insight-detail'].classList.contains('open'), false);
  assert.strictEqual(m.els['insight-why-label'].textContent, 'Ver por qué');
});

test('re-render deja el detalle plegado otra vez', () => {
  const m = build();
  m.renderInsight(INS);
  m.toggleInsightWhy();
  m.renderInsight(INS);
  assert.strictEqual(m.els['insight-detail'].classList.contains('open'), false);
});

test('mensaje de 1 bullet: esa es la accion; sin detalle de mensaje ni toggle si no hay mas', () => {
  const m = build();
  m.renderInsight({ severity: 'good', headline: 'Todo bien', message_bullets: ['Sigue tu plan.'] });
  assert.strictEqual(m.els['insight-action'].textContent, 'Sigue tu plan.');
  assert.strictEqual(m.els['insight-message'].style.display, 'none');
  assert.strictEqual(m.els['insight-why-toggle'].style.display, 'none');
  assert.strictEqual(m.els['insight-sev-word'].textContent, 'Bien');
});

test('1 bullet con drivers: el toggle aparece (hay detalle que ver)', () => {
  const m = build();
  m.renderInsight({ severity: 'neutral', headline: 'H', message_bullets: ['A'], drivers: [{ label: 'x', value: '1' }] });
  assert.strictEqual(m.els['insight-why-toggle'].style.display, 'inline-flex');
});

test('mensaje vacio: solo titular, sin linea de accion ni toggle; message suelto se acepta', () => {
  const m = build();
  m.renderInsight({ severity: 'reduce', headline: 'Solo titular' });
  assert.strictEqual(m.els['insight-headline'].textContent, 'Solo titular');
  assert.strictEqual(m.els['insight-action'].textContent, '');
  assert.strictEqual(m.els['insight-action'].style.display, 'none');
  assert.strictEqual(m.els['insight-why-toggle'].style.display, 'none');
  assert.strictEqual(m.els['insight-cta'].style.display, 'none');
  m.renderInsight({ severity: 'reduce', headline: 'H', message: 'Texto suelto' });
  assert.strictEqual(m.els['insight-action'].textContent, 'Texto suelto');
});

test('tipografia: nada por debajo de 0.8rem en la tarjeta, titular >=1.3rem', () => {
  const css = web.slice(web.indexOf('.insight-card {'), web.indexOf('/* -- KPI CARDS'));
  const sizes = [...css.matchAll(/font-size:\s*([\d.]+)rem/g)].map((x) => parseFloat(x[1]));
  assert.ok(sizes.length > 10);
  assert.ok(Math.min(...sizes) >= 0.8, 'min=' + Math.min(...sizes));
  assert.ok(/\.insight-headline\s*\{[^}]*font-size:\s*1\.3rem/.test(css));
});
