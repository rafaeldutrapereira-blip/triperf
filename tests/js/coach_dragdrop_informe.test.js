// DRAGDROP-INFORME: chips arrastrables, drop llama a move (con reversion) y botones del informe
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const src = fs.readFileSync(path.join(__dirname, '..', '..', 'coach.html'), 'utf8');

function extract(name, kind) {
  const head = (kind === undefined ? 'function ' : kind) + name;
  const i = src.indexOf(head);
  assert.ok(i >= 0, name + ' no existe');
  const j = src.indexOf('{', src.indexOf(')', i));
  let depth = 0;
  for (let k = j; k < src.length; k++) {
    if (src[k] === '{') depth++;
    else if (src[k] === '}' && --depth === 0) return src.slice(i, k + 1);
  }
  throw new Error('sin cierre ' + name);
}

test('los chips del calendario son arrastrables con data-assignment-id y las celdas son destino', () => {
  assert.match(src, /class="cal-chip" draggable="true" data-assignment-id="/);
  assert.match(src, /class="cal-cell" data-date="/);
  for (const ev of ['dragstart', 'dragover', 'drop']) assert.ok(src.includes("'" + ev + "'"), ev);
  assert.match(src, /calBindDnD\(el\);/);
});

test('mensajes honestos por codigo (403/404/422/400) y generico', () => {
  const calMoveMessage = new Function('_t', extract('calMoveMessage') + '; return calMoveMessage;')((k, fb) => fb);
  assert.match(calMoveMessage(403), /No puedes mover/);
  assert.match(calMoveMessage(404), /ya no existe/);
  assert.match(calMoveMessage(422), /Faltan datos/);
  assert.match(calMoveMessage(400), /Fecha inv/);
  assert.match(calMoveMessage(500), /No se pudo mover/);
});

function fakeCell(date, ath) {
  const attrs = { 'data-date': date, 'data-athlete-id': ath };
  const cell = {
    children: [],
    getAttribute: (k) => attrs[k],
    appendChild(ch) { if (ch.parentNode) ch.parentNode.remove(ch); cell.children.push(ch); ch.parentNode = cell; },
    insertBefore(ch) { cell.appendChild(ch); },
    remove(ch) { cell.children = cell.children.filter((x) => x !== ch); },
  };
  return cell;
}
function fakeChip(id, ath, cell) {
  const attrs = { 'data-assignment-id': id, 'data-athlete-id': ath };
  const chip = { style: {}, nextSibling: null, parentNode: null, getAttribute: (k) => attrs[k] };
  cell.appendChild(chip);
  return chip;
}
function harness(moveResult) {
  const log = { moves: [], toasts: [], reloads: 0 };
  const code = extract('calDrop', 'async function ') + '; return calDrop;';
  const msg = new Function('_t', extract('calMoveMessage') + '; return calMoveMessage;')((k, fb) => fb);
  const calDrop = new Function('calMoveAssignment', 'toast', 'loadCalendar', '_t', 'calMoveMessage', code)(
    async (id, date, ath) => { log.moves.push([id, date, ath]); if (moveResult instanceof Error) throw moveResult; return moveResult; },
    (m, t) => log.toasts.push([m, t]),
    () => { log.reloads++; },
    (k, fb) => fb,
    msg,
  );
  return { calDrop, log };
}

test('soltar en otro dia del mismo atleta llama a move solo con fecha y recarga', async () => {
  const { calDrop, log } = harness({ ok: true, status: 200, data: { intervals_push_status: 'ok' } });
  const from = fakeCell('2026-12-07', 'A'), to = fakeCell('2026-12-09', 'A');
  const chip = fakeChip('as1', 'A', from);
  await calDrop(chip, to);
  assert.deepStrictEqual(log.moves, [['as1', '2026-12-09', null]]);
  assert.strictEqual(chip.parentNode, to);
  assert.strictEqual(log.reloads, 1);
  assert.strictEqual(log.toasts[0][1], 'ok');
});

test('soltar en la fila de otro atleta envia new_athlete_id', async () => {
  const { calDrop, log } = harness({ ok: true, status: 200, data: {} });
  const from = fakeCell('2026-12-07', 'A'), to = fakeCell('2026-12-08', 'B');
  await calDrop(fakeChip('as1', 'A', from), to);
  assert.deepStrictEqual(log.moves, [['as1', '2026-12-08', 'B']]);
});

test('error 403 revierte el chip a su celda y avisa sin recargar', async () => {
  const { calDrop, log } = harness({ ok: false, status: 403, data: null });
  const from = fakeCell('2026-12-07', 'A'), to = fakeCell('2026-12-08', 'B');
  const chip = fakeChip('as1', 'A', from);
  await calDrop(chip, to);
  assert.strictEqual(chip.parentNode, from);
  assert.strictEqual(log.toasts[0][1], 'err');
  assert.match(log.toasts[0][0], /No puedes mover/);
  assert.strictEqual(log.reloads, 0);
});

test('error de red revierte y 404 ademas recarga el calendario', async () => {
  let h = harness(new Error('red'));
  let from = fakeCell('d1', 'A'), chip = fakeChip('as1', 'A', from);
  await h.calDrop(chip, fakeCell('d2', 'A'));
  assert.strictEqual(chip.parentNode, from);
  assert.strictEqual(h.log.toasts[0][1], 'err');

  h = harness({ ok: false, status: 404, data: null });
  from = fakeCell('d1', 'A'); chip = fakeChip('as1', 'A', from);
  await h.calDrop(chip, fakeCell('d2', 'A'));
  assert.strictEqual(h.log.reloads, 1);
});

test('push fallido a intervals se avisa como error visible (la sesion si se movio)', async () => {
  const { calDrop, log } = harness({ ok: true, status: 200, data: { intervals_push_status: 'failed', intervals_push_error: 'intervals caido' } });
  await calDrop(fakeChip('as1', 'A', fakeCell('d1', 'A')), fakeCell('d2', 'A'));
  assert.strictEqual(log.toasts[0][1], 'err');
  assert.match(log.toasts[0][0], /intervals caido/);
  assert.strictEqual(log.reloads, 1);
});

test('el informe tiene Exportar PDF y Compartir enlace que actuan contra la API', () => {
  assert.match(src, /id="rep-export-pdf" onclick="exportReportPdf\(\)"/);
  assert.match(src, /id="rep-share" onclick="shareReportLink\(\)"/);
  const exp = extract('window.exportReportPdf = async function', '');
  assert.match(exp, /\/pdf\?start=/);
  assert.match(exp, /Authorization/);
  assert.match(exp, /\.pdf'/);
  assert.match(src, /'\/coach\/report\/athlete\/' \+ c\.r\.athlete_id \+ '\/share'/);
  assert.match(src, /apiDelete\('\/coach\/report\/shares\/' \+ id\)/);
});

test('claves i18n nuevas existen en ES, PT y EN', () => {
  const i18n = fs.readFileSync(path.join(__dirname, '..', '..', 'i18n.js'), 'utf8');
  for (const k of ['dd_move_ok', 'dd_move_403', 'dd_pdf_btn', 'dd_share_btn', 'dd_share_revoke', 'dd_pub_gone']) {
    assert.strictEqual((i18n.match(new RegExp('\\b' + k + ':', 'g')) || []).length, 3, k);
  }
  const page = fs.readFileSync(path.join(__dirname, '..', '..', 'shared_report.html'), 'utf8');
  assert.match(page, /\/public\/reports\//);
  assert.match(page, /Fitness \(CTL\)/);
});
