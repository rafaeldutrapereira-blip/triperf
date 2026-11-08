/* lx-estado-ball.js (CQ8) — la "pelota" del Estado de hoy, una sola vez.
   Compartido por athlete-app.html (Hoy), dashboard.html (tarjeta Insight) y estado.html
   (traduccion). Lee el veredicto de GET /athlete/estado-hoy SIN cambiar su contrato:
   el semaforo sigue siendo el peor de Recuperacion y Mental.

   - LXEstadoBall.text(v)   -> {label, text, govName, other:{name,score,sev}|null, score, sev, pct}
     Etiqueta y frase salen de claves i18n por nivel (ment_level_*, mentmsg_mfs_*) en el idioma
     activo; el backend las manda siempre en espanol.
   - LXEstadoBall.render(el, v, opts) pinta anillo SVG proporcional (score/100) + numero +
     rotulo del indicador que manda (+ el otro como secundario si opts.other !== false).
   - LXEstadoBall.arc(score) -> {circ, offset, pct} (geometria del arco, r=58). */
(function () {
  'use strict';
  var COLORS = ['#10B981', '#F0A500', '#EF4444'];
  var R = 58;
  var CIRC = 364; /* mismo valor que estado.html (2*pi*58 ~ 364.4) */

  function tr(key, fb) {
    var v = window.i18n && window.i18n.t ? window.i18n.t(key) : null;
    return v && v !== key ? v : fb;
  }
  function be(s) {
    return window.lxBeT ? window.lxBeT(s || '') : s || '';
  }
  function num(x) {
    return x !== null && x !== undefined && isFinite(x);
  }
  function arc(score) {
    var pct = Math.max(0, Math.min(100, num(score) ? Number(score) : 0));
    return { circ: CIRC, offset: CIRC - (pct / 100) * CIRC, pct: pct };
  }
  function ok(v) {
    return !!(v && v.status === 'ok' && (v.sev === 0 || v.sev === 1 || v.sev === 2) && num(v.score) && (v.governs === 'rec' || v.governs === 'men'));
  }
  function names() {
    return { rec: tr('nav_recovery', 'Recuperación'), men: tr('nav_mental', 'Mental') };
  }

  function text(v) {
    if (!ok(v)) return null;
    var n = names();
    var gov = v.governs;
    var part = gov === 'men' ? v.mental : v.recovery;
    var level = (part && part.level) || '';
    var label, body;
    if (gov === 'men' && level) {
      label = tr('ment_level_' + level, be(v.label));
      body = tr('mentmsg_mfs_' + level, be(v.text));
    } else {
      label = be(v.label);
      body = be(v.text);
    }
    var otherKey = gov === 'men' ? 'rec' : 'men';
    var otherPart = otherKey === 'rec' ? v.recovery : v.mental;
    var other = otherPart && num(otherPart.score) ? { name: n[otherKey], score: Math.round(otherPart.score), sev: otherPart.sev } : null;
    var score = Math.round(v.score);
    return { label: label, text: body, govName: n[gov], gov: gov, other: other, score: score, sev: v.sev, pct: arc(score).pct };
  }

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  /* HTML de la pelota. opts.size = px (default 64); opts.other=false oculta el secundario. */
  function html(v, opts) {
    opts = opts || {};
    var size = opts.size || 64;
    var d = text(v);
    var col = d ? COLORS[d.sev] : '#9CA3AF';
    var a = arc(d ? d.score : 0);
    var big = size >= 100;
    var h =
      '<span class="lxb-dial" style="position:relative;display:inline-block;width:' + size + 'px;height:' + size + 'px;flex-shrink:0">' +
      '<svg viewBox="0 0 140 140" width="' + size + '" height="' + size + '" aria-hidden="true">' +
      '<circle cx="70" cy="70" r="' + R + '" fill="none" stroke="rgba(148,163,184,.25)" stroke-width="12"/>' +
      '<circle class="lxb-ring" cx="70" cy="70" r="' + R + '" fill="none" stroke="' + col + '" stroke-width="12" stroke-linecap="round"' +
      ' stroke-dasharray="' + a.circ + '" stroke-dashoffset="' + (d ? a.offset : a.circ) + '" data-pct="' + (d ? a.pct : 0) + '" transform="rotate(-90 70 70)"/>' +
      '</svg>' +
      '<span class="lxb-in" style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1">' +
      '<span class="lxb-n" style="font-family:Oswald,sans-serif;font-weight:700;font-size:' + (big ? 2.6 : size * 0.3 / 16) + 'rem;color:' + col + '">' + (d ? d.score : '—') + '</span>' +
      (d && size >= 56
        ? '<span class="lxb-l" style="font-family:Oswald,sans-serif;font-weight:700;font-size:' + (big ? 0.6 : 0.42) + 'rem;letter-spacing:.08em;text-transform:uppercase;color:var(--lxt-94a3b8,#94a3b8);margin-top:.1rem;max-width:' + (size - 10) + 'px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(d.govName) + '</span>'
        : '') +
      '</span></span>';
    return h;
  }

  /* Pinta la pelota (y opcionalmente el secundario) dentro de `el`. */
  function render(el, v, opts) {
    if (!el) return null;
    opts = opts || {};
    var d = text(v);
    el.innerHTML = html(v, opts);
    if (d && d.other && opts.other !== false) {
      var s = document.createElement('span');
      s.className = 'lxb-other';
      s.style.cssText = 'display:block;font-size:.72rem;color:var(--lxt-94a3b8,#94a3b8);margin-top:.2rem';
      s.textContent = d.other.name + ' ' + d.other.score;
      el.appendChild(s);
    }
    return d;
  }

  window.LXEstadoBall = { text: text, html: html, render: render, arc: arc, COLORS: COLORS, ok: ok };
})();
