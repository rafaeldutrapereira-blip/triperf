import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open('C:/Users/rafae/projects/LabX/training_detail.html', encoding='utf-8') as f:
    c = f.read()

# ── 1. Replace pool CSS ───────────────────────────────────────────────────────
OLD_POOL_CSS = """.pool-wrap{padding:1.5rem 2rem;background:var(--surface)}
.pool-svg{display:block;width:100%;max-height:260px}"""

NEW_POOL_CSS = """.pool-wrap{position:relative;background:var(--surface);border-radius:var(--radius);overflow:hidden}
.pool-canvas{display:block;width:100%;height:280px;cursor:default}
.pool-meta{position:absolute;bottom:10px;left:14px;display:flex;gap:.6rem;align-items:center;flex-wrap:wrap}
.pool-chip{background:rgba(4,8,15,.82);border:1px solid rgba(14,165,233,.28);border-radius:5px;
  padding:.22rem .6rem;font-family:'Oswald',sans-serif;font-size:.65rem;color:#0ea5e9;letter-spacing:.08em;
  backdrop-filter:blur(6px)}
.pool-replay{position:absolute;bottom:10px;right:12px;background:rgba(4,8,15,.88);
  border:1px solid rgba(14,165,233,.35);border-radius:6px;padding:.3rem .65rem;
  font-family:'Oswald',sans-serif;font-size:.63rem;font-weight:600;letter-spacing:.1em;
  color:#0ea5e9;cursor:pointer;backdrop-filter:blur(6px);transition:background .15s}
.pool-replay:hover{background:rgba(14,165,233,.18)}"""

if OLD_POOL_CSS in c:
    c = c.replace(OLD_POOL_CSS, NEW_POOL_CSS, 1)
    print('OK pool CSS')
else:
    print('MISS pool CSS')

# ── 2. Replace static pool SVG render with animated canvas ───────────────────
OLD_POOL_JS = """  if(cfg.type==='pool'){
    // SVG pool visualization
    var numLanes = ACT.dist_km ? Math.max(2, Math.ceil(ACT.dist_km*10/50)) : 8;
    var laneH = 28, laneW = 700, padX = 60, padY = 30;
    var svgH   = numLanes*laneH + padY*2;
    var svgW   = laneW + padX*2;
    var svg    = '<svg class="pool-svg" viewBox="0 0 '+svgW+' '+svgH+'" xmlns="http://www.w3.org/2000/svg">';
    svg += '<rect width="'+svgW+'" height="'+svgH+'" fill="var(--surface)"/>';
    svg += '<rect x="'+padX+'" y="'+padY+'" width="'+laneW+'" height="'+(numLanes*laneH)+'" rx="4" fill="rgba(14,165,233,.08)" stroke="rgba(14,165,233,.18)" stroke-width="1.5"/>';
    for(var li=0;li<=numLanes;li++){
      var ly = padY + li*laneH;
      svg += '<line x1="'+padX+'" y1="'+ly+'" x2="'+(padX+laneW)+'" y2="'+ly+'" stroke="rgba(14,165,233,.15)" stroke-width="1"/>';
    }
    // Swimmer path animation
    for(var si=0;si<Math.min(numLanes,4);si++){
      var sy = padY + si*laneH + laneH/2;
      var goRight = si%2===0;
      var x1 = padX+8, x2 = padX+laneW-8;
      svg += '<line x1="'+(goRight?x1:x2)+'" y1="'+sy+'" x2="'+(goRight?x2:x1)+'" y2="'+sy+'" stroke="var(--cyan)" stroke-width="2" stroke-dasharray="6 4" opacity="0.6"/>';
      svg += '<circle cx="'+(goRight?x2:x1)+'" cy="'+sy+'" r="5" fill="var(--cyan)" opacity="0.8"/>';
    }
    svg += '<text x="'+(padX-8)+'" y="'+(padY+laneH/2+4)+'" text-anchor="end" fill="var(--dim)" font-size="9" font-family="Oswald,sans-serif">25m</text>';
    if(ACT.dist_km){
      var totalLaps = Math.round(ACT.dist_km*1000/25);
      svg += '<text x="'+(padX+laneW/2)+'" y="'+(svgH-8)+'" text-anchor="middle" fill="var(--muted)" font-size="10" font-family="Oswald,sans-serif" letter-spacing="1">'+totalLaps+' LARGOS · '+(ACT.dist_km*1000).toFixed(0)+'m TOTAL</text>';
    }
    svg += '</svg>';
    mapWrap.innerHTML = '<div class="pool-wrap">'+svg+'</div>';
    return;
  }"""

