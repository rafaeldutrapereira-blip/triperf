/*
 * workout-blocks.js — Motor compartido de bloques de entrenamiento estructurado
 * (warmup/steady/intervals/ramp/freeride/cooldown), usado por coach.html
 * (asignación a atletas) e indoor_workout.html (builder de autoservicio).
 *
 * Por qué existe: ambas páginas implementaban el mismo modelo de datos y el
 * mismo generador de .zwo/.erg/.mrc por separado, sin ninguna relación entre
 * sí — cualquier cambio (un tipo de bloque nuevo, un fix en el XML) había que
 * hacerlo dos veces, y ya habían empezado a divergir en detalles menores
 * (labels, colores). Este archivo es la única fuente de verdad.
 *
 * Formato "wire" de un bloque (el que se guarda en blocks_json y el que usa
 * este módulo): duración siempre en SEGUNDOS, potencia siempre como fracción
 * de FTP 0..1 (no porcentaje 0..100). coach.html convierte sus inputs en
 * unidades más cómodas (minutos, % FTP) a este formato recién al guardar —
 * ver _mwGetBlocksJson() en coach.html.
 */
(function (global) {
  'use strict';

  var WORKOUT_BLOCK_TYPES = {
    warmup:    { label: 'Calentamiento', color: '#64B5F6', zwotag: 'Warmup',      hasRepeat: false, hasRamp: true  },
    steady:    { label: 'Steady State',  color: '#0EA5E9', zwotag: 'SteadyState', hasRepeat: false, hasRamp: false },
    intervals: { label: 'Intervalos',    color: '#EF4444', zwotag: 'IntervalsT',  hasRepeat: true,  hasRamp: false },
    ramp:      { label: 'Ramp',          color: '#10B981', zwotag: 'Ramp',        hasRepeat: false, hasRamp: true  },
    freeride:  { label: 'Free Ride',     color: '#A855F7', zwotag: 'FreeRide',    hasRepeat: false, hasRamp: false },
    cooldown:  { label: 'Vuelta Calma',  color: '#64B5F6', zwotag: 'Cooldown',    hasRepeat: false, hasRamp: true  },
  };

  function makeBlock(type, id) {
    switch (type) {
      case 'warmup':
      case 'cooldown':
        return { id: id, type: type, duration: 600, power_low: 0.50, power_high: 0.75 };
      case 'ramp':
        return { id: id, type: type, duration: 600, power_low: 0.60, power_high: 1.00 };
      case 'intervals':
        return { id: id, type: type, repeat: 4, on_duration: 240, on_power: 0.95, off_duration: 120, off_power: 0.55 };
      case 'freeride':
        return { id: id, type: type, duration: 300 };
      default: // steady
        return { id: id, type: 'steady', duration: 300, power: 0.75 };
    }
  }

  function totalBlockDuration(b) {
    if (b.type === 'intervals') return b.repeat * (b.on_duration + b.off_duration);
    return b.duration || 0;
  }

  function blockSummaryText(b, fmtDurFn) {
    var d = fmtDurFn ? fmtDurFn(totalBlockDuration(b)) : totalBlockDuration(b) + 's';
    switch (b.type) {
      case 'warmup':
      case 'cooldown':
      case 'ramp':
        return d + ' · ' + Math.round(b.power_low * 100) + '%→' + Math.round(b.power_high * 100) + '% FTP';
      case 'steady':
        return d + ' · ' + Math.round(b.power * 100) + '% FTP';
      case 'intervals':
        return b.repeat + '×(' + (fmtDurFn ? fmtDurFn(b.on_duration) : b.on_duration + 's') + ' @ ' + Math.round(b.on_power * 100) +
               '% / ' + (fmtDurFn ? fmtDurFn(b.off_duration) : b.off_duration + 's') + ' @ ' + Math.round(b.off_power * 100) + '%)';
      case 'freeride':
        return d + ' · Intensidad libre';
    }
    return d;
  }

  // Aplana los bloques a una lista de segmentos {ts, te, ps, pe} (tiempo
  // inicio/fin en segundos, potencia inicio/fin como fracción de FTP) —
  // usado para generar .erg/.mrc, que necesitan puntos minuto-a-minuto en
  // vez de la estructura por bloques.
  function buildSegments(blocks) {
    var segs = [];
    var t = 0;
    blocks.forEach(function (b) {
      switch (b.type) {
        case 'warmup': case 'cooldown': case 'ramp':
          segs.push({ ts: t, te: t + b.duration, ps: b.power_low, pe: b.power_high });
          t += b.duration;
          break;
        case 'steady':
          segs.push({ ts: t, te: t + b.duration, ps: b.power, pe: b.power });
          t += b.duration;
          break;
        case 'freeride':
          segs.push({ ts: t, te: t + b.duration, ps: 0.65, pe: 0.65, free: true });
          t += b.duration;
          break;
        case 'intervals':
          for (var r = 0; r < b.repeat; r++) {
            segs.push({ ts: t, te: t + b.on_duration, ps: b.on_power, pe: b.on_power });
            t += b.on_duration;
            segs.push({ ts: t, te: t + b.off_duration, ps: b.off_power, pe: b.off_power });
            t += b.off_duration;
          }
          break;
      }
    });
    return segs;
  }

  function _escXml(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Réplica exacta (mismo algoritmo, mismos tags) de generate_zwo_bytes() en
  // api/workout_delivery.py — esa versión Python corre server-side para el
  // email de entrega automática; esta corre client-side para la descarga
  // instantánea de indoor_workout.html. Dos runtimes, un solo algoritmo:
  // si se cambia acá, cambiar también allá (y viceversa).
  function blocksToZwoXml(blocks, name, description) {
    var lines = [
      '<?xml version="1.0" encoding="utf-8"?>',
      '<workout_file>',
      '  <author>LabX Coach</author>',
      '  <name>' + _escXml(name) + '</name>',
      '  <description>' + _escXml(description || name) + '</description>',
      '  <sportType>bike</sportType>',
      '  <tags/>',
      '  <workout>',
    ];
    blocks.forEach(function (b) {
      switch (b.type) {
        case 'warmup':
          lines.push('    <Warmup Duration="' + b.duration + '" PowerLow="' + b.power_low.toFixed(2) + '" PowerHigh="' + b.power_high.toFixed(2) + '"/>');
          break;
        case 'cooldown':
          lines.push('    <Cooldown Duration="' + b.duration + '" PowerLow="' + b.power_high.toFixed(2) + '" PowerHigh="' + b.power_low.toFixed(2) + '"/>');
          break;
        case 'steady':
          lines.push('    <SteadyState Duration="' + b.duration + '" Power="' + b.power.toFixed(2) + '"/>');
          break;
        case 'intervals':
          lines.push('    <IntervalsT Repeat="' + b.repeat + '" OnDuration="' + b.on_duration + '" OffDuration="' + b.off_duration +
                      '" OnPower="' + b.on_power.toFixed(2) + '" OffPower="' + b.off_power.toFixed(2) + '" pace="0"/>');
          break;
        case 'ramp':
          lines.push('    <Ramp Duration="' + b.duration + '" PowerLow="' + b.power_low.toFixed(2) + '" PowerHigh="' + b.power_high.toFixed(2) + '"/>');
          break;
        case 'freeride':
          lines.push('    <FreeRide Duration="' + b.duration + '" FlatRoad="0"/>');
          break;
      }
    });
    lines.push('  </workout>', '</workout_file>');
    return lines.join('\n');
  }

  function blocksToErgText(blocks, name, ftp) {
    var segs = buildSegments(blocks);
    var points = [];
    segs.forEach(function (s) {
      var dur = (s.te - s.ts) / 60;
      var w1 = (s.free ? 0.65 : s.ps) * ftp;
      var w2 = (s.free ? 0.65 : s.pe) * ftp;
      if (!points.length) points.push([0, Math.round(w1)]);
      var t = s.ts / 60;
      points.push([parseFloat(t.toFixed(3)), Math.round(w1)]);
      points.push([parseFloat((t + dur).toFixed(3)), Math.round(w2)]);
    });
    var header = '[COURSE HEADER]\r\nDESCRIPTION = ' + name + '\r\nFILE NAME = ' + name + '\r\nMINUTES WATTS\r\n[END COURSE HEADER]\r\n[COURSE DATA]\r\n';
    return header + points.map(function (p) { return p[0] + '\t' + p[1]; }).join('\r\n') + '\r\n[END COURSE DATA]';
  }

  function blocksToMrcText(blocks, name, ftp) {
    var segs = buildSegments(blocks);
    var points = [];
    segs.forEach(function (s) {
      var t = s.ts / 60;
      var dur = (s.te - s.ts) / 60;
      var p1 = Math.round((s.free ? 0.65 : s.ps) * 100);
      var p2 = Math.round((s.free ? 0.65 : s.pe) * 100);
      if (!points.length) points.push([0, p1]);
      points.push([parseFloat(t.toFixed(3)), p1]);
      points.push([parseFloat((t + dur).toFixed(3)), p2]);
    });
    var header = '[COURSE HEADER]\r\nDESCRIPTION = ' + name + '\r\nFILE NAME = ' + name + '\r\nMINUTES PERCENT\r\n[END COURSE HEADER]\r\n[COURSE DATA]\r\n';
    return header + points.map(function (p) { return p[0] + '\t' + p[1]; }).join('\r\n') + '\r\n[END COURSE DATA]';
  }

  // Color por intensidad relativa (0..~1.2) — mismo criterio que
  // indoor_workout.html usa para la curva de potencia de bici, generalizado
  // acá para reusarlo también en las curvas de carrera/natación de coach.html.
  function zoneColor(pct) {
    if (pct < 0.55) return '#64B5F6';
    if (pct < 0.75) return '#0EA5E9';
    if (pct < 0.90) return '#10B981';
    if (pct < 1.05) return '#FF6535';
    if (pct < 1.20) return '#EF4444';
    return '#A855F7';
  }

  // Dibuja una curva de intensidad (área apilada por bloque) a partir de
  // segmentos {ts, te, ps, pe[, free]} — mismo tipo de dato que buildSegments()
  // devuelve para bici. El eje X puede ser tiempo (segundos) o distancia
  // (metros); opts.xFmt define cómo se formatean las etiquetas del eje.
  // Devuelve un string SVG listo para insertar en innerHTML — sin depender
  // de ningún elemento del DOM, así sirve igual para bici (indoor_workout.html
  // ya tenía su propia versión probada) como para carrera/natación (coach.html).
  function renderCurveSvg(segments, opts) {
    opts = opts || {};
    var W = opts.width || 800, H = opts.height || 140;
    var padB = opts.padBottom != null ? opts.padBottom : 20;
    var padT = opts.padTop != null ? opts.padTop : 8;
    var xFmt = opts.xFmt || function (v) { return String(Math.round(v)); };
    var xStep = opts.xStep;
    var refLine = opts.refLine; // {value, label, color}

    if (!segments || !segments.length) {
      return '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:' + H + 'px;display:block">' +
        '<text x="' + (W / 2) + '" y="' + (H / 2) + '" text-anchor="middle" fill="#3D6880" font-family="Oswald,sans-serif" font-size="11" letter-spacing="2">SIN BLOQUES</text></svg>';
    }

    var totalX = segments[segments.length - 1].te;
    if (!totalX) totalX = 1;
    var chartH = H - padB - padT;
    var maxY = Math.max(1.25, Math.max.apply(null, segments.map(function (s) { return Math.max(s.ps, s.pe); })) * 1.1);

    function xOf(v) { return (v / totalX) * W; }
    function yOf(v) { return padT + chartH * (1 - Math.min(v, maxY) / maxY); }

    var paths = '';
    segments.forEach(function (s) {
      var x1 = xOf(s.ts), x2 = xOf(s.te), y1 = yOf(s.ps), y2 = yOf(s.pe);
      var col = s.free ? '#A855F7' : zoneColor((s.ps + s.pe) / 2);
      var bottom = padT + chartH;
      paths += '<polygon points="' + x1 + ',' + bottom + ' ' + x1 + ',' + y1 + ' ' + x2 + ',' + y2 + ' ' + x2 + ',' + bottom + '" fill="' + col + '" opacity="0.75"/>';
    });

    var labels = '';
    var step = xStep || (totalX <= 3600 ? 600 : totalX <= 7200 ? 1800 : Math.ceil(totalX / 8));
    for (var v = 0; v <= totalX; v += step) {
      var lx = xOf(v);
      labels += '<text x="' + lx + '" y="' + (H - 4) + '" text-anchor="middle" fill="#3D6880" font-family="Oswald,sans-serif" font-size="9">' + xFmt(v) + '</text>';
    }
    if (refLine) {
      var ry = yOf(refLine.value);
      labels += '<line x1="0" y1="' + ry + '" x2="' + W + '" y2="' + ry + '" stroke="' + (refLine.color || 'rgba(255,101,53,.4)') + '" stroke-width="1" stroke-dasharray="4,3"/>';
      labels += '<text x="4" y="' + (ry - 3) + '" fill="' + (refLine.color || 'rgba(255,101,53,.7)') + '" font-family="Oswald,sans-serif" font-size="9">' + (refLine.label || '') + '</text>';
    }

    return '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:' + H + 'px;display:block">' + paths + labels + '</svg>';
  }

  global.WORKOUT_BLOCK_TYPES = WORKOUT_BLOCK_TYPES;
  global.WorkoutBlocks = {
    TYPES: WORKOUT_BLOCK_TYPES,
    makeBlock: makeBlock,
    totalBlockDuration: totalBlockDuration,
    blockSummaryText: blockSummaryText,
    buildSegments: buildSegments,
    blocksToZwoXml: blocksToZwoXml,
    blocksToErgText: blocksToErgText,
    blocksToMrcText: blocksToMrcText,
    zoneColor: zoneColor,
    renderCurveSvg: renderCurveSvg,
  };
})(window);
