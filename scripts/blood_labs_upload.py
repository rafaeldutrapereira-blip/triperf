import sys, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open('C:/Users/rafae/projects/LabX/blood_labs.html', encoding='utf-8') as f:
    c = f.read()

# ── 1. Add PDF.js CDN before closing </head> ─────────────────────────────────
OLD_HEAD = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>'
NEW_HEAD = '''<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>'''

if OLD_HEAD in c:
    c = c.replace(OLD_HEAD, NEW_HEAD, 1)
    print('OK PDF.js CDN')
else:
    print('MISS PDF.js CDN anchor')

# ── 2. Replace the import tab HTML ───────────────────────────────────────────
OLD_IMPORT_TAB = '''<div class="tab-pane" id="tab-import">
  <div class="g2">
    <div>
      <div class="sec-h">Registrar Nuevo Examen</div>
      <div class="panel">
        <div class="panel-body">
          <div class="g2" style="gap:.75rem;margin-bottom:.75rem">
            <div class="form-field">
              <label class="form-label" data-i18n="labs_date">Fecha del examen</label>
              <input type="date" class="form-input" id="inp-date">
            </div>
            <div class="form-field">
              <label class="form-label" data-i18n="labs_lab">Laboratorio</label>
              <input type="text" class="form-input" id="inp-lab" placeholder="Laboratorio Clínico">
            </div>
          </div>
          <div class="form-field" style="margin-bottom:.75rem">
            <label class="form-label" data-i18n="labs_context">Contexto / Motivo</label>
            <input type="text" class="form-input" id="inp-ctx" placeholder="Ej: Control pre-temporada · Post-Ironman Vitoria">
          </div>
          <div id="form-cats-container"></div>
          <div style="margin-top:1.2rem;display:flex;gap:.75rem;flex-wrap:wrap">
            <button class="btn btn-primary" onclick="saveExam()" data-i18n="btn_save_exam">💾 Guardar Examen</button>
            <button class="btn btn-g" onclick="clearForm()" data-i18n="btn_clear">✕ Limpiar</button>
          </div>
          <div class="save-msg" id="save-msg"></div>
        </div>
      </div>
    </div>
    <div>
      <div class="sec-h">Guía de Marcadores para Triatleta</div>
      <div class="panel">
        <div class="panel-body" id="guide-panel" style="font-size:.78rem;color:var(--muted);line-height:1.65;max-height:520px;overflow-y:auto"></div>
      </div>
    </div>
  </div>
</div>'''

