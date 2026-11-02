'use strict';
// S28: reparto del check-in unico de 9 campos hacia los dos endpoints existentes.
const test = require('node:test');
const assert = require('node:assert/strict');
const EC = require('../../estado-checkin.js');

const ALL = {
  energy: 4, soreness: 3, stress: 2, sleep_quality: 5,
  mood: 4, motivation: 3,
  anxiety: 5, focus: 2, confidence: 4,
};
const D = '2026-11-02';

test('son exactamente 9 campos sin duplicados', () => {
  assert.equal(EC.FIELDS.length, 9);
  assert.equal(new Set(EC.FIELDS).size, 9);
});

test('mood y motivation alimentan ambos destinos; el resto solo uno', () => {
  const p = EC.buildPayloads(ALL, { dateIso: D, touched: {} });
  assert.deepEqual(p.well, {
    date_iso: D, notes: null,
    energy: 4, mood: 4, soreness: 3, motivation: 3, stress: 2, sleep_quality: 5,
  });
  assert.deepEqual(p.men, {
    date_iso: D, anxiety: 5, motivation: 3, focus: 2, confidence: 4, mood: 4, notes: null,
  });
});

test('la nota unica va a ambos destinos', () => {
  const p = EC.buildPayloads(ALL, { dateIso: D, notes: 'viaje', notesTouched: true });
  assert.equal(p.well.notes, 'viaje');
  assert.equal(p.men.notes, 'viaje');
});

test('sin respuestas no hay nada que enviar; solo bloque fisico no envia mental', () => {
  assert.deepEqual(EC.buildPayloads({}, { dateIso: D }), { well: null, men: null });
  const p = EC.buildPayloads({ energy: 3 }, { dateIso: D });
  assert.equal(p.men, null);
  assert.equal(p.well.energy, 3);
});

test('solo campos mentales: envia mental y bienestar queda null', () => {
  const p = EC.buildPayloads({ focus: 4 }, { dateIso: D });
  assert.equal(p.well, null);
  assert.equal(p.men.focus, 4);
  assert.equal(p.men.mood, null);
});

test('historico: mood/motivation distintos por destino se conservan si no se tocan', () => {
  const stored = { well: { mood: 2, motivation: 5 }, men: { mood: 4, motivation: 1 } };
  const shown = { mood: 2, motivation: 5, energy: 3, anxiety: 3 };
  const p = EC.buildPayloads(shown, { dateIso: D, stored, touched: {} });
  assert.equal(p.well.mood, 2);
  assert.equal(p.men.mood, 4);
  assert.equal(p.well.motivation, 5);
  assert.equal(p.men.motivation, 1);
});

test('historico: si el usuario toca un compartido, gana en ambos destinos', () => {
  const stored = { well: { mood: 2 }, men: { mood: 4 } };
  const p = EC.buildPayloads({ mood: 5, energy: 3, anxiety: 3 }, { dateIso: D, stored, touched: { mood: true } });
  assert.equal(p.well.mood, 5);
  assert.equal(p.men.mood, 5);
});

test('historico: si un destino no tenia el compartido, recibe el valor mostrado', () => {
  const stored = { well: {}, men: { mood: 4 } };
  const p = EC.buildPayloads({ mood: 4, energy: 3, anxiety: 3 }, { dateIso: D, stored, touched: {} });
  assert.equal(p.well.mood, 4);
  assert.equal(p.men.mood, 4);
});
