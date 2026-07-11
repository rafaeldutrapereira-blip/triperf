import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open('C:/Users/rafae/projects/LabX/training_detail.html', encoding='utf-8') as f:
    c = f.read()

# ── 1. Update getActConfig to carry zwift world info ─────────────────────────
OLD_CFG = """function getActConfig(act){
  var nm = (act.name||'').toLowerCase();
  if(nm.indexOf('zwift')>=0)    return {type:'indoor', icon:'🖥️', location:'Zwift — Indoor Trainer'};
  if(nm.indexOf('piscina')>=0 || act.sport==='swim')
                                return {type:'pool',   icon:'🏊', location:'Piscina'};
  if(act.sport==='str')         return {type:'indoor', icon:'🏋️', location:'Gimnasio'};"""

NEW_CFG = """function zwiftWorld(nm){
  if(/watopia|volcano|alpe|epic|ocean|jungle|hilly|ven|sand|lutscher/i.test(nm)) return 'watopia';
  if(/london|greater|box.?hill|leith|surrey/i.test(nm)) return 'london';
  if(/new.?york|nyc|manhattan|central.?park/i.test(nm)) return 'new_york';
  if(/france|ventoux|casse/i.test(nm)) return 'france';
  if(/innsbruck|austria|ring/i.test(nm)) return 'innsbruck';
  if(/richmond/i.test(nm)) return 'richmond';
  if(/makuri|neokyo|urukazi/i.test(nm)) return 'makuri';
  return 'watopia'; // default
}
function getActConfig(act){
  var nm = (act.name||'').toLowerCase();
  if(nm.indexOf('zwift')>=0){
    var w = zwiftWorld(nm);
    return {type:'zwift', world:w, icon:'🖥️', location:'Zwift — Indoor Trainer'};
  }
  if(nm.indexOf('piscina')>=0 || act.sport==='swim')
                                return {type:'pool',   icon:'🏊', location:'Piscina'};
  if(act.sport==='str')         return {type:'indoor', icon:'🏋️', location:'Gimnasio'};"""

if OLD_CFG in c:
    c = c.replace(OLD_CFG, NEW_CFG, 1)
    print('OK getActConfig')
else:
    print('MISS getActConfig')

# ── 2. Add Zwift CSS alongside pool CSS ──────────────────────────────────────
OLD_POOL_CSS = """.pool-wrap{position:relative;background:var(--surface);border-radius:var(--radius);overflow:hidden}"""

NEW_POOL_CSS = """.pool-wrap{position:relative;background:var(--surface);border-radius:var(--radius);overflow:hidden}
.zwift-wrap{position:relative;background:#04080F;border-radius:var(--radius);overflow:hidden}
.zwift-canvas{display:block;width:100%;height:300px}
.zwift-overlay{position:absolute;top:10px;left:14px;display:flex;flex-direction:column;gap:.4rem}
.zwift-world-badge{display:inline-flex;align-items:center;gap:.4rem;
  background:rgba(4,8,15,.88);border:1px solid rgba(255,101,53,.38);border-radius:6px;
  padding:.28rem .7rem;font-family:'Barlow Condensed',sans-serif;font-size:.88rem;
  font-weight:700;letter-spacing:.04em;color:#FF6535;backdrop-filter:blur(8px)}
.zwift-stats{display:flex;gap:.45rem;flex-wrap:wrap}
.zwift-chip{background:rgba(4,8,15,.82);border:1px solid rgba(255,101,53,.22);border-radius:5px;
  padding:.22rem .58rem;font-family:'Oswald',sans-serif;font-size:.64rem;
  color:rgba(255,165,0,.9);letter-spacing:.07em;backdrop-filter:blur(6px)}
.zwift-replay{position:absolute;bottom:10px;right:12px;background:rgba(4,8,15,.88);
  border:1px solid rgba(255,101,53,.38);border-radius:6px;padding:.3rem .65rem;
  font-family:'Oswald',sans-serif;font-size:.63rem;font-weight:600;letter-spacing:.1em;
  color:#FF6535;cursor:pointer;backdrop-filter:blur(6px);transition:background .15s}
.zwift-replay:hover{background:rgba(255,101,53,.18)}"""