NEW_IMPORT_TAB = '''<div class="tab-pane" id="tab-import">

<!-- ── CSS: upload UI ── -->
<style>
.upload-zone{border:2px dashed rgba(14,165,233,.35);border-radius:12px;
  background:rgba(14,165,233,.04);padding:3rem 2rem;text-align:center;
  cursor:pointer;transition:all .2s;position:relative}
.upload-zone.drag-over{border-color:#0ea5e9;background:rgba(14,165,233,.1)}
.upload-zone:hover{border-color:rgba(14,165,233,.6);background:rgba(14,165,233,.07)}
.upload-icon{font-size:3rem;margin-bottom:.75rem;opacity:.7}
.upload-title{font-family:'Barlow Condensed',sans-serif;font-size:1.35rem;font-weight:700;
  color:var(--text);margin-bottom:.35rem;letter-spacing:.02em}
.upload-sub{font-size:.8rem;color:var(--muted)}
.upload-formats{display:flex;gap:.4rem;justify-content:center;margin-top:.85rem;flex-wrap:wrap}
.fmt-badge{background:rgba(14,165,233,.1);border:1px solid rgba(14,165,233,.25);
  border-radius:4px;padding:.18rem .55rem;font-family:'Oswald',sans-serif;
  font-size:.62rem;letter-spacing:.08em;color:#0ea5e9}
.upload-btn{margin-top:1rem;background:rgba(14,165,233,.12);border:1px solid rgba(14,165,233,.3);
  border-radius:7px;padding:.55rem 1.4rem;font-family:'Oswald',sans-serif;font-size:.75rem;
  font-weight:600;letter-spacing:.1em;color:#0ea5e9;cursor:pointer;transition:background .15s}
.upload-btn:hover{background:rgba(14,165,233,.22)}
.upload-input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}

.proc-box{text-align:center;padding:2.5rem 1rem}
.proc-spinner{width:44px;height:44px;border:3px solid rgba(14,165,233,.2);
  border-top-color:#0ea5e9;border-radius:50%;animation:spin .8s linear infinite;
  margin:0 auto 1rem}
@keyframes spin{to{transform:rotate(360deg)}}
.proc-name{font-family:'Oswald',sans-serif;font-size:.8rem;color:var(--muted);letter-spacing:.06em}
.proc-step{font-size:.72rem;color:var(--dim);margin-top:.3rem}

.upload-result-header{display:flex;align-items:center;justify-content:space-between;
  margin-bottom:1.2rem;flex-wrap:wrap;gap:.75rem}
.result-file-badge{display:flex;align-items:center;gap:.5rem;background:rgba(14,165,233,.08);
  border:1px solid rgba(14,165,233,.22);border-radius:7px;padding:.4rem .9rem;
  font-family:'Oswald',sans-serif;font-size:.72rem;color:#0ea5e9;letter-spacing:.05em}
.result-count-badge{background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.25);
  border-radius:7px;padding:.4rem .9rem;font-family:'Oswald',sans-serif;font-size:.72rem;
  color:#10B981;letter-spacing:.05em}

.extracted-table{width:100%;border-collapse:collapse;margin-top:.75rem}
.extracted-table th{font-family:'Oswald',sans-serif;font-size:.64rem;letter-spacing:.1em;
  text-transform:uppercase;color:var(--dim);padding:.6rem .85rem;text-align:left;
  border-bottom:1px solid var(--border2)}
.extracted-table td{padding:.55rem .85rem;font-size:.78rem;border-bottom:1px solid var(--border2)}
.extracted-table tr:hover td{background:rgba(14,165,233,.03)}
.ext-val-ok{color:#10B981;font-weight:700}
.ext-val-hi{color:#F59E0B;font-weight:700}
.ext-val-lo{color:#0ea5e9;font-weight:700}
.ext-val-input{width:90px;background:var(--surface);border:1px solid var(--border2);
  border-radius:5px;padding:.25rem .5rem;font-size:.78rem;color:var(--text);
  font-family:'Barlow Condensed',sans-serif;text-align:right}
.ext-val-input:focus{outline:none;border-color:#0ea5e9}
.img-preview{max-width:100%;max-height:320px;border-radius:8px;border:1px solid var(--border2);
  display:block;margin:0 auto 1rem}
.parse-warn{background:rgba(245,158,11,.08);border:1px solid rgba(245,158,11,.25);
  border-radius:7px;padding:.75rem 1rem;font-size:.76rem;color:#F59E0B;margin-bottom:1rem}
.meta-row{display:grid;grid-template-columns:1fr 1fr;gap:.75rem;margin-bottom:.85rem}
@media(max-width:600px){.meta-row{grid-template-columns:1fr}}
.btn-upload-new{background:transparent;border:1px solid var(--border2);border-radius:6px;
  padding:.3rem .75rem;font-family:'Oswald',sans-serif;font-size:.65rem;letter-spacing:.08em;
  color:var(--muted);cursor:pointer;transition:all .15s}
.btn-upload-new:hover{border-color:#0ea5e9;color:#0ea5e9}
</style>

<!-- ── UPLOAD ZONE ── -->
<div id="upload-zone-wrap">
  <div class="g2" style="align-items:start">
    <div>
      <div class="sec-h">Subir Examen de Laboratorio</div>
      <div class="upload-zone" id="upload-zone" ondragover="upDrag(event,true)" ondragleave="upDrag(event,false)" ondrop="upDrop(event)">
        <input type="file" class="upload-input" id="upload-input" accept=".pdf,.jpg,.jpeg,.png,.webp,.docx"
               onchange="upPick(this.files)">
        <div class="upload-icon">📄</div>
        <div class="upload-title">Arrastra tu informe aquí</div>
        <div class="upload-sub">o haz clic para seleccionar el archivo</div>
        <div class="upload-formats">
          <span class="fmt-badge">PDF</span>
          <span class="fmt-badge">JPG</span>
          <span class="fmt-badge">PNG</span>
          <span class="fmt-badge">WEBP</span>
        </div>
        <button class="upload-btn" onclick="document.getElementById('upload-input').click();event.stopPropagation()">
          Seleccionar archivo
        </button>
      </div>
      <div class="parse-warn" style="margin-top:.85rem">
        💡 El extractor automático reconoce informes de <strong>Clínica Alemana, Bupa, Megasalud</strong> y la mayoría de laboratorios chilenos. Puedes corregir cualquier valor antes de guardar.
      </div>
    </div>
    <div>
      <div class="sec-h">Guía de Marcadores para Triatleta</div>
      <div class="panel">
        <div class="panel-body" id="guide-panel" style="font-size:.78rem;color:var(--muted);line-height:1.65;max-height:480px;overflow-y:auto"></div>
      </div>
    </div>
  </div>
</div>

<!-- ── PROCESSING STATE ── -->
<div id="upload-processing" style="display:none">
  <div class="panel"><div class="panel-body proc-box">
    <div class="proc-spinner"></div>
    <div class="proc-name" id="proc-filename"></div>
    <div class="proc-step" id="proc-step">Leyendo documento...</div>
  </div></div>
</div>

<!-- ── RESULTS PANEL ── -->
<div id="upload-results" style="display:none">
  <div class="upload-result-header">
    <div style="display:flex;align-items:center;gap:.6rem;flex-wrap:wrap">
      <span class="result-file-badge" id="res-file-badge">📄 archivo.pdf</span>
      <span class="result-count-badge" id="res-count-badge">✓ 0 marcadores</span>
    </div>
    <button class="btn-upload-new" onclick="resetUpload()">↑ Subir otro archivo</button>
  </div>

  <!-- image preview (for JPG/PNG) -->
  <div id="img-preview-wrap" style="display:none">
    <img id="img-preview" class="img-preview" src="" alt="Vista previa">
    <div class="parse-warn">⚠️ La extracción automática solo funciona con PDF de texto. Revisa la imagen y completa los valores manualmente.</div>
  </div>

  <div class="g2" style="align-items:start">
    <div>
      <!-- Meta fields -->
      <div class="panel" style="margin-bottom:1rem">
        <div class="panel-body">
          <div class="meta-row">
            <div class="form-field">
              <label class="form-label">Fecha del examen</label>
              <input type="date" class="form-input" id="res-date">
            </div>
            <div class="form-field">
              <label class="form-label">Laboratorio</label>
              <input type="text" class="form-input" id="res-lab" placeholder="Clínica Alemana">
            </div>
          </div>
          <div class="form-field">
            <label class="form-label">Contexto / Motivo</label>
            <input type="text" class="form-input" id="res-ctx" placeholder="Ej: Control pre-temporada · Post-Ironman">
          </div>
        </div>
      </div>

      <!-- Extracted values table -->
      <div class="panel">
        <div class="panel-body" style="padding:0">
          <div id="extracted-container"></div>
        </div>
      </div>

      <!-- Save bar -->
      <div style="margin-top:1.2rem;display:flex;gap:.75rem;flex-wrap:wrap;align-items:center">
        <button class="btn btn-primary" onclick="saveExtracted()">💾 Guardar Examen</button>
        <button class="btn btn-g" onclick="toggleManualEdit()">✎ Editar valores</button>
      </div>
      <div class="save-msg" id="save-msg"></div>
    </div>

    <!-- Manual edit panel (hidden by default) -->
    <div id="manual-edit-panel" style="display:none">
      <div class="sec-h">Editar / Agregar Valores</div>
      <div class="panel">
        <div class="panel-body">
          <div id="form-cats-container"></div>
        </div>
      </div>
    </div>
  </div>
</div>

</div><!-- /tab-import -->'''

