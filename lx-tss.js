/* lx-tss.js — estimador UNICO de TSS del front (CQ3).
 * Lo usan dashboard.html, training_plan.html y detalle.html: la misma
 * actividad da el mismo valor en las tres paginas.
 * Semantica honesta: si faltan FTP / FCmax / FC reales devuelve null (la UI
 * OMITE el TSS; nunca 0 ni un estimado disfrazado). Sin valores por defecto.
 * El TSS del servidor (a.tss) manda siempre sobre el estimado.
 * Fuerza: sRPE (RPE x min / 6) SOLO con RPE reportado; sin RPE => null.
 */
(function (root) {
  'use strict';

  function isStrength(sport) {
    return sport === 'gym' || sport === 'str' || sport === 'strength';
  }

  function pos(n) {
    n = Number(n);
    return isFinite(n) && n > 0 ? n : null;
  }

  // ctx opcional: { ftp, fcmax, rpeByDate }. Por defecto lee los globals
  // window._athleteFTP / _athleteFCMax / _strengthRpeByDate al momento de llamar.
  function estimate(a, ctx) {
    if (!a) return null;
    ctx = ctx || {};
    var g = root || {};
    var ftp = pos(ctx.ftp != null ? ctx.ftp : g._athleteFTP);
    var fcmax = pos(ctx.fcmax != null ? ctx.fcmax : g._athleteFCMax);
    if (a.tss) return Math.round(a.tss);
    var dur = pos(a.dur_min);
    if (isStrength(a.sport)) {
      var byDate = ctx.rpeByDate || g._strengthRpeByDate || {};
      var rpe = byDate[a.date_iso];
      if (rpe == null || !pos(rpe) || !dur) return null;
      return Math.round((Number(rpe) * dur) / 6);
    }
    if (!dur) return null;
    var h = dur / 60;
    var IF;
    var avgPower = pos(a.avg_power);
    var avgHr = pos(a.avg_hr);
    if (a.sport === 'bike' && avgPower && ftp) IF = avgPower / ftp;
    else if (!avgHr || !fcmax) return null;
    else if (a.sport === 'bike') IF = avgHr / (0.88 * fcmax);
    else if (a.sport === 'run') IF = avgHr / (0.89 * fcmax);
    else if (a.sport === 'swim') IF = avgHr / (0.82 * fcmax);
    else IF = avgHr / (0.75 * fcmax);
    return Math.round(h * Math.pow(Math.min(1.25, Math.max(0.4, IF)), 2) * 100);
  }

  var api = { estimate: estimate, isStrength: isStrength };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.LXTss = api;
})(
  typeof window !== 'undefined'
    ? window
    : typeof globalThis !== 'undefined'
      ? globalThis
      : this,
);
