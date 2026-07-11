import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open('C:/Users/rafae/projects/LabX/training_detail.html', encoding='utf-8') as f:
    c = f.read()

# ── 1. Inject animation CSS after the map height rule ───────────────────────
CSS_ANCHOR = '#map-leaflet{height:320px;background:#04080F}'

ANIM_CSS = '''#map-leaflet{height:320px;background:#04080F}
/* ── Route animation ── */
.map-replay-btn{
  position:absolute;bottom:10px;left:12px;z-index:500;
  background:rgba(4,8,15,.88);border:1px solid rgba(14,165,233,.35);
  border-radius:6px;padding:.32rem .72rem;
  font-family:'Oswald',sans-serif;font-size:.65rem;font-weight:600;
  letter-spacing:.1em;color:#0ea5e9;cursor:pointer;
  backdrop-filter:blur(6px);transition:background .15s,color .15s;
  display:flex;align-items:center;gap:.35rem;line-height:1;
}
.map-replay-btn:hover{background:rgba(14,165,233,.18);color:#38bdf8}
.map-replay-btn svg{width:9px;height:9px;fill:currentColor;flex-shrink:0}
@keyframes lx-head-pulse{
  0%  {box-shadow:0 0 0 0 var(--hc,#FF6535),0 0 0 0 var(--hc,#FF6535)}
  50% {box-shadow:0 0 0 5px rgba(255,101,53,0),0 0 8px 2px var(--hc,#FF6535)}
  100%{box-shadow:0 0 0 0 rgba(255,101,53,0),0 0 0 0 var(--hc,#FF6535)}
}'''

if CSS_ANCHOR in c:
    c = c.replace(CSS_ANCHOR, ANIM_CSS, 1)
    print('OK CSS injected')
else:
    print('MISS CSS anchor')

# ── 2. Replace the static render block with animated version ─────────────────
OLD_RENDER = '''    var lineColor = ACT.sport==='run' ? '#10B981' : '#FF6535';

    L.polyline(route, {color:lineColor, weight:10, opacity:.12}).addTo(leafletMap);
    var poly = L.polyline(route, {color:lineColor, weight:3, opacity:.95}).addTo(leafletMap);

    leafletMap.fitBounds(poly.getBounds(), {padding:[28,28]});

    function circleIcon(color){
      return L.divIcon({
        className:'',
        html:'<div style="width:14px;height:14px;border-radius:50%;background:'+color+';border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.5)"></div>',
        iconSize:[14,14], iconAnchor:[7,7]
      });
    }

    L.marker(route[0], {icon: circleIcon('#10B981')})
      .bindPopup('<b>Inicio</b><br>'+cfg.location).addTo(leafletMap);
    L.marker(route[route.length-1], {icon: circleIcon('#EF4444')})
      .bindPopup('<b>Fin</b><br>'+fmtDur(ACT.dur_min)).addTo(leafletMap);

    // Distance markers every N km
    var markerEvery = (ACT.dist_km||0) > 50 ? 20 : (ACT.dist_km||0) > 20 ? 10 : (ACT.dist_km||0) > 5 ? 5 : 2;
    var stepsPerKm  = route.length / (ACT.dist_km||1);
    for(var mk=markerEvery; mk<(ACT.dist_km||0); mk+=markerEvery){
      var idx = Math.round(mk * stepsPerKm);
      if(idx < route.length){
        L.marker(route[idx], {icon: L.divIcon({
          className:'',
          html:'<div style="font-family:Oswald,sans-serif;font-size:10px;color:#F0A500;background:rgba(4,8,15,.8);padding:1px 5px;border-radius:4px;border:1px solid rgba(240,165,0,.4);white-space:nowrap">'+mk+' km</div>',
          iconAnchor:[20,10]
        })}).addTo(leafletMap);
      }
    }'''