if OLD_IMPORT_TAB in c:
    c = c.replace(OLD_IMPORT_TAB, NEW_IMPORT_TAB, 1)
    print('OK tab-import replaced')
else:
    print('MISS tab-import — checking partial')
    idx = c.find('id="tab-import"')
    print(f'  tab-import at: {idx}')

# ── 3. Add upload JS before </script> of main script block ───────────────────
# Find the closing of the main script (after saveExam)
UPLOAD_JS = r'''
// ══════════════════════════════════════════════════════════════
// UPLOAD & PDF PARSING
// ══════════════════════════════════════════════════════════════

// PDF.js worker
if(typeof pdfjsLib !== 'undefined'){
  pdfjsLib.GlobalWorkerOptions.workerSrc =
    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
}

// Map: lowercase Spanish lab term → our BM key
var PDF_MAP = {
  'glucosa':'glucosa',
  'nitrógeno ureico':'nitrogeno_ureico','nitrogeno ureico':'nitrogeno_ureico',
  'urea':'urea',
  'colesterol total':'colesterol_total',
  'ácido úrico':'ac_urico','acido urico':'ac_urico',
  'proteínas totales':'proteinas_totales','proteinas totales':'proteinas_totales',
  'albúmina':'albumina','albumina':'albumina',
  'globulinas':'globulinas',
  'bilirrubina total':'bilirrubina_total',
  'transaminasa got-ast':'got_ast','got-ast':'got_ast',
  'transaminasa gpt-alt':'gpt_alt','gpt-alt':'gpt_alt',
  'gamma glutamiltransferasa ggt':'ggt','ggt ':'ggt',
  'deshidrogenasa láctica total ldh':'ldh','deshidrogenasa lactica total ldh':'ldh','ldh ':'ldh',
  'fosfatasas alcalinas totales':'fosfatasas_alc','fosfatasas alcalinas':'fosfatasas_alc',
  'calcio total':'calcio','calcio ':'calcio',
  'fósforo inorgánico':'fosforo','fosforo inorgánico':'fosforo',
  'triglicéridos':'trigliceridos','trigliceridos':'trigliceridos',
  'hdl colesterol':'hdl',
  'ldl colesterol':'ldl',
  'colesterol no hdl':'colesterol_nhdl',
  'vitamina b12 cianocobalamina':'vitamina_b12','vitamina b12':'vitamina_b12',
  'creatinina ':'creatinina',
  'tasa de filtración glomerular':'tfge','tfg estimada':'tfge','tfge ':'tfge',
  'antígeno prostático total':'psa_total','antígeno prostatico total':'psa_total','psa total':'psa_total',
  'h. tiroestimulante - tsh':'tsh','tsh ':'tsh',
  't4 libre - ft4':'ft4','ft4 ':'ft4',
  'sodio ':'na',
  'potasio ':'k',
  'cloro ':'cl',
  'vitamina d total':'vitamina_d','25-oh-d':'vitamina_d','vitamina d ':'vitamina_d',
  'recuento de hematíes':'eritrocitos','hematies ':'eritrocitos',
  'hemoglobina ':'hemoglobina',
  'hematocrito ':'hematocrito',
  'vcm ':'vcm',
  'hcm ':'hcm',
  'chcm ':'chcm',
  'recuento de leucocitos':'leucocitos',
  'recuento de plaquetas':'plaquetas',
  'sedimentación globular':'sedimentacion','sedimentacion globular':'sedimentacion',
  'creatinquinasa':'ck','creatina kinasa':'ck','ck total':'ck'
};

// Extract date from text
function pdfExtractDate(text){
  var m = text.match(/fecha\s+(?:de\s+)?(?:toma\s+de\s+muestra|validaci[oó]n)\s*:?\s*(\d{1,2})\/(\d{1,2})\/(\d{2,4})/i);
  if(m){
    var y = m[3].length===2 ? '20'+m[3] : m[3];
    return y+'-'+String(m[2]).padStart(2,'0')+'-'+String(m[1]).padStart(2,'0');
  }
  return new Date().toISOString().slice(0,10);
}

// Extract lab name from text
function pdfExtractLab(text){
  if(/cl[ií]nica\s+alemana/i.test(text)) return 'Clínica Alemana';
  if(/bupa/i.test(text)) return 'Bupa Chile';
  if(/megasalud/i.test(text)) return 'Megasalud';
  if(/santa\s+mar[ií]a/i.test(text)) return 'Clínica Santa María';
  if(/laboratorio\s+clínico/i.test(text)) return 'Laboratorio Clínico';
  return '';
}

// Parse lab values from extracted text
function parseLabText(text){
  var results = {};
  var norm = text
    .replace(/[↑↓↑↓]/g,' ')
    .replace(/\s+/g,' ')
    .toLowerCase();

  // Sort by length (longest match first to avoid partial matches)
  var entries = Object.entries(PDF_MAP);
  entries.sort(function(a,b){ return b[0].length - a[0].length; });

  entries.forEach(function(pair){
    var searchKey = pair[0], bmKey = pair[1];
    if(results[bmKey]) return; // already found
    // Escape regex special chars
    var esc = searchKey.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    // Pattern: key followed by optional ↑↓, then number (with dot or comma), then unit chars
    var re = new RegExp(esc + '\\s*[↑↓]?\\s*([\\d]+[,.]?[\\d]*)\\s*(?:mg|g\\/|u\\/|uu|pg|ng|meq|mm|%|10|ml)', 'i');
    var m = norm.match(re);
    if(m){
      var val = parseFloat(m[1].replace(',','.'));
      if(!isNaN(val) && val > 0) results[bmKey] = val;
    }
  });

  return results;
}

// Extract text from PDF using PDF.js
async function extractPdfText(file){
  if(typeof pdfjsLib === 'undefined') return null;
  var ab = await file.arrayBuffer();
  var pdf = await pdfjsLib.getDocument({data:ab}).promise;
  var fullText = '';
  for(var i=1; i<=pdf.numPages; i++){
    var page = await pdf.getPage(i);
    var content = await page.getTextContent();
    var pageText = content.items.map(function(it){ return it.str; }).join(' ');
    fullText += pageText + '\n';
  }
  return fullText;
}

// State for current upload
var _upExtracted = {};
var _upText = '';

// Drag & drop handlers
function upDrag(e, over){
  e.preventDefault();
  document.getElementById('upload-zone').classList.toggle('drag-over', over);
}
function upDrop(e){
  e.preventDefault();
  document.getElementById('upload-zone').classList.remove('drag-over');
  upPick(e.dataTransfer.files);
}
function upPick(files){
  if(!files || !files.length) return;
  processUpload(files[0]);
}

// Reset to upload zone
function resetUpload(){
  document.getElementById('upload-zone-wrap').style.display='';
  document.getElementById('upload-processing').style.display='none';
  document.getElementById('upload-results').style.display='none';
  document.getElementById('upload-input').value='';
}

// Main processing function
async function processUpload(file){
  document.getElementById('upload-zone-wrap').style.display='none';
  document.getElementById('upload-processing').style.display='';
  document.getElementById('upload-results').style.display='none';

  document.getElementById('proc-filename').textContent = file.name;
  document.getElementById('proc-step').textContent = 'Leyendo documento...';

  var isPDF  = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
  var isImg  = /image\/(jpeg|jpg|png|webp)/.test(file.type) || /\.(jpg|jpeg|png|webp)$/i.test(file.name);

  var extracted = {}, dateVal = '', labVal = '';

  if(isPDF){
    document.getElementById('proc-step').textContent = 'Extrayendo texto del PDF...';
    try{
      _upText = await extractPdfText(file);
      document.getElementById('proc-step').textContent = 'Identificando marcadores...';
      extracted = parseLabText(_upText);
      dateVal = pdfExtractDate(_upText);
      labVal  = pdfExtractLab(_upText);
    } catch(err){
      console.error('PDF parse error:', err);
      _upText = '';
    }
  }

  // Image preview
  document.getElementById('img-preview-wrap').style.display = isImg ? '' : 'none';
  if(isImg){
    var url = URL.createObjectURL(file);
    document.getElementById('img-preview').src = url;
  }

  _upExtracted = extracted;

  // Show results
  document.getElementById('upload-processing').style.display='none';
  document.getElementById('upload-results').style.display='';

  // File badge
  var ext = file.name.split('.').pop().toUpperCase();
  document.getElementById('res-file-badge').textContent = '📄 ' + file.name;
  var n = Object.keys(extracted).length;
  document.getElementById('res-count-badge').textContent =
    n > 0 ? ('✓ ' + n + ' marcadores detectados') : '⚠ Revisión manual requerida';
  document.getElementById('res-count-badge').style.background =
    n > 0 ? 'rgba(16,185,129,.1)' : 'rgba(245,158,11,.1)';
  document.getElementById('res-count-badge').style.borderColor =
    n > 0 ? 'rgba(16,185,129,.25)' : 'rgba(245,158,11,.25)';
  document.getElementById('res-count-badge').style.color =
    n > 0 ? '#10B981' : '#F59E0B';

  // Meta fields
  document.getElementById('res-date').value = dateVal || new Date().toISOString().slice(0,10);
  document.getElementById('res-lab').value  = labVal;

  // Render extracted table
  renderExtractedTable(extracted);

  // Also populate manual form fields (if they exist)
  if(typeof buildForm === 'function') buildForm();
  Object.entries(extracted).forEach(function(e){
    var el = document.getElementById('fi-'+e[0]);
    if(el) el.value = e[1];
  });
}

// Render the extracted values review table
function renderExtractedTable(extracted){
  var container = document.getElementById('extracted-container');
  var cats = FORM_CATS;
  var found = Object.keys(extracted);

  // Group by category
  var html = '';
  var totalShown = 0;

  cats.forEach(function(cat){
    var catKeys = cat.keys.filter(function(k){ return extracted[k] != null; });
    // Also include keys not in any cat but in extracted
    if(!catKeys.length) return;
    totalShown += catKeys.length;

    html += '<div style="padding:.6rem 1rem .15rem;border-bottom:1px solid var(--border2)">' +
      '<span style="font-family:\'Oswald\',sans-serif;font-size:.66rem;font-weight:700;' +
      'letter-spacing:.1em;text-transform:uppercase;color:var(--muted)">' + cat.label + '</span></div>';
    html += '<table class="extracted-table"><thead><tr>' +
      '<th>Marcador</th><th style="text-align:right">Valor</th>' +
      '<th>Unidad</th><th>Ref</th><th>Estado</th></tr></thead><tbody>';

    catKeys.forEach(function(k){
      var bmd = BM[k] || {label:k, unit:'', ref_low:0, ref_high:999};
      var val = extracted[k];
      var lo = bmd.ref_low, hi = bmd.ref_high;
      var status = '', cls = '';
      if(lo != null && hi != null){
        if(val < lo){       status = '↓ Bajo';  cls = 'ext-val-lo'; }
        else if(val > hi){  status = '↑ Alto';  cls = 'ext-val-hi'; }
        else{               status = '✓ Normal'; cls = 'ext-val-ok'; }
      }
      var refStr = (lo!=null&&hi!=null) ? lo+' – '+hi : '—';
      html += '<tr>' +
        '<td style="color:var(--text)">' + (bmd.label||k) + '</td>' +
        '<td style="text-align:right"><input class="ext-val-input" type="number" step="any" ' +
          'id="ev-'+k+'" value="'+val+'" oninput="updateExtracted(\''+k+'\',this.value)"></td>' +
        '<td style="color:var(--dim)">' + (bmd.unit||'') + '</td>' +
        '<td style="color:var(--dim);font-size:.72rem">' + refStr + '</td>' +
        '<td class="'+cls+'" style="font-size:.72rem">' + status + '</td>' +
        '</tr>';
    });
    html += '</tbody></table>';
  });

  // Unfound markers — show count
  var notFound = found.filter(function(k){
    return !cats.some(function(c){ return c.keys.indexOf(k)>=0; });
  });
  if(notFound.length){
    html += '<div style="padding:.5rem 1rem;font-size:.71rem;color:var(--dim)">' +
      'Otros: ' + notFound.map(function(k){ return k+': '+extracted[k]; }).join(' · ') + '</div>';
  }

  if(!found.length){
    html = '<div style="padding:2rem 1rem;text-align:center;color:var(--muted)">' +
      '<div style="font-size:2rem;margin-bottom:.5rem">📋</div>' +
      '<div style="font-family:\'Oswald\',sans-serif;font-size:.85rem">No se detectaron valores automáticamente</div>' +
      '<div style="font-size:.75rem;margin-top:.3rem">Usa el panel de edición manual para ingresar los valores</div>' +
      '</div>';
    // Show manual edit panel automatically
    document.getElementById('manual-edit-panel').style.display = '';
  }

  container.innerHTML = html;
}

function updateExtracted(key, val){
  var n = parseFloat(val);
  if(!isNaN(n)) _upExtracted[key] = n;
  else delete _upExtracted[key];
}

function toggleManualEdit(){
  var p = document.getElementById('manual-edit-panel');
  p.style.display = p.style.display === 'none' ? '' : 'none';
  if(p.style.display !== 'none' && typeof buildForm === 'function'){
    buildForm();
    // Re-populate from current extracted
    Object.entries(_upExtracted).forEach(function(e){
      var el = document.getElementById('fi-'+e[0]);
      if(el) el.value = e[1];
    });
  }
}

function saveExtracted(){
  var dateVal = document.getElementById('res-date').value;
  if(!dateVal){ showSaveMsg('⚠ Selecciona la fecha del examen','err'); return; }

  // Merge with any manual edits from form-cats-container
  var values = Object.assign({}, _upExtracted);
  if(typeof FORM_CATS !== 'undefined'){
    FORM_CATS.forEach(function(cat){
      cat.keys.forEach(function(k){
        var el = document.getElementById('fi-'+k);
        if(el && el.value !== '') values[k] = parseFloat(el.value);
      });
    });
  }

  if(!Object.keys(values).length){ showSaveMsg('⚠ No hay valores para guardar','err'); return; }

  var newExam = {
    date: dateVal,
    lab:  document.getElementById('res-lab').value  || 'Laboratorio Clínico',
    context: document.getElementById('res-ctx').value || '',
    values: values
  };

  var idx = EXAMS.findIndex(function(e){ return e.date === dateVal; });
  if(idx >= 0){ EXAMS[idx] = newExam; }
  else{ EXAMS.push(newExam); EXAMS.sort(function(a,b){ return a.date<b.date?-1:1; }); }

  localStorage.setItem('kl_blood_labs', JSON.stringify({biomarkers:BM, exams:EXAMS}));

  EXAM_IDX = EXAMS.length-1;
  COMP_IDX = EXAMS.length-2;
  buildExamSelectors();
  renderAll();

  showSaveMsg('✅ Examen del '+dateVal+' guardado con '+Object.keys(values).length+' marcadores.','ok');
}
'''

# Find a good insertion point: right before the closing </script> of the main block (after showSaveMsg)
# We look for the last occurrence of "function showSaveMsg" and add after it
idx = c.rfind('function showSaveMsg')
# Find the closing brace of showSaveMsg
end = c.find('\n}', idx) + 2
c = c[:end] + '\n' + UPLOAD_JS + c[end:]
print('OK upload JS injected')

with open('C:/Users/rafae/projects/LabX/blood_labs.html', 'w', encoding='utf-8') as f:
    f.write(c)
print('Saved blood_labs.html')