NEW_POOL_JS = r"""  if(cfg.type==='pool'){
    var poolLen  = 25; // metres per lap
    var distM    = ACT.dist_km ? ACT.dist_km * 1000 : 1000;
    var totalLaps= Math.round(distM / poolLen);
    var numLanes = Math.max(4, Math.min(8, Math.ceil(totalLaps / 2)));

    mapWrap.innerHTML =
      '<div class="pool-wrap">' +
        '<canvas class="pool-canvas" id="pool-cv"></canvas>' +
        '<div class="pool-meta">' +
          '<span class="pool-chip">🏊 ' + totalLaps + ' largos</span>' +
          '<span class="pool-chip">📏 ' + (distM).toFixed(0) + ' m</span>' +
          (ACT.avg_hr ? '<span class="pool-chip">❤️ ' + ACT.avg_hr + ' bpm</span>' : '') +
          (ACT.swolf  ? '<span class="pool-chip">SWOLF ' + ACT.swolf + '</span>' : '') +
        '</div>' +
        '<button class="pool-replay" id="pool-replay">▶ REPLAY</button>' +
      '</div>';

    var cv  = document.getElementById('pool-cv');
    var ctx = cv.getContext('2d');
    var W, H, padX, padY, laneW, laneH;

    function resizeCanvas(){
      var wrap = cv.parentElement;
      W = wrap.offsetWidth || 700;
      H = 280;
      cv.width  = W;
      cv.height = H;
      padX  = 52;
      padY  = 28;
      laneW = W - padX * 2;
      laneH = (H - padY * 2 - 24) / numLanes;
    }
    resizeCanvas();

    /* ── Water shimmer wave offsets (pre-computed) ── */
    var waveT = 0;

    /* ── Swimmer shape drawn with canvas paths ── */
    function drawSwimmer(x, y, dir, alpha) {
      // dir: 1 = right, -1 = left
      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.translate(x, y);
      ctx.scale(dir, 1);

      var sw = 0.65; // scale

      // Body
      ctx.beginPath();
      ctx.ellipse(0, 0, 16 * sw, 5 * sw, -0.18, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(224,242,254,.92)';
      ctx.fill();

      // Head
      ctx.beginPath();
      ctx.arc(18 * sw, -1, 5 * sw, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(251,207,143,.95)';
      ctx.fill();

      // Cap
      ctx.beginPath();
      ctx.ellipse(18 * sw, -3 * sw, 5 * sw, 3.5 * sw, -0.2, Math.PI, Math.PI * 2);
      ctx.fillStyle = '#0ea5e9';
      ctx.fill();

      // Goggle
      ctx.beginPath();
      ctx.arc(22 * sw, 0, 2 * sw, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(14,165,233,.7)';
      ctx.fill();

      // Extended arm (forward)
      ctx.beginPath();
      ctx.moveTo(14 * sw, -3 * sw);
      ctx.quadraticCurveTo(22 * sw, -9 * sw, 30 * sw, -4 * sw);
      ctx.strokeStyle = 'rgba(224,242,254,.85)';
      ctx.lineWidth = 3 * sw;
      ctx.lineCap = 'round';
      ctx.stroke();

      // Pull arm (behind)
      ctx.beginPath();
      ctx.moveTo(-8 * sw, 2 * sw);
      ctx.quadraticCurveTo(-14 * sw, 8 * sw, -6 * sw, 13 * sw);
      ctx.strokeStyle = 'rgba(224,242,254,.65)';
      ctx.lineWidth = 2.5 * sw;
      ctx.stroke();

      // Kick legs
      ctx.beginPath();
      ctx.moveTo(-14 * sw, 0);
      ctx.lineTo(-22 * sw, -6 * sw);
      ctx.moveTo(-14 * sw, 0);
      ctx.lineTo(-22 * sw, 5 * sw);
      ctx.strokeStyle = 'rgba(224,242,254,.55)';
      ctx.lineWidth = 2 * sw;
      ctx.stroke();

      ctx.restore();
    }

    /* ── Draw pool frame ── */
    function drawPool(swimmerLap, lapProgress) {
      ctx.clearRect(0, 0, W, H);

      // Background
      var bg = ctx.createLinearGradient(0, 0, 0, H);
      bg.addColorStop(0,   '#04080F');
      bg.addColorStop(0.5, '#061220');
      bg.addColorStop(1,   '#04080F');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, W, H);

      // Pool water body
      var waterGrad = ctx.createLinearGradient(padX, padY, padX, padY + numLanes * laneH);
      waterGrad.addColorStop(0,   'rgba(7,40,80,.55)');
      waterGrad.addColorStop(0.5, 'rgba(10,55,100,.65)');
      waterGrad.addColorStop(1,   'rgba(7,40,80,.55)');
      ctx.fillStyle = waterGrad;
      ctx.beginPath();
      ctx.roundRect(padX, padY, laneW, numLanes * laneH, 6);
      ctx.fill();

      // Lane ropes
      for (var li = 0; li <= numLanes; li++) {
        var ly = padY + li * laneH;
        var isEdge = li === 0 || li === numLanes;

        // Rope line
        ctx.beginPath();
        ctx.moveTo(padX, ly);
        ctx.lineTo(padX + laneW, ly);
        ctx.strokeStyle = isEdge ? 'rgba(14,165,233,.55)' : 'rgba(14,165,233,.22)';
        ctx.lineWidth = isEdge ? 2 : 1;
        ctx.stroke();

        // Float beads every 14px
        if (!isEdge) {
          for (var fx = padX + 7; fx < padX + laneW - 5; fx += 14) {
            ctx.beginPath();
            ctx.arc(fx, ly, 2.2, 0, Math.PI * 2);
            ctx.fillStyle = li % 2 === 0 ? 'rgba(14,165,233,.45)' : 'rgba(255,101,53,.38)';
            ctx.fill();
          }
        }
      }

      // Water shimmer lines (horizontal)
      waveT += 0.018;
      for (var wi = 0; wi < numLanes; wi++) {
        var wy = padY + wi * laneH + laneH * 0.55;
        var wAlpha = 0.04 + 0.03 * Math.sin(waveT + wi * 1.3);
        ctx.beginPath();
        for (var wx = padX; wx < padX + laneW; wx += 3) {
          var woff = Math.sin(wx * 0.04 + waveT + wi) * 2.5;
          if (wx === padX) ctx.moveTo(wx, wy + woff);
          else ctx.lineTo(wx, wy + woff);
        }
        ctx.strokeStyle = 'rgba(14,165,233,' + wAlpha + ')';
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // Lane numbers (left wall)
      for (var ln = 0; ln < numLanes; ln++) {
        var lny = padY + ln * laneH + laneH / 2 + 4;
        ctx.font = '600 9px Oswald,sans-serif';
        ctx.fillStyle = 'rgba(14,165,233,.4)';
        ctx.textAlign = 'center';
        ctx.fillText(ln + 1, padX - 18, lny);
      }

      // Pool length label
      ctx.font = '700 9px Oswald,sans-serif';
      ctx.fillStyle = 'rgba(14,165,233,.45)';
      ctx.textAlign = 'center';
      ctx.letterSpacing = '1px';
      ctx.fillText('25 m', padX + laneW / 2, padY - 10);

      // Wall tiles (left & right)
      var tileColors = ['rgba(14,165,233,.25)','rgba(8,100,160,.25)'];
      for (var ti = 0; ti < numLanes; ti++) {
        var ty = padY + ti * laneH;
        ctx.fillStyle = tileColors[ti % 2];
        ctx.fillRect(padX - 10, ty, 10, laneH);
        ctx.fillRect(padX + laneW, ty, 10, laneH);
      }

      // ── Swimmer wake trail ──
      var swimLane = swimmerLap % numLanes;
      var goRight  = swimmerLap % 2 === 0;
      var swimY    = padY + swimLane * laneH + laneH / 2;
      var x0 = padX + (goRight ? 0 : laneW);
      var x1 = padX + (goRight ? laneW : 0);
      var swimX = x0 + (x1 - x0) * lapProgress;

      // Trail (wake bubbles)
      var trailLen = 60;
      for (var ti2 = 0; ti2 < 8; ti2++) {
        var tx = swimX + (goRight ? -1 : 1) * (ti2 * 8 + 4);
        var tAlpha = (1 - ti2 / 8) * 0.35;
        if (tx < padX || tx > padX + laneW) continue;
        ctx.beginPath();
        ctx.arc(tx, swimY + (Math.random() > 0.5 ? 3 : -3), 1.5, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(186,230,253,' + tAlpha + ')';
        ctx.fill();
      }

      // Dashed trail line
      ctx.beginPath();
      ctx.setLineDash([4, 5]);
      var trailStart = swimX + (goRight ? -trailLen : trailLen);
      trailStart = Math.max(padX, Math.min(padX + laneW, trailStart));
      ctx.moveTo(trailStart, swimY);
      ctx.lineTo(swimX, swimY);
      ctx.strokeStyle = 'rgba(14,165,233,.35)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.setLineDash([]);

      // ── Completed lanes (full trace) ──
      for (var cl = 0; cl < swimmerLap; cl++) {
        var clY    = padY + (cl % numLanes) * laneH + laneH / 2;
        var clDir  = cl % 2 === 0;
        ctx.beginPath();
        ctx.moveTo(padX + (clDir ? 8 : laneW - 8), clY);
        ctx.lineTo(padX + (clDir ? laneW - 8 : 8), clY);
        ctx.strokeStyle = 'rgba(14,165,233,.18)';
        ctx.lineWidth = 2;
        ctx.stroke();
        // End dot
        ctx.beginPath();
        ctx.arc(padX + (clDir ? laneW - 6 : 6), clY, 3, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(14,165,233,.3)';
        ctx.fill();
      }

      // ── Draw swimmer ──
      drawSwimmer(swimX, swimY, goRight ? 1 : -1, 1);

      // Lap counter (top right)
      var lapsDone = swimmerLap;
      ctx.font = '700 11px Oswald,sans-serif';
      ctx.fillStyle = 'rgba(14,165,233,.7)';
      ctx.textAlign = 'right';
      ctx.fillText('LARGO ' + (lapsDone + 1) + ' / ' + totalLaps, padX + laneW, padY - 10);
    }

    /* ── Animation loop ── */
    var ANIM_DUR = Math.min(18000, Math.max(8000, totalLaps * 260));
    var animStart = null, animRAF = null;

    function easeInOut(t){ return t < .5 ? 2*t*t : -1+(4-2*t)*t; }

    function frame(ts) {
      if (!animStart) animStart = ts;
      var raw  = Math.min(1, (ts - animStart) / ANIM_DUR);
      var prog = raw; // linear across total laps
      var totalProg = prog * totalLaps;
      var curLap    = Math.min(totalLaps - 1, Math.floor(totalProg));
      var lapProg   = totalProg - curLap;

      drawPool(curLap, lapProg);

      if (raw < 1) {
        animRAF = requestAnimationFrame(frame);
      } else {
        // Show completed state
        drawPool(totalLaps - 1, 1);
      }
    }

    function startAnim() {
      if (animRAF) cancelAnimationFrame(animRAF);
      animStart = null;
      animRAF = requestAnimationFrame(frame);
    }

    document.getElementById('pool-replay').addEventListener('click', startAnim);

    // Handle resize
    window.addEventListener('resize', function(){
      resizeCanvas();
    });

    startAnim();
    return;
  }"""

if OLD_POOL_JS in c:
    c = c.replace(OLD_POOL_JS, NEW_POOL_JS, 1)
    print('OK pool JS replaced')
else:
    print('MISS pool JS — checking first line')
    first = "  if(cfg.type==='pool'){"
    idx = c.find(first)
    print(f'  first line at: {idx}')

with open('C:/Users/rafae/projects/LabX/training_detail.html', 'w', encoding='utf-8') as f:
    f.write(c)
print('Saved training_detail.html')
