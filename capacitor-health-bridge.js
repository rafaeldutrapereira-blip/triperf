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

  const READ_TYPES = ['steps', 'distance', 'calories', 'heartRate', 'workouts'];

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

  global.LabXHealthBridge = {
    isNative,
    isAvailable,
    requestAuthorization,
    queryRecentWorkouts,
    normalizeHealthWorkout, // exportado para tests
  };
})(window);
