/**
 * Sprint 55 (multi-marca / app nativa) — puente a HealthKit (iOS) / Health
 * Connect (Android) vía @capgo/capacitor-health, sin bundler: Capacitor
 * expone el plugin automaticamente en runtime como
 * `window.Capacitor.Plugins.Health` dentro del shell nativo (no hace falta
 * importar el paquete npm en www/ — eso solo se usa para tipos TS y el
 * codigo nativo Swift/Kotlin del plugin).
 *
 * Ver docs/plan-multi-brand-wearables.md (Sprint 55). Igual criterio que
 * los providers de Wahoo/Polar: normaliza al mismo formato interno de
 * Activity (sport/date_iso/dur_min/dist_km/avg_hr/calories/tss).
 *
 * IMPORTANTE — sin verificar en dispositivo real todavia: este archivo se
 * escribio contra la API documentada del plugin (definitions.d.ts), pero
 * nunca se corrio dentro de un APK real (no hay Android SDK/emulador en
 * esta maquina). No activar en produccion hasta probarlo en un dispositivo
 * Android real con Health Connect instalado.
 */
(function (global) {
  'use strict';

  function isNative() {
    return !!(global.Capacitor && global.Capacitor.isNativePlatform && global.Capacitor.isNativePlatform());
  }

  function healthPlugin() {
    return global.Capacitor && global.Capacitor.Plugins && global.Capacitor.Plugins.Health;
  }

  async function isAvailable() {
    const plugin = healthPlugin();
    if (!isNative() || !plugin) return { available: false, reason: 'no-native-shell' };
    return plugin.isAvailable();
  }

  const READ_TYPES = ['steps', 'distance', 'calories', 'heartRate', 'workouts', 'sleep'];

  async function requestAuthorization() {
    const plugin = healthPlugin();
    if (!plugin) throw new Error('Health plugin no disponible (no se esta corriendo dentro del shell nativo)');
    return plugin.requestAuthorization({ read: READ_TYPES, requestHistoryAccess: true });
  }

  // Mismo mapeo de categorias (swim/bike/run/gym/other) que usan los demas
  // providers (Garmin/Wahoo/Polar) — WorkoutType de HealthKit/Health Connect
  // trae MUCHOS mas valores especificos que los otros proveedores; se
  // agrupan por substring igual que se hizo con el `sport` libre de Polar.
  const _SPORT_KEYWORDS = [
    ['swim', 'swim'],
    ['running', 'run'],
    ['walk', 'run'],
    ['cycl', 'bike'],
    ['biking', 'bike'],
    ['strength', 'gym'],
    ['weightlifting', 'gym'],
    ['yoga', 'gym'],
    ['pilates', 'gym'],
    ['crossTraining', 'gym'],
    ['functionalStrengthTraining', 'gym'],
  ];

  function normSport(workoutType) {
    if (!workoutType) return 'other';
    const low = String(workoutType).toLowerCase();
    for (const [kw, sport] of _SPORT_KEYWORDS) {
      if (low.includes(kw.toLowerCase())) return sport;
    }
    return 'other';
  }

  /** Convierte un Workout (HealthPlugin.queryWorkouts) al formato interno
   * de Activity. Sin potencia; TSS solo por %FCmax si se conoce el avg_hr
   * de la sesion, que este plugin NO expone directamente en el objeto
   * Workout (habria que cruzar heartRate samples del mismo rango de
   * tiempo via readSamples — no implementado en esta primera pasada). */
  function normalizeHealthWorkout(w) {
    const sport = normSport(w.workoutType);
    const dateIso = (w.startDate || '').slice(0, 10);
    const durMin = w.duration ? Math.round(w.duration / 60) : 0;
    const distKm = w.totalDistance ? Math.round((w.totalDistance / 1000) * 100) / 100 : 0;
    const calories = w.totalEnergyBurned ? Math.round(w.totalEnergyBurned) : null;

    return {
      activity_id: 'health_' + (w.platformId || w.sourceId || w.startDate),
      name: w.sourceName || sport,
      sport: sport,
      date_iso: dateIso,
      dur_min: durMin,
      dist_km: distKm,
      avg_hr: null,
      avg_power: null,
      calories: calories,
      elev_m: null,
      tss: 0.0, // sin HR/potencia por sesion en esta primera pasada -- ver nota arriba
    };
  }

  async function queryRecentWorkouts(days) {
    const plugin = healthPlugin();
    if (!plugin) throw new Error('Health plugin no disponible');
    const end = new Date();
    const start = new Date(end.getTime() - (days || 7) * 86400000);
    const result = await plugin.queryWorkouts({
      startDate: start.toISOString(),
      endDate: end.toISOString(),
      limit: 100,
    });
    return (result.workouts || []).map(normalizeHealthWorkout);
  }

  // ── Siestas (HealthKit/Health Connect) ──────────────────────────────
  // A diferencia de Garmin (que trae dailySleepDTO.napTimeSeconds ya
  // separado y verificado con datos reales, ver
  // docs/plan-multi-brand-wearables.md), HealthKit/Health Connect no
  // tienen una categoria "nap" explicita -- el sueno se expone como una
  // serie de samples individuales con su propio horario. Una siesta es
  // simplemente OTRA sesion de sueno mas corta, en horario distinto al de
  // la noche. Hay que: 1) agrupar samples cercanos en "episodios" de
  // sueno, 2) clasificar cada episodio como nocturno o siesta.
  //
  // Criterio de clasificacion (simplificacion del que usa el propio
  // Garmin: "menos de 3 horas y fuera de tu ventana habitual de sueno" --
  // Garmin aprende esa ventana con anos de datos del dispositivo; acá se
  // aproxima con una regla fija de horario diurno, documentada como
  // simplificacion, no como equivalente exacto):
  //   - duracion dormida < 180 min, Y
  //   - el episodio empieza entre las 08:00 y las 21:00 hora local
  // Todo lo demas se trata como sueno nocturno principal.
  const _NAP_MAX_MIN = 180;
  const _NAP_WINDOW_START_HOUR = 8;
  const _NAP_WINDOW_END_HOUR = 21;
  const _EPISODE_GAP_MIN = 30; // samples con menos de esto entre si son el mismo episodio

  const _ASLEEP_STATES = new Set(['asleep', 'rem', 'deep', 'light']);

  /** Agrupa samples de sueno (ya ordenados o no) en episodios contiguos. */
  function _groupSleepEpisodes(samples) {
    const sorted = (samples || [])
      .filter((s) => s.startDate && s.endDate)
      .slice()
      .sort((a, b) => new Date(a.startDate) - new Date(b.startDate));

    const episodes = [];
    let current = null;

    for (const s of sorted) {
      const start = new Date(s.startDate);
      const end = new Date(s.endDate);
      if (current && (start - current.end) / 60000 <= _EPISODE_GAP_MIN) {
        current.samples.push(s);
        if (end > current.end) current.end = end;
      } else {
        current = { start, end, samples: [s] };
        episodes.push(current);
      }
    }
    return episodes;
  }

  /** Minutos realmente dormidos dentro de un episodio (excluye 'awake'/'inBed'). */
  function _asleepMinutes(episode) {
    let min = 0;
    for (const s of episode.samples) {
      if (_ASLEEP_STATES.has(s.sleepState)) {
        min += (new Date(s.endDate) - new Date(s.startDate)) / 60000;
      }
    }
    return Math.round(min);
  }

  /** Clasifica episodios de sueno en {mainSleepMin, napMin} para un dia,
   * mismo shape que Garmin (total_min vs nap_min separados, nunca sumados
   * entre si en el sleep_score). */
  function classifySleepEpisodes(samples) {
    const episodes = _groupSleepEpisodes(samples);
    let mainSleepMin = 0;
    let napMin = 0;

    for (const ep of episodes) {
      const asleepMin = _asleepMinutes(ep);
      if (asleepMin === 0) continue;
      const startHour = ep.start.getHours();
      const isNap = asleepMin < _NAP_MAX_MIN &&
        startHour >= _NAP_WINDOW_START_HOUR && startHour < _NAP_WINDOW_END_HOUR;
      if (isNap) {
        napMin += asleepMin;
      } else if (asleepMin > mainSleepMin) {
        // Si hay mas de un episodio "nocturno" en el rango (raro), se
        // toma el mas largo como sueno principal del dia.
        mainSleepMin = asleepMin;
      }
    }
    return { mainSleepMin: mainSleepMin || null, napMin: napMin || null };
  }

  async function querySleepToday() {
    const plugin = healthPlugin();
    if (!plugin) throw new Error('Health plugin no disponible');
    const end = new Date();
    const start = new Date(end.getTime() - 36 * 3600000); // 36h atras cubre siesta de ayer + noche
    const result = await plugin.readSamples({
      dataType: 'sleep',
      startDate: start.toISOString(),
      endDate: end.toISOString(),
      limit: 200,
      ascending: true,
    });
    return classifySleepEpisodes(result.samples || []);
  }

  global.LabXHealthBridge = {
    isNative,
    isAvailable,
    requestAuthorization,
    queryRecentWorkouts,
    querySleepToday,
    classifySleepEpisodes, // exportado para tests
    normalizeHealthWorkout, // exportado para tests
  };
})(window);