NEW_RENDER = '''    var lineColor = ACT.sport==='run' ? '#10B981' : '#FF6535';

    // Fit map to full route immediately (before animation)
    var boundsRef = L.polyline(route);
    leafletMap.fitBounds(boundsRef.getBounds(), {padding:[28,28]});

    // Ghost trace — full route, very faint, so athlete can see the circuit
    L.polyline(route, {color:lineColor, weight:8, opacity:.07, smoothFactor:1}).addTo(leafletMap);

    // Animated polylines (empty at start)
    var shadowPoly = L.polyline([], {color:lineColor, weight:10, opacity:.12, smoothFactor:1}).addTo(leafletMap);
    var mainPoly   = L.polyline([], {color:lineColor, weight:3,  opacity:.95, smoothFactor:1}).addTo(leafletMap);

    // Pulsing head marker
    function makeHeadIcon(color){
      return L.divIcon({
        className:'',
        html:'<div style="width:12px;height:12px;border-radius:50%;background:'+color+
             ';border:2px solid #fff;--hc:'+color+
             ';animation:lx-head-pulse 1s ease-in-out infinite"></div>',
        iconSize:[12,12], iconAnchor:[6,6]
      });
    }
    function circleIcon(color, size){
      size = size||14;
      return L.divIcon({
        className:'',
        html:'<div style="width:'+size+'px;height:'+size+'px;border-radius:50%;background:'+color+
             ';border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.6)"></div>',
        iconSize:[size,size], iconAnchor:[size/2,size/2]
      });
    }

    var headMarker = L.marker(route[0], {icon: makeHeadIcon(lineColor), zIndexOffset:1000}).addTo(leafletMap);

    // ── Animation ──────────────────────────────────────────────────────────
    var ANIM_DURATION = Math.min(5000, Math.max(2500, route.length * 10)); // 2.5–5s
    var animStart = null, animFrame = null, animDone = false;

    function easeInOutSine(t){ return -(Math.cos(Math.PI*t)-1)/2; }

    function drawFrame(ts){
      if(!animStart) animStart = ts;
      var raw  = Math.min(1, (ts - animStart) / ANIM_DURATION);
      var prog = easeInOutSine(raw);
      var n    = Math.max(2, Math.ceil(prog * route.length));
      var pts  = route.slice(0, n);

      shadowPoly.setLatLngs(pts);
      mainPoly.setLatLngs(pts);
      headMarker.setLatLng(pts[pts.length-1]);

      if(raw < 1){
        animFrame = requestAnimationFrame(drawFrame);
      } else {
        finishAnimation();
      }
    }

    function finishAnimation(){
      animDone = true;
      // Replace pulsing head with clean end marker
      leafletMap.removeLayer(headMarker);

      L.marker(route[0], {icon: circleIcon('#10B981')})
        .bindPopup('<b>Inicio</b><br>'+cfg.location).addTo(leafletMap);
      L.marker(route[route.length-1], {icon: circleIcon('#EF4444')})
        .bindPopup('<b>Fin</b><br>'+fmtDur(ACT.dur_min)).addTo(leafletMap);

      // Distance markers every N km
      var markerEvery = (ACT.dist_km||0) > 50 ? 20 : (ACT.dist_km||0) > 20 ? 10 : (ACT.dist_km||0) > 5 ? 5 : 2;
      var stepsPerKm  = route.length / (ACT.dist_km||1);
      for(var mk=markerEvery; mk<(ACT.dist_km||0); mk+=markerEvery){
        var mIdx = Math.round(mk * stepsPerKm);
        if(mIdx < route.length){
          L.marker(route[mIdx], {icon: L.divIcon({
            className:'',
            html:'<div style="font-family:Oswald,sans-serif;font-size:10px;color:#F0A500;background:rgba(4,8,15,.8);padding:1px 5px;border-radius:4px;border:1px solid rgba(240,165,0,.4);white-space:nowrap">'+mk+' km</div>',
            iconAnchor:[20,10]
          })}).addTo(leafletMap);
        }
      }
    }

    // Start animation when map tiles ready (or immediately)
    leafletMap.once('load', function(){ animFrame = requestAnimationFrame(drawFrame); });
    setTimeout(function(){
      if(!animStart) animFrame = requestAnimationFrame(drawFrame);
    }, 400);

    // ── Replay button ───────────────────────────────────────────────────────
    var replayBtn = document.createElement('button');
    replayBtn.className = 'map-replay-btn';
    replayBtn.innerHTML = '<svg viewBox="0 0 10 10"><polygon points="2,1 9,5 2,9"/></svg>REPLAY';
    replayBtn.addEventListener('click', function(){
      if(animFrame) cancelAnimationFrame(animFrame);
      animStart = null; animDone = false;

      // Remove old overlays except ghost and tiles
      shadowPoly.setLatLngs([]); mainPoly.setLatLngs([]);
      // Remove start/end/km markers (re-created by finishAnimation)
      leafletMap.eachLayer(function(layer){
        if(layer instanceof L.Marker) leafletMap.removeLayer(layer);
      });
      // Re-add head marker
      leafletMap.addLayer(headMarker);
      headMarker.setLatLng(route[0]);

      animFrame = requestAnimationFrame(drawFrame);
    });
    document.getElementById('map-wrap').appendChild(replayBtn);'''

if OLD_RENDER in c:
    c = c.replace(OLD_RENDER, NEW_RENDER, 1)
    print('OK render replaced')
else:
    print('MISS render — trying partial match')
    # Check first line
    first = '    var lineColor = ACT.sport===\'run\' ? \'#10B981\' : \'#FF6535\';'
    idx = c.find(first)
    print(f'  first line at: {idx}')

with open('C:/Users/rafae/projects/LabX/training_detail.html', 'w', encoding='utf-8') as f:
    f.write(c)
print('Saved training_detail.html')
