import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open('C:/Users/rafae/projects/LabX/blood_labs.html', encoding='utf-8') as f:
    c = f.read()

# ── 1. Fix init(): merge localStorage with seed data (prefer richer record) ──
OLD_INIT = """(function init(){
  // Try localStorage first as fast path
  var stored = localStorage.getItem('kl_blood_labs');
  if(stored){ try{ var d=JSON.parse(stored); if(d.exams&&d.exams.length>=EXAMS.length){ EXAMS.splice(0,EXAMS.length); d.exams.forEach(function(e){ EXAMS.push(e); }); if(d.biomarkers) Object.assign(BM,d.biomarkers); } }catch(e){} }
  buildExamSelectors();
  buildForm();
  renderAll();
  // Then load from API (overrides localStorage if more data)
  loadExamsFromAPI();
})();"""

NEW_INIT = """(function init(){
  // Merge localStorage with seed data — prefer record with MORE values per date
  var stored = localStorage.getItem('kl_blood_labs');
  if(stored){ try{
    var d = JSON.parse(stored);
    if(d.exams && d.exams.length){
      d.exams.forEach(function(de){
        var nv = Object.keys(de.values||{}).length;
        var ei = EXAMS.findIndex(function(e){ return e.date===de.date; });
        var ev = ei>=0 ? Object.keys(EXAMS[ei].values||{}).length : 0;
        if(nv >= ev){
          if(ei>=0) EXAMS[ei]=de; else EXAMS.push(de);
        }
      });
      EXAMS.sort(function(a,b){ return a.date<b.date?-1:1; });
    }
    if(d.biomarkers) Object.assign(BM, d.biomarkers);
  }catch(e){} }
  buildExamSelectors();
  buildForm();
  renderAll();
  // Then load from API — merge, don't replace
  loadExamsFromAPI();
})();"""

if OLD_INIT in c:
    c = c.replace(OLD_INIT, NEW_INIT, 1)
    print('OK init() fixed')
else:
    print('MISS init()')

# ── 2. Fix loadExamsFromAPI(): merge by date, prefer API record if richer ─────
OLD_LOAD_API = """      if (!rows || !rows.length) return;
      var apiExams = rows.map(function(r){
        var vals = {};
        try { vals = JSON.parse(r.values_json); } catch(e){}
        return { date: r.date_iso, lab: r.lab_name || 'Laboratorio', context: r.context || '', values: vals, _api_id: r.id };
      });
      EXAMS.splice(0, EXAMS.length);
      apiExams.forEach(function(e){ EXAMS.push(e); });
      EXAMS.sort(function(a,b){ return a.date<b.date?-1:1; });
      EXAM_IDX = EXAMS.length - 1;
      COMP_IDX = EXAMS.length - 2;
      buildExamSelectors();
      renderAll();"""

NEW_LOAD_API = """      if (!rows || !rows.length) return;
      var apiExams = rows.map(function(r){
        var vals = {};
        try { vals = JSON.parse(r.values_json); } catch(e){}
        return { date: r.date_iso, lab: r.lab_name || 'Laboratorio', context: r.context || '', values: vals, _api_id: r.id };
      });
      // Merge by date — prefer record with more values
      apiExams.forEach(function(ae){
        var nv = Object.keys(ae.values||{}).length;
        var ei = EXAMS.findIndex(function(e){ return e.date===ae.date; });
        var ev = ei>=0 ? Object.keys(EXAMS[ei].values||{}).length : 0;
        if(nv >= ev){
          if(ei>=0) EXAMS[ei]=ae; else EXAMS.push(ae);
        } else if(ei<0){
          EXAMS.push(ae); // add if new date
        }
      });
      EXAMS.sort(function(a,b){ return a.date<b.date?-1:1; });
      EXAM_IDX = EXAMS.length - 1;
      COMP_IDX = EXAMS.length - 2;
      buildExamSelectors();
      renderAll();"""

if OLD_LOAD_API in c:
    c = c.replace(OLD_LOAD_API, NEW_LOAD_API, 1)
    print('OK loadExamsFromAPI() fixed')
else:
    print('MISS loadExamsFromAPI()')

# ── 3. Fix saveExtracted(): also POST to API for server-side persistence ──────
OLD_SAVE_EXT = """  var idx = EXAMS.findIndex(function(e){ return e.date === dateVal; });
  if(idx >= 0){ EXAMS[idx] = newExam; }
  else{ EXAMS.push(newExam); EXAMS.sort(function(a,b){ return a.date<b.date?-1:1; }); }

  localStorage.setItem('kl_blood_labs', JSON.stringify({biomarkers:BM, exams:EXAMS}));

  EXAM_IDX = EXAMS.length-1;
  COMP_IDX = EXAMS.length-2;
  buildExamSelectors();
  buildForm();
  renderAll();

  showSaveMsg('✅ Examen del '+dateVal+' guardado con '+Object.keys(values).length+' marcadores.','ok');
}"""

