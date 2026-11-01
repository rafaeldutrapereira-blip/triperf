// S5 (2026-11-01) — motor de bloques: running (ritmo / FC) + regresión de bici.
// Ejecutar: node --test tests/js/workout_blocks_run_s5.test.js
const { test } = require('node:test');
const assert = require('node:assert/strict');
const lax = require('node:assert'); // deepEqual sin chequeo de prototipo (objetos de otro contexto vm)
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SRC = fs.readFileSync(path.join(__dirname, '..', '..', 'workout-blocks.js'), 'utf8');
const win = {};
vm.runInNewContext(SRC, { window: win });
const W = win.WorkoutBlocks;

const THR = 270; // 4:30/km

test('parsePace / fmtPace: mm:ss válido, basura rechazada', () => {
  assert.equal(W.parsePace('4:30'), 270);
  assert.equal(W.parsePace('4,30'), 270);
  assert.equal(W.parsePace(' 5:05 '), 305);
  assert.equal(W.parsePace('4:'), null);
  assert.equal(W.parsePace('abc'), null);
  assert.equal(W.parsePace('4:75'), null);
  assert.equal(W.parsePace('1:00'), null, 'fuera de rango humano (<2:00)');
  assert.equal(W.fmtPace(270), '4:30');
  assert.equal(W.fmtPace(305), '5:05');
  assert.equal(W.fmtPace(0), '--:--');
});

test('makeBlock run/pace: tipos de bici, objetivo derivado del umbral', () => {
  const o = { sport: 'run', mode: 'pace', thresholdPace: THR };
  const warm = W.makeBlock('warmup', 'a', o);
  const iv = W.makeBlock('intervals', 'b', o);
  const cool = W.makeBlock('cooldown', 'c', o);
  const st = W.makeBlock('steady', 'd', o);
  assert.equal(warm.mode, 'pace');
  assert.ok(warm.val_low > warm.val_high, 'calentamiento acelera (ritmo en s/km baja)');
  assert.ok(iv.on_val < THR, 'series más rápidas que el umbral');
  assert.ok(iv.off_val > THR, 'recuperación más lenta que el umbral');
  assert.ok(cool.val_low < cool.val_high, 'enfriamiento desacelera');
  assert.ok(st.val > THR, 'steady aeróbico más lento que el umbral');
  assert.equal(iv.repeat, 4);
  assert.equal(W.totalBlockDuration(iv), 4 * (240 + 120));
});

test('makeBlock run/hr: valores como fracción de FCmáx', () => {
  const o = { sport: 'run', mode: 'hr' };
  const iv = W.makeBlock('intervals', 'b', o);
  assert.equal(iv.mode, 'hr');
  assert.ok(iv.on_val > iv.off_val && iv.on_val <= 1);
  const ramp = W.makeBlock('ramp', 'r', o);
  assert.ok(ramp.val_high > ramp.val_low);
});

test('sin umbral real usa referencia por defecto (5:00/km), sin romper', () => {
  const iv = W.makeBlock('intervals', 'b', { sport: 'run', mode: 'pace' });
  assert.ok(iv.on_val > 0 && iv.on_val < W.RUN_DEFAULT_THR);
});

test('buildSegments run: intensidad relativa al umbral (ritmo y FC)', () => {
  const pace = [
    { type: 'steady', mode: 'pace', duration: 600, val: 270 }, // = umbral
    { type: 'intervals', mode: 'pace', repeat: 2, on_duration: 60, on_val: 240, off_duration: 60, off_val: 360 },
  ];
  const segs = W.buildSegments(pace, { thresholdPace: THR });
  assert.equal(segs.length, 5);
  assert.equal(segs[0].ps, 1);
  assert.ok(Math.abs(segs[1].ps - 270 / 240) < 1e-9);
  assert.ok(Math.abs(segs[2].ps - 270 / 360) < 1e-9);
  assert.equal(segs[4].te, 600 + 2 * 120);
  const hr = W.buildSegments([{ type: 'steady', mode: 'hr', duration: 60, val: 0.9 }]);
  assert.ok(Math.abs(hr[0].ps - 1) < 1e-9, '90% FCmáx = umbral');
});

test('blockSummaryText run: ritmo en m:ss/km, FC con bpm si hay FCmáx', () => {
  const fmt = (s) => s + 's';
  assert.equal(
    W.blockSummaryText({ type: 'steady', mode: 'pace', duration: 600, val: 300 }, fmt, {}),
    '600s · 5:00/km',
  );
  assert.equal(
    W.blockSummaryText({ type: 'steady', mode: 'hr', duration: 600, val: 0.75 }, fmt, { fcmax: 200 }),
    '600s · 75% FCmax (150 bpm)',
  );
  assert.equal(
    W.blockSummaryText({ type: 'intervals', mode: 'pace', repeat: 5, on_duration: 240, on_val: 260, off_duration: 120, off_val: 380 }, fmt, {}),
    '5×(240s @ 4:20/km / 120s @ 6:20/km)',
  );
});