if OLD_POOL_CSS in c:
    c = c.replace(OLD_POOL_CSS, NEW_POOL_CSS, 1)
    print('OK Zwift CSS')
else:
    print('MISS Zwift CSS')

# ── 3. Replace indoor block with branch: zwift or generic indoor ─────────────
OLD_INDOOR = """  if(cfg.type==='indoor'){
    mapWrap.innerHTML =
      '<div class="indoor-card">'
      +'<div class="indoor-icon">'+cfg.icon+'</div>'
      +'<div class="indoor-label">'+cfg.location+'</div>'
      +'<div class="indoor-sub">'+(ACT.name||sp.label)+' · '+durStr+(ACT.dist_km?' · '+ACT.dist_km.toFixed(1)+' km':'')+'</div>'
      +'</div>';
    return;
  }"""

NEW_INDOOR = r"""  if(cfg.type==='zwift'){
    /* ── ZWIFT WORLD ROUTES (normalised 0..1 points) ── */
    var ZWIFT_ROUTES = {
      watopia: [
        [.12,.52],[.18,.44],[.26,.38],[.34,.34],[.44,.32],[.54,.33],[.62,.37],
        [.70,.42],[.76,.50],[.80,.58],[.82,.66],[.80,.74],[.76,.80],[.70,.84],
        [.62,.86],[.54,.85],[.48,.82],[.44,.78],[.42,.72],[.44,.66],[.48,.62],
        [.54,.60],[.60,.60],[.66,.62],[.70,.66],[.70,.72],[.68,.78],[.62,.82],
        [.54,.83],[.44,.82],[.38,.78],[.32,.72],[.26,.64],[.20,.56],[.12,.52]
      ],
      london: [
        [.18,.60],[.24,.50],[.32,.42],[.42,.36],[.52,.34],[.62,.36],[.70,.42],
        [.76,.50],[.78,.58],[.76,.66],[.70,.72],[.60,.76],[.52,.78],[.44,.76],
        [.36,.70],[.28,.64],[.22,.60],[.18,.60]
      ],
      new_york: [
        [.20,.65],[.22,.55],[.26,.46],[.32,.39],[.40,.34],[.50,.33],[.60,.36],
        [.68,.42],[.72,.50],[.74,.58],[.72,.65],[.68,.71],[.62,.76],[.54,.78],
        [.48,.76],[.42,.71],[.38,.64],[.36,.56],[.38,.50],[.42,.44],[.48,.40],
        [.54,.38],[.60,.40],[.64,.46],[.64,.54],[.60,.62],[.54,.68],[.46,.70],
        [.38,.68],[.30,.62],[.24,.56],[.20,.65]
      ],
      france: [
        [.14,.58],[.20,.48],[.28,.40],[.38,.35],[.50,.33],[.62,.36],[.72,.42],
        [.80,.50],[.84,.60],[.82,.70],[.76,.78],[.66,.83],[.56,.85],[.46,.83],
        [.36,.78],[.26,.70],[.18,.62],[.14,.58]
      ],
      innsbruck: [
        [.20,.60],[.26,.52],[.34,.45],[.44,.40],[.54,.38],[.64,.40],[.72,.46],
        [.78,.54],[.78,.62],[.74,.70],[.66,.76],[.56,.78],[.46,.76],[.36,.70],
        [.28,.64],[.20,.60]
      ],
      richmond: [
        [.22,.58],[.28,.50],[.36,.43],[.46,.38],[.56,.37],[.66,.40],[.74,.46],
        [.78,.54],[.78,.62],[.74,.68],[.66,.72],[.56,.74],[.46,.72],[.38,.66],
        [.32,.60],[.26,.58],[.22,.58]
      ],
      makuri: [
        [.16,.55],[.22,.46],[.30,.39],[.40,.34],[.52,.33],[.64,.36],[.73,.43],
        [.79,.52],[.82,.61],[.80,.70],[.74,.77],[.65,.82],[.55,.84],[.45,.82],
        [.37,.77],[.30,.70],[.24,.62],[.18,.57],[.16,.55]
      ]
    };
    var ZWIFT_NAMES = {
      watopia:'Watopia', london:'London', new_york:'New York',
      france:'France', innsbruck:'Innsbruck', richmond:'Richmond', makuri:'Makuri'
    };
    var ZWIFT_COLORS = {
      watopia:'#FF6535', london:'#10B981', new_york:'#F59E0B',
      france:'#8B5CF6', innsbruck:'#0ea5e9', richmond:'#EC4899', makuri:'#14B8A6'
    };

    var world   = cfg.world || 'watopia';
    var wColor  = ZWIFT_COLORS[world] || '#FF6535';
    var wName   = ZWIFT_NAMES[world] || 'Watopia';
    var wRoute  = ZWIFT_ROUTES[world] || ZWIFT_ROUTES.watopia;

    var np  = ACT.avg_power ? Math.round(ACT.avg_power * 1.07) : null;
    var ifv = np ? (np / (FTP||200)).toFixed(2) : null;

    mapWrap.innerHTML =
      '<div class="zwift-wrap">' +
        '<canvas class="zwift-canvas" id="zwift-cv"></canvas>' +
        '<div class="zwift-overlay">' +
          '<span class="zwift-world-badge">🖥️ ' + wName + '</span>' +
          '<div class="zwift-stats">' +
            (ACT.dist_km ? '<span class="zwift-chip">📍 '+ACT.dist_km.toFixed(1)+' km</span>' : '') +
            (ACT.avg_power ? '<span class="zwift-chip">⚡ '+ACT.avg_power+'W avg</span>' : '') +
            (np ? '<span class="zwift-chip">NP '+np+'W</span>' : '') +
            (ifv ? '<span class="zwift-chip">IF '+ifv+'</span>' : '') +
            (ACT.tss ? '<span class="zwift-chip">TSS '+ACT.tss+'</span>' : '') +
            (ACT.avg_hr ? '<span class="zwift-chip">❤️ '+ACT.avg_hr+' bpm</span>' : '') +
          '</div>' +
        '</div>' +
        '<button class="zwift-replay" id="zwift-replay">▶ REPLAY</button>' +
      '</div>';

    var cv  = document.getElementById('zwift-cv');
    var ctx = cv.getContext('2d');
    var W, H;

    function resizeZwift(){
      W = cv.parentElement.offsetWidth || 700;
      H = 300;
      cv.width  = W;
      cv.height = H;
    }
    resizeZwift();

    /* Scale route points to canvas */
    function scalePts(pts){
      var pad = 48;
      return pts.map(function(p){
        return [pad + p[0]*(W-pad*2), pad + p[1]*(H-pad*2)];
      });
    }

    /* Draw cyclist silhouette at position x,y facing dir (1=right,-1=left) */
    function drawCyclist(x, y, dir, wc){
      ctx.save();
      ctx.translate(x, y);
      ctx.scale(dir, 1);

      var s = 0.7;

      // rear wheel
      ctx.beginPath();
      ctx.arc(-10*s, 6*s, 8*s, 0, Math.PI*2);
      ctx.strokeStyle = wc;
      ctx.lineWidth = 2*s;
      ctx.stroke();
      // spokes
      for(var sp2=0; sp2<4; sp2++){
        var ang = (sp2/4)*Math.PI*2 + Date.now()*0.008 % (Math.PI*2);
        ctx.beginPath();
        ctx.moveTo(-10*s, 6*s);
        ctx.lineTo(-10*s + Math.cos(ang)*7*s, 6*s + Math.sin(ang)*7*s);
        ctx.strokeStyle = 'rgba(255,255,255,.3)';
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // front wheel
      ctx.beginPath();
      ctx.arc(10*s, 6*s, 8*s, 0, Math.PI*2);
      ctx.strokeStyle = wc;
      ctx.lineWidth = 2*s;
      ctx.stroke();

      // frame: bottom bracket
      ctx.beginPath();
      ctx.moveTo(-10*s, 6*s);   // rear dropout
      ctx.lineTo(0, 0);         // bottom bracket
      ctx.lineTo(10*s, 6*s);    // front dropout
      ctx.moveTo(0, 0);
      ctx.lineTo(-2*s, -14*s);  // seat tube
      ctx.lineTo(-10*s, 6*s);   // chain stay
      ctx.moveTo(-2*s, -14*s);  // top tube
      ctx.lineTo(9*s, -10*s);   // head tube
      ctx.moveTo(9*s, -10*s);
      ctx.lineTo(10*s, 6*s);    // fork
      ctx.strokeStyle = wc;
      ctx.lineWidth = 1.8*s;
      ctx.lineJoin = 'round';
      ctx.stroke();

      // handlebars (aero position)
      ctx.beginPath();
      ctx.moveTo(9*s, -10*s);
      ctx.lineTo(14*s, -12*s);
      ctx.lineTo(16*s, -10*s);
      ctx.strokeStyle = 'rgba(255,255,255,.7)';
      ctx.lineWidth = 1.5*s;
      ctx.stroke();

      // saddle
      ctx.beginPath();
      ctx.moveTo(-5*s, -14*s);
      ctx.lineTo(1*s, -14*s);
      ctx.strokeStyle = 'rgba(255,255,255,.6)';
      ctx.lineWidth = 2*s;
      ctx.lineCap = 'round';
      ctx.stroke();

      // rider body (aero tuck)
      ctx.beginPath();
      ctx.moveTo(0*s, -2*s);     // hips
      ctx.quadraticCurveTo(4*s, -16*s, 14*s, -14*s); // back
      ctx.strokeStyle = 'rgba(230,230,230,.9)';
      ctx.lineWidth = 4*s;
      ctx.lineCap = 'round';
      ctx.stroke();

      // helmet/head
      ctx.beginPath();
      ctx.arc(15*s, -17*s, 4.5*s, 0, Math.PI*2);
      ctx.fillStyle = wc;
      ctx.fill();
      ctx.beginPath();
      ctx.arc(17.5*s, -14.5*s, 2.5*s, 0, Math.PI*2);
      ctx.fillStyle = 'rgba(251,207,143,.95)';
      ctx.fill();

      // pedaling leg (crank animation)
      var crankAng = (Date.now() * 0.006) % (Math.PI*2);
      var cx2 = 0, cy2 = 0;
      var kx = cx2 + Math.cos(crankAng)*5*s;
      var ky = cy2 + Math.sin(crankAng)*5*s;
      ctx.beginPath();
      ctx.moveTo(cx2, cy2);
      ctx.lineTo(kx, ky);
      ctx.strokeStyle = 'rgba(255,255,255,.5)';
      ctx.lineWidth = 2*s;
      ctx.stroke();

      ctx.restore();
    }

    /* Interpolate position along scaled route */
    function routePos(pts, t){
      var totalLen = 0;
      var segs = [];
      for(var i=1; i<pts.length; i++){
        var dx = pts[i][0]-pts[i-1][0], dy = pts[i][1]-pts[i-1][1];
        var l = Math.sqrt(dx*dx+dy*dy);
        segs.push(l);
        totalLen += l;
      }
      var target = t * totalLen, acc = 0;
      for(var j=0; j<segs.length; j++){
        if(acc + segs[j] >= target){
          var localT = (target - acc) / segs[j];
          return {
            x: pts[j][0] + (pts[j+1][0]-pts[j][0])*localT,
            y: pts[j][1] + (pts[j+1][1]-pts[j][1])*localT,
            dir: pts[j+1][0] >= pts[j][0] ? 1 : -1
          };
        }
        acc += segs[j];
      }
      return {x: pts[pts.length-1][0], y: pts[pts.length-1][1], dir:1};
    }

    /* Draw grid background */
    function drawBG(){
      // Dark gradient
      var bg = ctx.createRadialGradient(W/2, H/2, 0, W/2, H/2, Math.max(W,H)/1.4);
      bg.addColorStop(0,   '#081828');
      bg.addColorStop(0.6, '#060E1A');
      bg.addColorStop(1,   '#04080F');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, W, H);

      // Grid lines
      ctx.strokeStyle = 'rgba(14,165,233,.06)';
      ctx.lineWidth = 1;
      for(var gx=0; gx<W; gx+=40){
        ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, H); ctx.stroke();
      }
      for(var gy=0; gy<H; gy+=40){
        ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(W, gy); ctx.stroke();
      }
    }

    /* Elevation mini-profile at bottom */
    function drawElevation(progress, wc){
      var ex0=48, ey0=H-18, ew=W-96, eh=22;
      // Base line
      ctx.fillStyle = 'rgba(0,0,0,.4)';
      ctx.fillRect(ex0-2, ey0-eh-2, ew+4, eh+4);

      // Pre-computed elevation from route Y (higher Y = lower elevation in canvas)
      var wPts = wRoute;
      var grad = ctx.createLinearGradient(ex0, ey0, ex0+ew, ey0);
      grad.addColorStop(0, wc+'44');
      grad.addColorStop(progress, wc+'cc');
      grad.addColorStop(progress, wc+'22');
      grad.addColorStop(1, wc+'22');
      ctx.fillStyle = grad;

      ctx.beginPath();
      ctx.moveTo(ex0, ey0);
      for(var ei=0; ei<wPts.length; ei++){
        var ex = ex0 + (ei/(wPts.length-1))*ew;
        // Invert Y: lower Y in route = higher elevation
        var ee = ey0 - (1 - wPts[ei][1]) * eh * 1.5;
        if(ei===0) ctx.moveTo(ex, ee);
        else ctx.lineTo(ex, ee);
      }
      ctx.lineTo(ex0+ew, ey0);
      ctx.lineTo(ex0, ey0);
      ctx.fill();

      // Progress indicator
      var pline = ex0 + progress * ew;
      ctx.beginPath();
      ctx.moveTo(pline, ey0-eh-2);
      ctx.lineTo(pline, ey0);
      ctx.strokeStyle = wc;
      ctx.lineWidth = 1.5;
      ctx.stroke();

      ctx.font = '600 8px Oswald,sans-serif';
      ctx.fillStyle = 'rgba(255,255,255,.35)';
      ctx.textAlign = 'left';
      ctx.fillText('RUTA', ex0, ey0-eh-5);
    }

    var ANIM_DUR = Math.min(16000, Math.max(8000, (ACT.dist_km||20)*320));
    var animStart2 = null, animRAF2 = null;

    function frameZwift(ts){
      if(!animStart2) animStart2 = ts;
      var raw   = Math.min(1, (ts - animStart2) / ANIM_DUR);
      var prog  = raw;
      var sPts  = scalePts(wRoute);

      drawBG();

      // Ghost full route (thin)
      ctx.beginPath();
      sPts.forEach(function(p,i){ i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]); });
      ctx.strokeStyle = 'rgba(255,255,255,.07)';
      ctx.lineWidth = 3;
      ctx.lineJoin = 'round';
      ctx.stroke();

      // Completed route (glow)
      var nDone = Math.max(2, Math.ceil(prog * sPts.length));
      var donePts = sPts.slice(0, nDone);

      // Shadow glow
      ctx.beginPath();
      donePts.forEach(function(p,i){ i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]); });
      ctx.strokeStyle = wColor + '33';
      ctx.lineWidth = 10;
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';
      ctx.stroke();

      // Main line
      ctx.beginPath();
      donePts.forEach(function(p,i){ i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]); });
      var lineGrad = ctx.createLinearGradient(sPts[0][0], sPts[0][1], donePts[donePts.length-1][0], donePts[donePts.length-1][1]);
      lineGrad.addColorStop(0, wColor+'55');
      lineGrad.addColorStop(1, wColor+'ff');
      ctx.strokeStyle = lineGrad;
      ctx.lineWidth = 3;
      ctx.stroke();

      // Route dots (checkpoints)
      for(var di=0; di<sPts.length; di+=Math.max(1,Math.floor(sPts.length/8))){
        var passed = di <= nDone;
        ctx.beginPath();
        ctx.arc(sPts[di][0], sPts[di][1], passed ? 3.5 : 2, 0, Math.PI*2);
        ctx.fillStyle = passed ? wColor : 'rgba(255,255,255,.15)';
        ctx.fill();
      }

      // Start marker
      ctx.beginPath();
      ctx.arc(sPts[0][0], sPts[0][1], 5, 0, Math.PI*2);
      ctx.fillStyle = '#10B981';
      ctx.fill();
      ctx.font = '600 8px Oswald,sans-serif';
      ctx.fillStyle = '#10B981';
      ctx.textAlign = 'center';
      ctx.fillText('START', sPts[0][0], sPts[0][1]-9);

      // Rider position
      var pos = routePos(sPts, prog);

      // Wake trail
      for(var wi2=1; wi2<=6; wi2++){
        var wp = routePos(sPts, Math.max(0, prog - wi2*0.012));
        ctx.beginPath();
        ctx.arc(wp.x, wp.y, 1.5, 0, Math.PI*2);
        ctx.fillStyle = wColor + Math.round((1-wi2/6)*80).toString(16).padStart(2,'0');
        ctx.fill();
      }

      // Cyclist
      drawCyclist(pos.x, pos.y, pos.dir, wColor);

      // Elevation profile
      drawElevation(prog, wColor);

      // KM counter (top right)
      var distDone = prog * (ACT.dist_km||20);
      ctx.font = '700 12px Oswald,sans-serif';
      ctx.fillStyle = 'rgba(255,255,255,.7)';
      ctx.textAlign = 'right';
      ctx.fillText(distDone.toFixed(1)+' / '+(ACT.dist_km||20).toFixed(1)+' km', W-14, 22);

      if(raw < 1){
        animRAF2 = requestAnimationFrame(frameZwift);
      } else {
        // Finish flag at end
        var last = sPts[sPts.length-1];
        ctx.font = '700 9px Oswald,sans-serif';
        ctx.fillStyle = '#F59E0B';
        ctx.textAlign = 'center';
        ctx.fillText('🏁 FINISH', last[0], last[1]-12);
      }
    }

    function startZwift(){
      if(animRAF2) cancelAnimationFrame(animRAF2);
      animStart2 = null;
      animRAF2 = requestAnimationFrame(frameZwift);
    }

    document.getElementById('zwift-replay').addEventListener('click', startZwift);
    window.addEventListener('resize', function(){ resizeZwift(); });
    startZwift();
    return;
  }

  if(cfg.type==='indoor'){
    mapWrap.innerHTML =
      '<div class="indoor-card">'
      +'<div class="indoor-icon">'+cfg.icon+'</div>'
      +'<div class="indoor-label">'+cfg.location+'</div>'
      +'<div class="indoor-sub">'+(ACT.name||sp.label)+' · '+durStr+(ACT.dist_km?' · '+ACT.dist_km.toFixed(1)+' km':'')+'</div>'
      +'</div>';
    return;
  }"""

if OLD_INDOOR in c:
    c = c.replace(OLD_INDOOR, NEW_INDOOR, 1)
    print('OK indoor block replaced')
else:
    print('MISS indoor block')

with open('C:/Users/rafae/projects/LabX/training_detail.html', 'w', encoding='utf-8') as f:
    f.write(c)
print('Saved training_detail.html')
