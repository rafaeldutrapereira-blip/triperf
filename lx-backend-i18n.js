/* lx-backend-i18n.js — traduccion de textos que el backend genera en espanol.
   El backend (training_service, recovery_routes, readiness_service,
   injury_risk_service, performance_analytics_service, race_routes) devuelve
   estas frases en espanol. lxBeT() las traduce por coincidencia exacta o por
   plantilla ({marcador}); los nombres de deporte dentro de las plantillas
   ({sport}, {label}) se traducen con LX_BE_SPORT. Si el texto no esta en el
   mapa, lo devuelve sin cambios. Mantener en sincronia con
   api/tests/test_backend_i18n_mapping.py. */
var LX_BE_ENTRIES = [
 [
  "Sin datos suficientes para ACWR",
  "be_013"
 ],
 [
  "Necesitas al menos 7 días de actividad para calcular tu ratio de carga.",
  "be_014"
 ],
 [
  "⚠️ Alto riesgo de lesión",
  "be_015"
 ],
 [
  "Fatiga acumulada",
  "be_059"
 ],
 [
  "Carga elevada",
  "be_060"
 ],
 [
  "Carga por debajo de lo óptimo",
  "be_061"
 ],
 [
  "Estado de forma óptimo",
  "be_062"
 ],
 [
  "TSB {tsb} indica fatiga acumulada severa. Descanso obligatorio.",
  "be_069"
 ],
 [
  "Tu TSB ({tsb}) indica fatiga acumulada severa. Descanso obligatorio.",
  "be_070"
 ],
 [
  "TSB {tsb}. Mantén intensidad pero reduce volumen esta semana.",
  "be_071"
 ],
 [
  "TSB {tsb} — estás fresco y en buena forma. Ideal para competir o testear.",
  "be_072"
 ],
 [
  "TSB {tsb} — fatiga acumulada muy alta. Riesgo de sobreentrenamiento activo.",
  "be_073"
 ],
 [
  "TSB {tsb}: programa al menos 4-5 días de taper antes del próximo estímulo duro.",
  "be_074"
 ],
 [
  "Fatiga acumulada alta (TSB {tsb}). Considera 2-3 días de carga reducida.",
  "be_075"
 ],
 [
  "TSB {tsb} — bloque de fatiga severa. Considera reducir carga 3-5 días.",
  "be_076"
 ],
 [
  "Monotonía {monotony} — las sesiones son muy similares entre sí. Agrega variedad.",
  "be_077"
 ],
 [
  "Monotonía de entrenamiento {monotony} (>2.5 = sobreentrenamiento silencioso).",
  "be_078"
 ],
 [
  "Varía el tipo y duración de sesiones. Incluye 1 día de descanso completo esta semana.",
  "be_079"
 ],
 [
  "Tu ACWR es bajo. Puedes aumentar volumen o intensidad gradualmente.",
  "be_080"
 ],
 [
  "HRV {hrv_drop}% por debajo del promedio 7 días. Señal de fatiga sistémica.",
  "be_081"
 ],
 [
  "HRV levemente deprimido ({hrv_drop}% bajo promedio). Monitorear mañana.",
  "be_082"
 ],
 [
  "Tu ACWR ({acwr}) indica sobrecarga moderada. Prioriza recuperación.",
  "be_083"
 ],
 [
  "ACWR {acwr} — carga aguda muy elevada vs crónica. Zona de alto riesgo de lesión.",
  "be_084"
 ],
 [
  "Reduce el volumen de entrenamiento los próximos 3-5 días al 60-70% del habitual.",
  "be_085"
 ],
 [
  "ACWR {acwr} — zona de riesgo elevado. No aumentes carga esta semana.",
  "be_086"
 ],
 [
  "Mantén la carga estable esta semana. Evita sesiones de volumen alto.",
  "be_087"
 ],
 [
  "Prioriza recuperación hoy: sueño 8h+, hidratación, sesión suave máximo Z2.",
  "be_088"
 ],
 [
  "Reduce intensidad y volumen al 70% esta semana. Prioriza sueño y nutrición.",
  "be_089"
 ],
 [
  "✓ Carga bien gestionada. Puedes continuar con el plan habitual.",
  "be_090"
 ],
 [
  "⛔ RIESGO CRÍTICO: Descansa hoy. Consulta con tu coach antes de entrenar mañana.",
  "be_091"
 ],
 [
  "CRÍTICO",
  "be_092"
 ],
 [
  "Sin datos fisiológicos disponibles — DRS neutral (70)",
  "be_093"
 ],
 [
  "Recuperación",
  "be_094"
 ],
 [
  "HRV + Sueño",
  "be_095"
 ],
 [
  "Estado Mental",
  "be_096"
 ],
 [
  "Fatiga Neurocognitiva",
  "be_097"
 ],
 [
  "Bioquímica",
  "be_098"
 ],
 [
  "Óptimo",
  "be_099"
 ],
 [
  "Crítico",
  "be_100"
 ],
 [
  "Condiciones fisiológicas ideales. Aprovecha para sesiones de calidad.",
  "be_101"
 ],
 [
  "Sesión de alta intensidad o largo endurance según plan",
  "be_102"
 ],
 [
  "Buena disposición para entrenar. Ejecuta el plan con normalidad.",
  "be_103"
 ],
 [
  "Sigue el plan — intensidad moderada a alta según programa",
  "be_104"
 ],
 [
  "Readiness moderada. Ajusta la intensidad si sientes fatiga.",
  "be_105"
 ],
 [
  "Preferir Zona 2 — evitar series VO2 hoy",
  "be_106"
 ],
 [
  "Señales de fatiga acumulada. Considera reducir volumen o descansar.",
  "be_107"
 ],
 [
  "Solo Zona 1 o descanso activo (movilidad, natación suave)",
  "be_108"
 ],
 [
  "Cuerpo en estado de recuperación. El entrenamiento duro hoy puede lesionar.",
  "be_109"
 ],
 [
  "Descanso completo o recuperación activa muy suave",
  "be_110"
 ],
 [
  "🟢 Forma óptima",
  "be_111"
 ],
 [
  "🟡 Recuperación moderada",
  "be_112"
 ],
 [
  "🟡 Carga pendiente",
  "be_113"
 ],
 [
  "🔴 Recuperación insuficiente",
  "be_114"
 ],
 [
  "Recuperación óptima. Sistema nervioso listo para alta intensidad.",
  "be_115"
 ],
 [
  "Ventana ideal para trabajo de calidad: VO2max, umbrales o bloque de fuerza.",
  "be_116"
 ],
 [
  "Buenas condiciones. Puedes entrenar con intensidad normal.",
  "be_117"
 ],
 [
  "Monitora la respuesta — si el esfuerzo percibido supera lo esperado, modera.",
  "be_118"
 ],
 [
  "Recuperación moderada. Sesión a intensidad controlada recomendada.",
  "be_119"
 ],
 [
  "Carga de entrenamiento acumulada detectada (TSB bajo). No añadas intensidad extra hoy.",
  "be_120"
 ],
 [
  "HRV bajo baseline. El sistema nervioso no está completamente recuperado.",
  "be_121"
 ],
 [
  "Fatiga acumulada significativa. Sesión técnica suave o descanso activo.",
  "be_122"
 ],
 [
  "Prioriza dormir bien esta noche — un buen sueño puede revertir el score mañana.",
  "be_123"
 ],
 [
  "Recuperación insuficiente. El riesgo de lesión o sobreentrenamiento es alto.",
  "be_124"
 ],
 [
  "Descanso completo o movilidad suave. No ignores esta señal.",
  "be_125"
 ],
 [
  "HRV {delta}% bajo tu baseline ({base}ms). Recuperación neuro comprometida.",
  "be_126"
 ],
 [
  "HRV {delta}% sobre tu baseline. Forma potencialmente óptima.",
  "be_127"
 ],
 [
  "Sesión completa según plan. Alta intensidad disponible.",
  "be_128"
 ],
 [
  "Sesión moderada. Reduce intensidad al 75-80% del plan.",
  "be_129"
 ],
 [
  "Solo Z1-Z2. Técnica o recuperación activa. TSS ≤ 50.",
  "be_130"
 ],
 [
  "Descanso completo o stretching suave. Cero carga.",
  "be_131"
 ],
 [
  "HRV muy bajo. El sistema nervioso autónomo no está recuperado. Riesgo de sobreentrenamiento.",
  "be_132"
 ],
 [
  "Sueño insuficiente. El 75% de la hormona de crecimiento se libera en sueño profundo.",
  "be_133"
 ],
 [
  "🌙 Prioriza dormir 8h esta noche",
  "be_134"
 ],
 [
  "🧘 Estrés alto detectado — técnicas de relajación o meditación",
  "be_135"
 ],
 [
  "🫀 HRV bajo — protocolo de recuperación neuro (Z1, baño frío, respiración)",
  "be_136"
 ],
 [
  "Fatiga Moderada",
  "be_137"
 ],
 [
  "Fatiga Alta",
  "be_138"
 ],
 [
  "Sin datos",
  "be_139"
 ],
 [
  "Bajo (infracarga)",
  "be_140"
 ],
 [
  "Faltan al menos 7 días de carga registrada para calcular el ACWR.",
  "be_141"
 ],
 [
  "Aumenta la carga gradualmente para mantener adaptación.",
  "be_142"
 ],
 [
  "Zona óptima de carga. Mantén el patrón actual.",
  "be_143"
 ],
 [
  "Reduce la intensidad o volumen esta semana para consolidar.",
  "be_144"
 ],
 [
  "Riesgo real de lesión por sobrecarga. Prioriza recuperación.",
  "be_145"
 ],
 [
  "Análisis de sangre pendiente",
  "be_146"
 ],
 [
  "No tienes análisis de laboratorio en los últimos 90 días. Para atletas en carga, se recomienda cada trimestre.",
  "be_147"
 ],
 [
  "Solicita análisis completo: hemograma, ferritina, vitamina D, cortisol, testosterona, TSH.",
  "be_148"
 ],
 [
  "Semana de baja carga",
  "be_149"
 ],
 [
  "Si es semana de recuperación planificada, continúa. Si no, suma al menos 2 sesiones de calidad.",
  "be_150"
 ],
 [
  "Fatiga mental acumulada",
  "be_151"
 ],
 [
  "Reduce la carga cognitiva antes de sesiones clave. Prueba los protocolos de mindfulness en el módulo Mental.",
  "be_152"
 ],
 [
  "Valores estimados desde actividades recientes. Confirmar con test formal para mayor precisión.",
  "be_153"
 ],
 [
  "ACWR {sport}",
  "be_154"
 ],
 [
  "Objetivo: {carb_g_h}g carbohidratos/hora durante las partes activas.",
  "be_155"
 ],
 [
  "Fatiga mental alta. Prioriza descanso mental — un entrenamiento suave o día de recuperación.",
  "mentmsg_mfs_low"
 ],
 [
  "Ferritina",
  "be_156"
 ],
 [
  "Hemoglobina",
  "be_157"
 ],
 [
  "Vitamina D",
  "be_158"
 ],
 [
  "Cortisol matutino",
  "be_159"
 ],
 [
  "Creatina Quinasa",
  "be_160"
 ],
 [
  "Hierro bisglicinate 25-50mg/día en ayunas + vitamina C",
  "be_161"
 ],
 [
  "Hierro bisglicinate 25mg/día con vitamina C",
  "be_162"
 ],
 [
  "Revisión dietética — aumentar hierro hemo (carnes rojas 2×/sem)",
  "be_163"
 ],
 [
  "Descartar anemia ferropénica con médico — posible suplementación IV",
  "be_164"
 ],
 [
  "Hierro + vitamina B12 + ácido fólico — revisar absorción GI",
  "be_165"
 ],
 [
  "Vitamina D3 4000-6000 UI/día × 8-12 semanas + control analítico",
  "be_166"
 ],
 [
  "Vitamina D3 2000 UI/día + exposición solar 15min/día",
  "be_167"
 ],
 [
  "Vitamina D3 1000 UI/día mantenimiento",
  "be_168"
 ],
 [
  "Ashwagandha 600mg/día + magnesio glicinato 400mg noche",
  "be_169"
 ],
 [
  "Reducir estresores externos + adaptógenos (rhodiola 200mg)",
  "be_170"
 ],
 [
  "Creatina monohidrato 5g/día + proteína 2g/kg/día",
  "be_171"
 ],
 [
  "Reducir eccéntricos — priorizar natación y ciclismo",
  "be_172"
 ],
 [
  "Iniciar suplementación de hierro; repetir labs en 3-4 semanas",
  "be_173"
 ],
 [
  "Semana de recuperación activa: máx. 60% del volumen habitual, solo Z1-Z2",
  "be_174"
 ],
 [
  "Priorizar sueño 8-9h, reducir estresores externos, mindfulness 10min/día",
  "be_175"
 ],
 [
  "Labs en rango óptimo — continuar planificación normal",
  "be_176"
 ],
 [
  "Cortisol elevado → limitar sesiones >90min hasta normalización",
  "be_177"
 ]
];
var LX_BE_SPORT = {
 "natación": "opt_swim",
 "ciclismo": "opt_bike",
 "trote": "dash_sport_run",
 "carrera": "sp_run",
 "fuerza": "sp_force",
 "fuerza / prep. física": "sp_strength",
 "prep. física": "aa_prep_fisica"
};
(function(){
  var FIXED = {}, TEMPL = [];
  function escRe(s){ return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  LX_BE_ENTRIES.forEach(function(e){
    var es = e[0], key = e[1];
    if(es.indexOf('{') === -1){ FIXED[es] = key; return; }
    var names = [], parts = es.split(/\{(\w+)\}/), src = '';
    for(var i = 0; i < parts.length; i++){
      if(i % 2 === 0){ src += escRe(parts[i]); }
      else { names.push(parts[i]); src += '(.+?)'; }
    }
    TEMPL.push({ re: new RegExp('^' + src + '$'), key: key, names: names });
  });
  function tr(key, vars){
    var v = window.i18n ? window.i18n.t(key) : null;
    if(!v || v === key) return null;
    if(vars) Object.keys(vars).forEach(function(n){ v = v.split('{' + n + '}').join(vars[n]); });
    return v;
  }
  function sportName(v){
    var k = LX_BE_SPORT[String(v).toLowerCase()];
    var t = k ? tr(k) : null;
    if(!t) return v;
    /* conserva la minuscula inicial si el original la traia (p.ej. .lower() en el backend) */
    if(v.charAt(0) === v.charAt(0).toLowerCase() && t.charAt(0) !== t.charAt(0).toLowerCase()){
      t = t.charAt(0).toLowerCase() + t.slice(1);
    }
    return t;
  }
  window.lxSport = sportName;
  function one(text){
    if(Object.prototype.hasOwnProperty.call(FIXED, text)){ return tr(FIXED[text]) || text; }
    for(var i = 0; i < TEMPL.length; i++){
      var m = TEMPL[i].re.exec(text);
      if(m){
        var vars = {};
        TEMPL[i].names.forEach(function(n, j){
          vars[n] = (n === 'sport' || n === 'label') ? sportName(m[j + 1]) : m[j + 1];
        });
        return tr(TEMPL[i].key, vars) || text;
      }
    }
    return text;
  }
  /* El backend une varias oraciones con espacio: se traduce cada una (la combinacion mas larga que coincida). */
  window.lxBeT = function(text){
    if(typeof text !== 'string' || !text) return text;
    var t = one(text);
    if(t !== text) return t;
    var parts = text.split(/(?<=[.!?])\s+/), out = [], i = 0;
    if(parts.length < 2) return text;
    while(i < parts.length){
      var hit = false;
      for(var j = parts.length; j > i; j--){
        var seg = parts.slice(i, j).join(' '), r = one(seg);
        if(r !== seg || j === i + 1){ out.push(r); i = j; hit = true; break; }
      }
      if(!hit){ out.push(parts[i]); i++; }
    }
    return out.join(' ');
  };
})();
