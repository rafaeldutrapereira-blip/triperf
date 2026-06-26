/**
 * lx-info.js — Sistema universal de tooltips informativos para LabX
 * Panel lateral contextual con definición + rango + interpretación del valor actual.
 * Uso: lxInfo.show('ctl', 72) o <button onclick="lxInfo.show('ctl',72)">ℹ</button>
 */
(function(){
'use strict';

/* ── Diccionario de métricas ─────────────────────────────────────────── */
var METRICS = {

  ctl: {
    nombre: 'CTL — Carga Crónica de Entrenamiento',
    emoji: '📈',
    definicion: 'Mide tu nivel de <strong>fitness acumulado</strong> durante los últimos 42 días. Cuanto más alto, más forma tienes construida. Sube despacio con entrenamiento consistente y baja cuando descansas o te lesionas.',
    formula: 'CTL = promedio exponencial de TSS diario (constante de tiempo: 42 días)',
    rangos: [
      {min:0,   max:30,  label:'Principiante',    color:'#6B7280', advice:'Estás comenzando. Sé paciente y consistente — cada semana suma.'},
      {min:30,  max:60,  label:'Recreativo',       color:'#0EA5E9', advice:'Buena base para carreras populares (5K, 10K, sprint triatlón).'},
      {min:60,  max:90,  label:'Amateur competitivo', color:'#10B981', advice:'Rango sólido para medio ironman y maratón.'},
      {min:90,  max:120, label:'Amateur avanzado',  color:'#F59E0B', advice:'Nivel de atleta serio. Requiere recuperación bien gestionada.'},
      {min:120, max:999, label:'Elite / Pro',       color:'#A855F7', advice:'Zona de alto rendimiento. Monitorear fatiga de cerca.'},
    ],
    meta_triathlon: 'Ironman: 100–140 · 70.3: 70–100 · Sprint: 40–70',
    pro_tip: 'Intenta no subir más de 5–7 puntos por semana para evitar lesiones.',
    unidad: 'puntos',
  },

  atl: {
    nombre: 'ATL — Carga Aguda (Fatiga)',
    emoji: '🔥',
    definicion: 'Mide la <strong>fatiga acumulada</strong> de los últimos 7 días. Un ATL alto significa que has entrenado fuerte recientemente. Es normal y necesario — la fatiga precede a la mejora.',
    formula: 'ATL = promedio exponencial de TSS diario (constante de tiempo: 7 días)',
    rangos: [
      {min:0,   max:40,  label:'Baja fatiga',      color:'#10B981', advice:'Estás fresco. Bueno para competir o hacer una sesión exigente.'},
      {min:40,  max:80,  label:'Fatiga moderada',   color:'#F59E0B', advice:'Fatiga normal de entrenamiento. Asegura buen sueño y nutrición.'},
      {min:80,  max:120, label:'Fatiga alta',       color:'#EF4444', advice:'Cuerpo bajo estrés. Prioriza recuperación activa y descanso.'},
      {min:120, max:999, label:'Fatiga extrema',    color:'#7C2D12', advice:'Riesgo de sobreentrenamiento. Reduce carga esta semana.'},
    ],
    meta_triathlon: 'Normal en pico de entrenamiento: 80–110 · En taper: bajar a 40–60',
    pro_tip: 'El ATL alto por sí solo no es malo — lo que importa es la relación ATL/CTL (ACWR).',
    unidad: 'puntos',
  },

  tsb: {
    nombre: 'TSB — Forma / Frescura',
    emoji: '⚡',
    definicion: 'Indica tu <strong>frescura y disposición para rendir</strong>. Es simplemente CTL menos ATL. Positivo = estás descansado. Negativo = estás fatigado (pero entrenando fuerte). El objetivo es llegar a competencia con TSB entre 0 y +20.',
    formula: 'TSB = CTL − ATL',
    rangos: [
      {min:-999, max:-20, label:'Bajo fatiga intensa', color:'#EF4444', advice:'Muy fatigado. Necesitas reducir carga antes de competir.'},
      {min:-20,  max:-5,  label:'Entrenando duro',    color:'#F59E0B', advice:'Normal en bloque de carga. Aguanta — la forma viene al descansar.'},
      {min:-5,   max:5,   label:'Equilibrio',          color:'#10B981', advice:'Balance entre fitness y fatiga. Buen estado para sesiones largas.'},
      {min:5,    max:20,  label:'Forma positiva ✓',   color:'#22D3EE', advice:'Ideal para competir. Estás fresco y con buena forma acumulada.'},
      {min:20,   max:999, label:'Muy descansado',     color:'#6B7280', advice:'Muy fresco. Si llevas semanas así, podrías estar perdiendo forma.'},
    ],
    meta_triathlon: 'Día de carrera ideal: entre +5 y +15',
    pro_tip: 'El TSB es el número más importante en los 7 días previos a competencia.',
    unidad: 'puntos (CTL − ATL)',
  },

  acwr: {
    nombre: 'ACWR — Ratio de Carga Aguda/Crónica',
    emoji: '🛡',
    definicion: 'Mide si estás <strong>aumentando la carga demasiado rápido</strong>. Compara lo que hiciste esta semana vs el promedio de las últimas 4. Es el mejor predictor científico de riesgo de lesión.',
    formula: 'ACWR = ATL ÷ CTL',
    rangos: [
      {min:0,    max:0.8,  label:'Zona segura baja',  color:'#0EA5E9', advice:'Estás haciendo menos de lo habitual. Puede ser bueno si descansas, malo si bajas demasiado el volumen.'},
      {min:0.8,  max:1.3,  label:'Zona óptima ✓',    color:'#10B981', advice:'Rango seguro. Progresión controlada, riesgo de lesión mínimo.'},
      {min:1.3,  max:1.5,  label:'Zona de alerta',   color:'#F59E0B', advice:'Carga más alta que tu promedio. Cuida el sueño y la alimentación.'},
      {min:1.5,  max:999,  label:'Zona de riesgo ⚠', color:'#EF4444', advice:'Riesgo elevado de lesión o enfermedad. Reduce carga esta semana.'},
    ],
    meta_triathlon: 'Mantener entre 0.8 y 1.3 durante todo el período de entrenamiento',
    pro_tip: 'Si subes de volumen más del 10% por semana, el ACWR probablemente supere 1.3.',
    unidad: 'ratio (sin unidad)',
  },

  tss: {
    nombre: 'TSS — Training Stress Score',
    emoji: '💪',
    definicion: 'Mide el <strong>estrés total de un entrenamiento o semana</strong>. Considera duración e intensidad juntos. Una hora a máximo esfuerzo = ~100 TSS. Una hora fácil = ~40–50 TSS.',
    formula: 'TSS = (duración_seg × NP × IF) / (FTP × 3600) × 100',
    rangos: [
      {min:0,   max:100,  label:'Sesión suave',      color:'#10B981', advice:'Recuperación activa o sesión corta.'},
      {min:100, max:200,  label:'Sesión moderada',   color:'#0EA5E9', advice:'Entrenamiento estándar de fondo o intensidad media.'},
      {min:200, max:300,  label:'Sesión exigente',   color:'#F59E0B', advice:'Sesión larga o de alta intensidad. Planifica recuperación.'},
      {min:300, max:999,  label:'Sesión extrema',    color:'#EF4444', advice:'Muy demandante (ej: un Ironman). 2–3 días de recuperación mínimo.'},
    ],
    meta_semana: 'Principiante: 200–350 · Intermedio: 350–550 · Avanzado: 550–800',
    pro_tip: 'Suma TSS de todas tus sesiones para calcular la carga semanal total.',
    unidad: 'puntos',
  },

  hrv: {
    nombre: 'HRV — Variabilidad de la Frecuencia Cardíaca',
    emoji: '❤️',
    definicion: 'Mide las <strong>pequeñas variaciones entre latidos</strong> del corazón. Un HRV alto = sistema nervioso descansado y listo para esfuerzo. Un HRV bajo = estrés, fatiga o enfermedad incipiente.',
    formula: 'HRV = desviación estándar de intervalos RR (medido en reposo, mañana)',
    rangos: [
      {min:0,   max:30,  label:'Muy bajo',    color:'#EF4444', advice:'Señal de estrés alto o enfermedad. Considera descanso hoy.'},
      {min:30,  max:50,  label:'Bajo',        color:'#F59E0B', advice:'Por debajo de tu línea base. Sesión suave máximo.'},
      {min:50,  max:80,  label:'Normal',      color:'#10B981', advice:'Listo para entrenar normalmente.'},
      {min:80,  max:999, label:'Alto ✓',     color:'#22D3EE', advice:'Sistema nervioso en óptimas condiciones. Aprovecha para sesión intensa.'},
    ],
    pro_tip: 'Lo importante es tu propio rango base — no compartes con otros. Un HRV de 45ms puede ser excelente para ti.',
    unidad: 'ms (milisegundos)',
  },

  vo2max: {
    nombre: 'VO2 Máx — Capacidad Aeróbica Máxima',
    emoji: '🫁',
    definicion: 'Mide cuánto oxígeno puede procesar tu cuerpo por minuto por kilo de peso. Es el mayor predictor de rendimiento en deportes de resistencia. Mejora con entrenamiento durante meses/años.',
    formula: 'Estimado por Garmin a partir de FC, ritmo y datos de movimiento',
    rangos: [
      {min:0,  max:35, label:'Bajo',            color:'#6B7280', advice:'Zona de salud básica. El entrenamiento aeróbico mejorará esto significativamente.'},
      {min:35, max:45, label:'Moderado',        color:'#0EA5E9', advice:'Nivel recreativo. Suficiente para terminar un sprint o olímpico triatlón.'},
      {min:45, max:55, label:'Bueno',           color:'#10B981', advice:'Nivel amateur competitivo. Capaz de completar ironman con buen tiempo.'},
      {min:55, max:65, label:'Muy bueno',       color:'#F59E0B', advice:'Top 10-20% de atletas recreativos. Clasificado para grupos de edad.'},
      {min:65, max:999,label:'Excelente / Elite',color:'#A855F7', advice:'Nivel de atleta de elite. VO2max de ciclistas Pro: 70–90.'},
    ],
    pro_tip: 'El VO2max de Garmin es una estimación — un test en laboratorio da el valor real.',
    unidad: 'ml/kg/min',
  },

  ftp: {
    nombre: 'FTP — Potencia Umbral Funcional',
    emoji: '⚡',
    definicion: 'La máxima potencia (en vatios) que puedes sostener durante <strong>una hora</strong> sin entrar en deuda de oxígeno. Es la base para calcular todas las zonas de entrenamiento en ciclismo.',
    formula: 'FTP = promedio de potencia en test de 20 min × 0.95',
    rangos: [
      {min:0,   max:150, label:'Principiante',  color:'#6B7280', advice:''},
      {min:150, max:220, label:'Recreativo',    color:'#0EA5E9', advice:''},
      {min:220, max:300, label:'Amateur',       color:'#10B981', advice:''},
      {min:300, max:380, label:'Avanzado',      color:'#F59E0B', advice:''},
      {min:380, max:999, label:'Pro / Elite',   color:'#A855F7', advice:''},
    ],
    pro_tip: 'Más importante que el FTP absoluto es el W/kg: divide FTP ÷ peso corporal. Triatetas elite apuntan a 4–5 W/kg.',
    unidad: 'vatios (W)',
  },

  css: {
    nombre: 'CSS — Critical Swim Speed',
    emoji: '🏊',
    definicion: 'El ritmo (en seg/100m) que puedes mantener en natación durante un esfuerzo largo sin entrar en déficit de oxígeno. Equivalente al umbral de lactato en natación.',
    formula: 'CSS = (400m − 200m) / (t400 − t200) — test de campo de 2 pruebas',
    rangos: [
      {min:0,   max:90,  label:'Elite',         color:'#A855F7', advice:'Ritmos de menos de 1:30/100m — nadador de alto nivel.'},
      {min:90,  max:110, label:'Avanzado',      color:'#10B981', advice:'Buena base para triatlón olímpico e ironman.'},
      {min:110, max:130, label:'Intermedio',    color:'#F59E0B', advice:'Enfócate en técnica para bajar este número.'},
      {min:130, max:999, label:'Principiante',  color:'#0EA5E9', advice:'Incrementa volumen de natación progresivamente.'},
    ],
    pro_tip: 'Haz el test CSS cada 6–8 semanas para ajustar tus zonas de entrenamiento en agua.',
    unidad: 'seg/100m (menor = más rápido)',
  },

  rpe: {
    nombre: 'RPE — Esfuerzo Percibido',
    emoji: '😤',
    definicion: 'Escala del <strong>1 al 10</strong> que mide cuán difícil sintió el entrenamiento. Es tan válida como la frecuencia cardíaca para monitorear intensidad. Muy útil cuando no tienes sensor de FC o potenciómetro.',
    formula: 'Escala de Borg modificada: 1 = sentado, 10 = esfuerzo máximo imposible de mantener',
    rangos: [
      {min:1, max:3, label:'Muy fácil',          color:'#10B981', advice:'Recuperación activa. Podrías mantenerlo horas.'},
      {min:3, max:5, label:'Fácil–Moderado',     color:'#0EA5E9', advice:'Zona 2. Puedes hablar con frases completas.'},
      {min:5, max:7, label:'Moderado–Difícil',   color:'#F59E0B', advice:'Umbral. Puedes hablar palabras sueltas.'},
      {min:7, max:9, label:'Difícil',            color:'#EF4444', advice:'VO2max. Solo puedes aguantar minutos.'},
      {min:9, max:10,label:'Máximo',             color:'#7C2D12', advice:'All-out. Solo segundos a este esfuerzo.'},
    ],
    pro_tip: 'Si tu RPE es mucho más alto de lo esperado para esa intensidad, es señal de fatiga acumulada.',
    unidad: '1–10 (subjetivo)',
  },

  readiness: {
    nombre: 'Readiness — Disposición para Entrenar',
    emoji: '🟢',
    definicion: 'Puntuación combinada (0–100) que estima <strong>cuán listo estás para entrenar hoy</strong>. Combina datos de HRV, sueño, bienestar subjetivo y carga de los últimos días.',
    formula: 'Algoritmo interno: HRV (40%) + sueño (30%) + bienestar (20%) + TSB (10%)',
    rangos: [
      {min:0,  max:30, label:'Descansar hoy',      color:'#EF4444', advice:'Tu cuerpo necesita recuperación. Haz sesión muy suave o descansa.'},
      {min:30, max:60, label:'Entrenamiento ligero',color:'#F59E0B', advice:'Sesión moderada OK. Evita intervalos de alta intensidad.'},
      {min:60, max:80, label:'Listo para entrenar', color:'#10B981', advice:'Buenas condiciones. Puedes hacer tu sesión planificada.'},
      {min:80, max:100,label:'Óptimo ✓',           color:'#22D3EE', advice:'Condiciones ideales. Aprovecha para sesión exigente o test.'},
    ],
    pro_tip: 'Si el Readiness está bajo pero tienes una carrera, prioriza la carrera y recupera después.',
    unidad: '0–100 puntos',
  },

  if_metric: {
    nombre: 'IF — Factor de Intensidad',
    emoji: '🎯',
    definicion: 'Ratio entre la <strong>potencia normalizada</strong> de un entrenamiento y tu FTP. Mide la intensidad relativa de la sesión independientemente de la duración.',
    formula: 'IF = NP ÷ FTP',
    rangos: [
      {min:0,    max:0.75, label:'Recuperación',   color:'#6B7280', advice:''},
      {min:0.75, max:0.85, label:'Endurance',      color:'#0EA5E9', advice:'Zona 2, fondo largo.'},
      {min:0.85, max:0.95, label:'Tempo / Sweet Spot', color:'#10B981', advice:'Zona 3-4, umbral inferior.'},
      {min:0.95, max:1.05, label:'Umbral',         color:'#F59E0B', advice:'Trabajo a FTP o cerca.'},
      {min:1.05, max:999,  label:'VO2max +',       color:'#EF4444', advice:'Intervalos cortos de alta intensidad.'},
    ],
    pro_tip: 'Un IF > 1.05 en más de una hora indica que tu FTP podría estar subestimado.',
    unidad: 'ratio (sin unidad)',
  },

  np: {
    nombre: 'NP — Potencia Normalizada',
    emoji: '📊',
    definicion: 'La potencia que <strong>biológicamente costó</strong> el entrenamiento, ajustada para el impacto de los cambios de intensidad. Una sesión de intervalos cuesta más que una sesión estable con el mismo promedio de vatios.',
    formula: 'NP = raíz cuarta de la media de (potencia⁴ en ventanas de 30 seg)',
    pro_tip: 'NP siempre es mayor o igual que la potencia promedio. La diferencia indica cuánto variaste la intensidad.',
    unidad: 'vatios (W)',
  },

  lthr: {
    nombre: 'LTHR — Frecuencia Cardíaca en Umbral Láctico',
    emoji: '💓',
    definicion: 'La frecuencia cardíaca máxima que puedes mantener durante un esfuerzo sostenido sin acumular lactato de forma progresiva. Por encima de este punto el esfuerzo se vuelve insostenible.',
    formula: 'Estimado como 92–94% FCmáx, o test de 20–30 min a máximo esfuerzo sostenido',
    pro_tip: 'El LTHR es diferente por deporte: normalmente es 5–10 lpm más bajo en ciclismo que en carrera.',
    unidad: 'lpm (latidos por minuto)',
  },

  nutricion_cho: {
    nombre: 'Carbohidratos por hora (CHO/h)',
    emoji: '🍌',
    definicion: 'Cantidad de carbohidratos en gramos que debes consumir <strong>por hora de esfuerzo</strong> para mantener el rendimiento. El intestino puede absorber hasta 60g/h de glucosa sola, o hasta 90g/h si mezclas glucosa + fructosa.',
    rangos: [
      {min:0,  max:30,  label:'Sesión corta (<1h)',     color:'#10B981', advice:'Agua sola puede ser suficiente.'},
      {min:30, max:60,  label:'Sesión media (1–2h)',    color:'#0EA5E9', advice:'60 g/h solo glucosa (geles, plátano).'},
      {min:60, max:90,  label:'Sesión larga (2–4h)',    color:'#F59E0B', advice:'Mezcla glucosa+fructosa 2:1 para llegar a 90 g/h.'},
      {min:90, max:999, label:'Ultra-endurance (>4h)',  color:'#A855F7', advice:'Hasta 120 g/h con entrenamiento intestinal.'},
    ],
    pro_tip: 'El intestino se puede "entrenar" para absorber más. Practica la nutrición en tus entrenamientos largos.',
    unidad: 'g/hora',
  },

  nutricion_sodio: {
    nombre: 'Sodio por hora',
    emoji: '🧂',
    definicion: 'El sodio perdido en el sudor debe reponerse para evitar <strong>hiponatremia</strong> (sodio bajo) y calambres. Las pérdidas varían mucho por persona y condiciones climáticas.',
    rangos: [
      {min:0,   max:500,  label:'Clima frío / baja sudoración',  color:'#10B981', advice:''},
      {min:500, max:1000, label:'Clima templado / normal',        color:'#F59E0B', advice:'Rango estándar para la mayoría.'},
      {min:1000,max:999,  label:'Clima caliente / alta sudoración', color:'#EF4444', advice:'Deportistas que sudan mucho o en calor extremo.'},
    ],
    pro_tip: 'El test de sudoración (sweat test) en laboratorio da tu tasa exacta de pérdida de sodio.',
    unidad: 'mg/hora',
  },

};

/* ── HTML del panel ──────────────────────────────────────────────────── */
var _panelEl = null;

function _ensurePanel(){
  if(_panelEl) return;
  var div = document.createElement('div');
  div.id = 'lx-info-panel';
  div.innerHTML = [
    '<div id="lx-info-overlay" onclick="lxInfo.hide()"></div>',
    '<div id="lx-info-drawer">',
    '  <button id="lx-info-close" onclick="lxInfo.hide()" aria-label="Cerrar">✕</button>',
    '  <div id="lx-info-body"></div>',
    '</div>',
  ].join('');
  document.body.appendChild(div);
  _panelEl = div;

  // Inyectar CSS inline si no está ya
  if(!document.getElementById('lx-info-css')){
    var s = document.createElement('style');
    s.id = 'lx-info-css';
    s.textContent = [
      '#lx-info-overlay{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9998;opacity:0;pointer-events:none;transition:opacity .25s}',
      '#lx-info-drawer{position:fixed;top:0;right:0;height:100%;width:min(420px,96vw);background:#111827;border-left:1px solid rgba(255,255,255,.08);z-index:9999;transform:translateX(100%);transition:transform .3s cubic-bezier(.4,0,.2,1);overflow-y:auto;padding:1.5rem 1.35rem 2rem}',
      '#lx-info-panel.open #lx-info-overlay{opacity:1;pointer-events:auto}',
      '#lx-info-panel.open #lx-info-drawer{transform:translateX(0)}',
      '#lx-info-close{position:sticky;top:0;float:right;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12);color:#9CA3AF;width:28px;height:28px;border-radius:6px;font-size:.85rem;cursor:pointer;margin-bottom:1rem}',
      '#lx-info-body h2{font-family:"Oswald",sans-serif;font-size:1.1rem;font-weight:700;letter-spacing:.04em;color:#F9FAFB;margin:0 0 .35rem;display:flex;align-items:center;gap:.45rem}',
      '#lx-info-body .li-unit{font-size:.68rem;font-weight:500;letter-spacing:.12em;text-transform:uppercase;color:#6B7280;margin-bottom:1.1rem;display:block}',
      '#lx-info-body .li-def{font-size:.85rem;line-height:1.65;color:#D1D5DB;margin-bottom:1.1rem}',
      '#lx-info-body .li-def strong{color:#F9FAFB;font-weight:600}',
      '#lx-info-body .li-formula{font-size:.75rem;font-family:monospace;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);border-radius:6px;padding:.55rem .75rem;color:#9CA3AF;margin-bottom:1.1rem;word-break:break-word}',
      '.li-range-bar{margin-bottom:.5rem}',
      '.li-range-row{display:flex;align-items:center;gap:.55rem;padding:.4rem .6rem;border-radius:6px;transition:background .15s}',
      '.li-range-row.active{background:rgba(255,255,255,.07)}',
      '.li-range-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}',
      '.li-range-label{font-size:.78rem;font-weight:600;color:#F9FAFB;flex:1}',
      '.li-range-advice{font-size:.72rem;color:#9CA3AF;line-height:1.5}',
      '.li-current-box{border-radius:8px;padding:.75rem 1rem;margin:1.1rem 0;border:1px solid rgba(255,255,255,.1)}',
      '.li-current-box .li-cb-label{font-size:.65rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#6B7280;margin-bottom:.25rem}',
      '.li-current-box .li-cb-val{font-family:"Oswald",sans-serif;font-size:2rem;font-weight:700;line-height:1}',
      '.li-current-box .li-cb-interp{font-size:.78rem;color:#D1D5DB;margin-top:.35rem;line-height:1.5}',
      '.li-section-title{font-size:.65rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#6B7280;margin:1.1rem 0 .45rem}',
      '.li-pro-tip{background:rgba(14,165,233,.08);border:1px solid rgba(14,165,233,.2);border-radius:8px;padding:.65rem .85rem;font-size:.78rem;color:#7DD3FC;line-height:1.55}',
      '.li-pro-tip::before{content:"💡 ";font-style:normal}',
      '.lx-info-btn{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);color:#9CA3AF;font-size:.7rem;font-weight:700;cursor:pointer;flex-shrink:0;transition:all .15s;vertical-align:middle;margin-left:.3rem;line-height:1}',
      '.lx-info-btn:hover{background:rgba(14,165,233,.2);border-color:rgba(14,165,233,.5);color:#7DD3FC}',
    ].join('\n');
    document.head.appendChild(s);
  }
}

/* ── Buscar el rango activo ──────────────────────────────────────────── */
function _findRange(m, val){
  if(!m.rangos || val == null) return null;
  var num = parseFloat(val);
  for(var i=0;i<m.rangos.length;i++){
    var r = m.rangos[i];
    if(num >= r.min && num < r.max) return r;
  }
  return m.rangos[m.rangos.length-1];
}

/* ── Render HTML del panel ───────────────────────────────────────────── */
function _render(metricId, currentValue){
  var m = METRICS[metricId];
  if(!m) return '<p style="color:#9CA3AF">Métrica no encontrada: '+metricId+'</p>';

  var activeRange = _findRange(m, currentValue);
  var html = '';

  // Título
  html += '<h2>'+m.emoji+' '+m.nombre+'</h2>';
  if(m.unidad) html += '<span class="li-unit">Unidad: '+m.unidad+'</span>';

  // Valor actual (si se pasó)
  if(currentValue != null && currentValue !== ''){
    var col = activeRange ? activeRange.color : '#F9FAFB';
    html += '<div class="li-current-box" style="background:'+col+'12;border-color:'+col+'33">'
      +'<div class="li-cb-label">Tu valor actual</div>'
      +'<div class="li-cb-val" style="color:'+col+'">'+currentValue+(m.unidad&&m.unidad.indexOf('puntos')>-1?'':'')+' <span style="font-size:1rem;font-weight:400;color:#6B7280">'+m.unidad+'</span></div>'
      +(activeRange?'<div class="li-cb-interp"><strong style="color:'+col+'">'+activeRange.label+'</strong>'+(activeRange.advice?' — '+activeRange.advice:'')+'</div>':'')
      +'</div>';
  }

  // Definición
  html += '<div class="li-section-title">Qué mide</div>';
  html += '<div class="li-def">'+m.definicion+'</div>';

  // Fórmula / método
  if(m.formula){
    html += '<div class="li-section-title">Cómo se calcula</div>';
    html += '<div class="li-formula">'+m.formula+'</div>';
  }

  // Rangos
  if(m.rangos && m.rangos.length){
    html += '<div class="li-section-title">Rangos de referencia</div>';
    html += '<div class="li-range-bar">';
    m.rangos.forEach(function(r){
      var isActive = activeRange === r;
      html += '<div class="li-range-row'+(isActive?' active':'')+'">'
        +'<div class="li-range-dot" style="background:'+r.color+'"></div>'
        +'<div>'
        +'<div class="li-range-label" style="color:'+r.color+'">'
        +(isActive?'▶ ':'')+r.label+' <span style="font-size:.65rem;font-weight:400;color:#6B7280">('+r.min+' – '+(r.max===999?'∞':r.max)+')</span>'
        +'</div>'
        +(r.advice?'<div class="li-range-advice">'+r.advice+'</div>':'')
        +'</div></div>';
    });
    html += '</div>';
  }

  // Meta triatlón / semana
  if(m.meta_triathlon){
    html += '<div class="li-section-title">Referencia triatlón</div>';
    html += '<div class="li-def" style="font-size:.78rem">'+m.meta_triathlon+'</div>';
  }
  if(m.meta_semana){
    html += '<div class="li-section-title">Meta semanal</div>';
    html += '<div class="li-def" style="font-size:.78rem">'+m.meta_semana+'</div>';
  }

  // Pro tip
  if(m.pro_tip){
    html += '<div class="li-pro-tip">'+m.pro_tip+'</div>';
  }

  return html;
}

/* ── API pública ─────────────────────────────────────────────────────── */
window.lxInfo = {

  show: function(metricId, currentValue){
    _ensurePanel();
    document.getElementById('lx-info-body').innerHTML = _render(metricId, currentValue);
    _panelEl.classList.add('open');
    document.body.style.overflow = 'hidden';
  },

  hide: function(){
    if(_panelEl) _panelEl.classList.remove('open');
    document.body.style.overflow = '';
  },

  /** Genera el botón ℹ inline. value puede ser un número o un selector CSS para leerlo. */
  btn: function(metricId, valueOrSelector, extraStyle){
    var js = valueOrSelector
      ? ('var _v=typeof '+JSON.stringify(valueOrSelector)+'==="string"&&'+JSON.stringify(valueOrSelector)+'.startsWith("#")?+(document.querySelector('+JSON.stringify(valueOrSelector)+')&&document.querySelector('+JSON.stringify(valueOrSelector)+').textContent.replace(/[^0-9.-]/g,""))||null:'+JSON.stringify(valueOrSelector)+';lxInfo.show('+JSON.stringify(metricId)+',_v)')
      : 'lxInfo.show('+JSON.stringify(metricId)+',null)';
    return '<button type="button" class="lx-info-btn" onclick="'+js.replace(/"/g,'&quot;')+'" title="¿Qué es '+metricId.toUpperCase()+'?" aria-label="Info sobre '+(METRICS[metricId]?METRICS[metricId].nombre:metricId)+'"'+(extraStyle?' style="'+extraStyle+'"':'')+'>ℹ</button>';
  },

  /** Agrega botón ℹ a todos los elementos que tengan [data-lx-info] */
  autoInit: function(){
    document.querySelectorAll('[data-lx-info]').forEach(function(el){
      if(el.querySelector('.lx-info-btn')) return; // ya tiene
      var mid   = el.getAttribute('data-lx-info');
      var vsel  = el.getAttribute('data-lx-info-val') || null;
      var btn   = document.createElement('button');
      btn.type  = 'button';
      btn.className = 'lx-info-btn';
      btn.title = '¿Qué es esto?';
      btn.setAttribute('aria-label','Más información');
      btn.textContent = 'ℹ';
      btn.addEventListener('click', function(e){
        e.stopPropagation();
        var val = null;
        if(vsel){
          var target = document.querySelector(vsel);
          if(target) val = parseFloat(target.textContent.replace(/[^0-9.-]/g,'')) || null;
        }
        lxInfo.show(mid, val);
      });
      el.appendChild(btn);
    });
  },
};

/* Cerrar con Escape */
document.addEventListener('keydown', function(e){ if(e.key==='Escape') lxInfo.hide(); });

/* Auto-init cuando DOM listo */
if(document.readyState==='loading'){
  document.addEventListener('DOMContentLoaded', lxInfo.autoInit);
}else{
  setTimeout(lxInfo.autoInit, 100);
}

})();
