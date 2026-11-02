/*
 * estado-checkin.js (S28) — check-in unico de 9 campos de "Estado de hoy".
 *
 * Funcion pura: reparte las respuestas del formulario unico hacia los DOS
 * endpoints que ya existen, con exactamente la misma forma de payload que
 * armaban los dos formularios anteriores:
 *   - POST /api/recovery/wellness  (energy, mood, soreness, motivation, stress, sleep_quality, notes)
 *   - POST /api/mental/checkin     (anxiety, motivation, focus, confidence, mood, notes)
 * Los calculos de Recovery y MFS no cambian: solo cambia la captura.
 *
 * Campos: 4 solo-fisicos (energy, soreness, stress, sleep_quality),
 *         3 solo-mentales (anxiety, focus, confidence),
 *         2 compartidos (mood, motivation) que alimentan ambos puntajes.
 */
(function (root) {
  'use strict';

  var PHYS = ['energy', 'soreness', 'stress', 'sleep_quality'];
  var BOTH = ['mood', 'motivation'];
  var MENT = ['anxiety', 'focus', 'confidence'];
  var FIELDS = PHYS.concat(BOTH, MENT);
  var WELL_FIELDS = ['energy', 'mood', 'soreness', 'motivation', 'stress', 'sleep_quality'];
  var MEN_FIELDS = ['anxiety', 'motivation', 'focus', 'confidence', 'mood'];

  function has(v) {
    return v !== null && v !== undefined && v !== 0 && v !== '';
  }

  /*
   * answers : { campo: 1..5 }  lo que muestra el formulario
   * opts.dateIso
   * opts.touched : { campo: true }  campos que el usuario toco en esta sesion
   * opts.stored  : { well: {...}, men: {...} }  lo ya guardado hoy en cada destino
   *                (dias con dos check-ins separados pueden diferir en mood/motivation:
   *                 si el usuario no los toca, cada destino conserva su valor)
   * opts.notes / opts.notesTouched / opts.storedNotes { well, men }
   * Devuelve { well: body|null, men: payload|null } (null = nada que enviar).
   */
  function buildPayloads(answers, opts) {
    opts = opts || {};
    answers = answers || {};
    var touched = opts.touched || {};
    var stored = opts.stored || {};
    var sw = stored.well || {};
    var sm = stored.men || {};
    var sn = opts.storedNotes || {};

    function pick(field, own) {
      var shared = BOTH.indexOf(field) !== -1;
      if (shared && !touched[field] && has(own)) return own;
      return answers[field];
    }

    var note = opts.notes || '';
    function noteFor(own) {
      if (opts.notesTouched) return note || null;
      return own || note || null;
    }

    var well = { date_iso: opts.dateIso, notes: noteFor(sn.well) };
    var anyWell = false;
    WELL_FIELDS.forEach(function (f) {
      var v = pick(f, sw[f]);
      if (has(v)) {
        well[f] = v;
        anyWell = true;
      }
    });

    var men = { date_iso: opts.dateIso };
    var anyMen = false;
    MEN_FIELDS.forEach(function (f) {
      var v = pick(f, sm[f]);
      men[f] = has(v) ? v : null;
      if (has(v)) anyMen = true;
    });
    men.notes = noteFor(sn.men);

    return { well: anyWell ? well : null, men: anyMen ? men : null };
  }

  var api = {
    FIELDS: FIELDS,
    PHYS: PHYS,
    BOTH: BOTH,
    MENT: MENT,
    WELL_FIELDS: WELL_FIELDS,
    MEN_FIELDS: MEN_FIELDS,
    buildPayloads: buildPayloads,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.EstadoCheckin = api;
})(typeof window !== 'undefined' ? window : globalThis);