NEW_SAVE_EXT = """  var idx = EXAMS.findIndex(function(e){ return e.date === dateVal; });
  if(idx >= 0){ EXAMS[idx] = newExam; }
  else{ EXAMS.push(newExam); EXAMS.sort(function(a,b){ return a.date<b.date?-1:1; }); }

  localStorage.setItem('kl_blood_labs', JSON.stringify({biomarkers:BM, exams:EXAMS}));

  EXAM_IDX = EXAMS.length-1;
  COMP_IDX = EXAMS.length-2;
  buildExamSelectors();
  renderAll();

  // Also POST to API for server-side persistence
  var tok = typeof getApiToken === 'function' ? getApiToken() : null;
  if(tok){
    fetch(API_BASE + '/athlete/blood-labs', {
      method:'POST', headers: typeof apiHeaders==='function' ? apiHeaders() : {'Content-Type':'application/json','Authorization':'Bearer '+tok},
      body: JSON.stringify({
        date_iso: dateVal,
        lab_name: newExam.lab,
        context:  newExam.context,
        values_json: JSON.stringify(values)
      })
    }).then(function(r){
      showSaveMsg(r.ok
        ? '✅ Examen del '+dateVal+' guardado ('+Object.keys(values).length+' marcadores) — sincronizado ✓'
        : '✅ Guardado localmente ('+Object.keys(values).length+' marcadores)', 'ok');
    }).catch(function(){
      showSaveMsg('✅ Guardado localmente ('+Object.keys(values).length+' marcadores)', 'ok');
    });
  } else {
    showSaveMsg('✅ Examen del '+dateVal+' guardado con '+Object.keys(values).length+' marcadores.','ok');
  }
}"""

if OLD_SAVE_EXT in c:
    c = c.replace(OLD_SAVE_EXT, NEW_SAVE_EXT, 1)
    print('OK saveExtracted() fixed')
else:
    print('MISS saveExtracted()')

# ── 4. Add a "limpiar caché" safety button in the upload zone tip ─────────────
OLD_TIP = '''      <div class="parse-warn" style="margin-top:.85rem">
        💡 El extractor automático reconoce informes de <strong>Clínica Alemana, Bupa, Megasalud</strong> y la mayoría de laboratorios chilenos. Puedes corregir cualquier valor antes de guardar.
      </div>'''

NEW_TIP = '''      <div class="parse-warn" style="margin-top:.85rem">
        💡 El extractor automático reconoce informes de <strong>Clínica Alemana, Bupa, Megasalud</strong> y la mayoría de laboratorios chilenos. Puedes corregir cualquier valor antes de guardar.
        <div style="margin-top:.5rem">
          <button onclick="clearBloodLabsCache()" style="background:none;border:1px solid rgba(245,158,11,.4);border-radius:5px;padding:.2rem .65rem;font-family:\'Oswald\',sans-serif;font-size:.62rem;color:#F59E0B;cursor:pointer;letter-spacing:.07em">
            🗑 Limpiar caché local
          </button>
          <span style="font-size:.68rem;color:var(--dim);margin-left:.5rem">Si el resumen aparece vacío o con datos incorrectos</span>
        </div>
      </div>'''

if OLD_TIP in c:
    c = c.replace(OLD_TIP, NEW_TIP, 1)
    print('OK cache clear button added')
else:
    print('MISS tip block')

# ── 5. Add clearBloodLabsCache() function before init ─────────────────────────
OLD_INIT_START = "(function init(){"
NEW_INIT_START = """function clearBloodLabsCache(){
  localStorage.removeItem('kl_blood_labs');
  // Reload seed data
  EXAMS.splice(0, EXAMS.length);
  var seed = (window.KL_BLOOD||{}).exams||[];
  seed.forEach(function(e){ EXAMS.push(e); });
  EXAMS.sort(function(a,b){ return a.date<b.date?-1:1; });
  EXAM_IDX = EXAMS.length-1; COMP_IDX = EXAMS.length-2;
  buildExamSelectors(); renderAll();
  alert('Caché local limpiada. Mostrando datos del archivo base.');
}

(function init(){"""

# Only replace the LAST occurrence (in init section)
last_idx = c.rfind(OLD_INIT_START)
if last_idx >= 0:
    c = c[:last_idx] + NEW_INIT_START + c[last_idx+len(OLD_INIT_START):]
    # Fix the extra closing brace
    print('OK clearBloodLabsCache() added')
else:
    print('MISS init start for cache clear fn')

with open('C:/Users/rafae/projects/LabX/blood_labs.html', 'w', encoding='utf-8') as f:
    f.write(c)
print('Saved blood_labs.html')