test('convertRunBlock pace -> hr -> pace conserva la intensidad (±5 s/km)', () => {
  const b = W.makeBlock('intervals', 'x', { sport: 'run', mode: 'pace', thresholdPace: THR });
  const orig = { on: b.on_val, off: b.off_val };
  const ctx = { thresholdPace: THR };
  W.convertRunBlock(b, 'hr', ctx);
  assert.equal(b.mode, 'hr');
  assert.ok(b.on_val > b.off_val && b.on_val < 1);
  W.convertRunBlock(b, 'pace', ctx);
  assert.equal(b.mode, 'pace');
  assert.ok(Math.abs(b.on_val - orig.on) <= 5 && Math.abs(b.off_val - orig.off) <= 5);
});

test('TCX de running: Sport=Running, nunca bike; pasos y objetivos correctos', () => {
  const blocks = [
    { type: 'warmup', mode: 'pace', duration: 600, val_low: 390, val_high: 345 },
    { type: 'intervals', mode: 'pace', repeat: 5, on_duration: 240, on_val: 260, off_duration: 120, off_val: 380 },
    { type: 'cooldown', mode: 'pace', duration: 300, val_low: 345, val_high: 390 },
  ];
  const x = W.blocksToTcxXml(blocks, 'Series 5x4', {});
  assert.match(x, /<Workout Sport="Running">/);
  assert.doesNotMatch(x, /bike|Biking/i);
  assert.match(x, /<Repetitions>5<\/Repetitions>/);
  assert.match(x, /<Intensity>Warmup<\/Intensity>/);
  assert.match(x, /<Intensity>Resting<\/Intensity>/);
  assert.match(x, /<Intensity>Cooldown<\/Intensity>/);
  assert.match(x, /Speed_t/);
  // 6:30/km = 2.564 m/s (límite lento) y 5:45/km = 2.899 m/s (rápido)
  assert.match(x, /<LowInMetersPerSecond>2\.564<\/LowInMetersPerSecond><HighInMetersPerSecond>2\.899</);
  // nombre de Training Center: máx. 15 caracteres
  const long = W.blocksToTcxXml(blocks, 'Nombre larguisimo de workout', {});
  assert.match(long, /<Name>Nombre larguisi<\/Name>/);
});

test('TCX con objetivo por FC: bpm absolutos con FCmáx real', () => {
  const x = W.blocksToTcxXml([{ type: 'steady', mode: 'hr', duration: 1200, val: 0.75 }], 'Z2', { fcmax: 200 });
  assert.match(x, /HeartRate_t/);
  assert.match(x, /<Low [^>]*><Value>146<\/Value><\/Low><High [^>]*><Value>154<\/Value>/);
});

// ---- Regresión de bici: salida idéntica a la de antes de S5 ----
const BIKE = [
  { id: 'a', type: 'warmup', duration: 600, power_low: 0.5, power_high: 0.75 },
  { id: 'b', type: 'intervals', repeat: 4, on_duration: 240, on_power: 0.95, off_duration: 120, off_power: 0.55 },
  { id: 'c', type: 'steady', duration: 300, power: 0.75 },
  { id: 'd', type: 'cooldown', duration: 300, power_low: 0.5, power_high: 0.75 },
];

test('bici: ZWO idéntico (sportType bike, mismos tags)', () => {
  const zwo = W.blocksToZwoXml(BIKE, 'Sweet', 'desc');
  assert.equal(
    zwo,
    [
      '<?xml version="1.0" encoding="utf-8"?>',
      '<workout_file>',
      '  <author>LabX Coach</author>',
      '  <name>Sweet</name>',
      '  <description>desc</description>',
      '  <sportType>bike</sportType>',
      '  <tags/>',
      '  <workout>',
      '    <Warmup Duration="600" PowerLow="0.50" PowerHigh="0.75"/>',
      '    <IntervalsT Repeat="4" OnDuration="240" OffDuration="120" OnPower="0.95" OffPower="0.55" pace="0"/>',
      '    <SteadyState Duration="300" Power="0.75"/>',
      '    <Cooldown Duration="300" PowerLow="0.75" PowerHigh="0.50"/>',
      '  </workout>',
      '</workout_file>',
    ].join('\n'),
  );
});

test('bici: ERG/MRC y segmentos sin cambios', () => {
  const segs = W.buildSegments(BIKE);
  assert.equal(segs.length, 1 + 8 + 1 + 1);
  lax.deepEqual(segs[0], { ts: 0, te: 600, ps: 0.5, pe: 0.75 });
  const erg = W.blocksToErgText(BIKE, 'Sweet', 200);
  assert.match(erg, /MINUTES WATTS/);
  assert.match(erg, /\r\n0\t100\r\n0\t100\r\n10\t150\r\n/);
  const mrc = W.blocksToMrcText(BIKE, 'Sweet', 200);
  assert.match(mrc, /MINUTES PERCENT/);
  assert.match(mrc, /\r\n10\t75\r\n10\t95\r\n/);
  assert.equal(W.blockSummaryText(BIKE[2], null), '300s · 75% FTP');
});

test('bici: makeBlock sin opts devuelve los mismos bloques de siempre', () => {
  lax.deepEqual(W.makeBlock('steady', 'z'), { id: 'z', type: 'steady', duration: 300, power: 0.75 });
  lax.deepEqual(W.makeBlock('freeride', 'f'), { id: 'f', type: 'freeride', duration: 300 });
  assert.equal(W.makeBlock('intervals', 'i').on_power, 0.95);
});
