import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open('C:/Users/rafae/projects/LabX/training_detail.html', encoding='utf-8') as f:
    c = f.read()

# ── 1. Simplify getActConfig: Zwift → outdoor with real GPS coords ────────────
OLD_CFG = """function zwiftWorld(nm){
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
  }"""

NEW_CFG = """function zwiftWorldName(nm){
  if(/london|greater|box.?hill|leith|surrey/i.test(nm))   return 'Zwift — London';
  if(/new.?york|nyc|manhattan/i.test(nm))                 return 'Zwift — New York';
  if(/france|ventoux/i.test(nm))                          return 'Zwift — France';
  if(/innsbruck|austria/i.test(nm))                       return 'Zwift — Innsbruck';
  if(/richmond/i.test(nm))                                return 'Zwift — Richmond';
  if(/makuri|neokyo/i.test(nm))                           return 'Zwift — Makuri';
  return 'Zwift — Watopia';
}
function getActConfig(act){
  var nm = (act.name||'').toLowerCase();
  if(nm.indexOf('zwift')>=0){
    // Zwift GPS files contain real virtual-world coords — use Leaflet pipeline
    return {type:'outdoor', isZwift:true, icon:'🖥️',
            location:zwiftWorldName(nm),
            lat:-11.638, lng:166.949}; // Watopia fallback if no GPS file
  }"""

if OLD_CFG in c:
    c = c.replace(OLD_CFG, NEW_CFG, 1)
    print('OK getActConfig')
else:
    print('MISS getActConfig')

# ── 2. Remove the big zwift canvas block (replaced by Leaflet) ───────────────
import re
# Match everything between "if(cfg.type==='zwift'){" and the closing "  }" before pool block
pattern = r"  if\(cfg\.type===\'zwift\'\)\{.*?    return;\n  \}\n\n  if\(cfg\.type===\'indoor\'\)"
m = re.search(pattern, c, re.DOTALL)
if m:
    replacement = "  if(cfg.type==='indoor')"
    c = c[:m.start()] + replacement + c[m.end():]
    print('OK zwift canvas block removed')
else:
    print('MISS zwift canvas block')

# ── 3. Enhance the outdoor Leaflet badge to show Zwift branding ──────────────
OLD_BADGE = """  var badge = document.getElementById('map-badge');
  var locEl  = document.getElementById('map-loc');
  if(ACT.sport==='bike' && ACT.avg_power){
    badge.innerHTML = '<strong>'+cfg.location+'</strong>'
      +'⚡ '+ACT.avg_power+'W avg<br>'
      +(ACT.dist_km?'📍 '+ACT.dist_km.toFixed(1)+' km<br>':'')
      +(ACT.avg_hr?'❤️ '+ACT.avg_hr+' bpm':'');
  } else if(ACT.sport==='run'){
    var rPace = ACT.dist_km ? fmtPace(Math.round((ACT.dur_min*60)/ACT.dist_km)) : '—';
    badge.innerHTML = '<strong>'+cfg.location+'</strong>'
      +'🏃 '+rPace+'<br>'
      +(ACT.dist_km?'📍 '+ACT.dist_km.toFixed(1)+' km<br>':'')
      +(ACT.avg_hr?'❤️ '+ACT.avg_hr+' bpm':'');
  }
  locEl.textContent = cfg.location;"""

NEW_BADGE = """  var badge = document.getElementById('map-badge');
  var locEl  = document.getElementById('map-loc');
  if(cfg.isZwift){
    var np2  = ACT.avg_power ? Math.round(ACT.avg_power*1.07) : null;
    var if2  = np2 ? (np2/(FTP||200)).toFixed(2) : null;
    badge.innerHTML = '<strong>🖥️ '+cfg.location+'</strong>'
      +(ACT.avg_power?'⚡ '+ACT.avg_power+'W avg<br>':'')
      +(np2?'NP '+np2+'W · IF '+if2+'<br>':'')
      +(ACT.tss?'TSS '+ACT.tss+'<br>':'')
      +(ACT.avg_hr?'❤️ '+ACT.avg_hr+' bpm':'');
  } else if(ACT.sport==='bike' && ACT.avg_power){
    badge.innerHTML = '<strong>'+cfg.location+'</strong>'
      +'⚡ '+ACT.avg_power+'W avg<br>'
      +(ACT.dist_km?'📍 '+ACT.dist_km.toFixed(1)+' km<br>':'')
      +(ACT.avg_hr?'❤️ '+ACT.avg_hr+' bpm':'');
  } else if(ACT.sport==='run'){
    var rPace = ACT.dist_km ? fmtPace(Math.round((ACT.dur_min*60)/ACT.dist_km)) : '—';
    badge.innerHTML = '<strong>'+cfg.location+'</strong>'
      +'🏃 '+rPace+'<br>'
      +(ACT.dist_km?'📍 '+ACT.dist_km.toFixed(1)+' km<br>':'')
      +(ACT.avg_hr?'❤️ '+ACT.avg_hr+' bpm':'');
  }
  locEl.textContent = cfg.location;"""

if OLD_BADGE in c:
    c = c.replace(OLD_BADGE, NEW_BADGE, 1)
    print('OK badge')
else:
    print('MISS badge')

# ── 4. Zwift uses orange route color (not green for run) ─────────────────────
OLD_COLOR = "    var lineColor = ACT.sport==='run' ? '#10B981' : '#FF6535';"
NEW_COLOR = "    var lineColor = ACT.sport==='run' ? '#10B981' : cfg.isZwift ? '#FF6535' : '#FF6535';"
# No change needed — Zwift is always bike color. But let's add a Zwift label to the map
# Instead, inject a Zwift overlay label when it's Zwift
OLD_LOCTEXT = "  locEl.textContent = cfg.location;"
NEW_LOCTEXT = """  locEl.textContent = cfg.location;
  if(cfg.isZwift){
    locEl.style.color='#FF6535';
    locEl.style.borderColor='rgba(255,101,53,.35)';
  }"""

if OLD_LOCTEXT in c:
    c = c.replace(OLD_LOCTEXT, NEW_LOCTEXT, 1)
    print('OK zwift loc style')
else:
    print('MISS zwift loc style')

# ── 5. Remove now-unused Zwift CSS (keep pool CSS clean) ────────────────────
old_zwift_css = """.zwift-wrap{position:relative;background:#04080F;border-radius:var(--radius);overflow:hidden}
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
if old_zwift_css in c:
    c = c.replace(old_zwift_css, '', 1)
    print('OK zwift CSS removed')
else:
    print('NOTE: zwift CSS not found (may already be gone)')

with open('C:/Users/rafae/projects/LabX/training_detail.html', 'w', encoding='utf-8') as f:
    f.write(c)
print('Saved training_detail.html')
