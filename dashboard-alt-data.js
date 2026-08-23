/* LabX — dashboard-alt-data.js
   Capa de datos independiente para dashboard-alt.html (Vista Beta glassmorphic).

   No depende del JS de dashboard.html ni lo modifica. Consume el MISMO
   endpoint y el MISMO shape de datos que el dashboard clásico
   (/api/athlete/dashboard, /api/athlete/profile), así que ambos dashboards
   quedan sincronizados con el backend sin duplicar lógica de servidor.
*/
(function (global) {
  'use strict';

  function _apiBase() {
    // Sprint 55: dentro del shell nativo de Capacitor, window.location.origin
    // no es la URL real de produccion -- el check de 'file:' de abajo no
    // cubre ese caso (Capacitor no usa protocolo file:).
    if (window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform()) {
      return 'https://labxperformanceapp.com/api';
    }
    return window.location.protocol === 'file:'
      ? 'http://localhost:8000/api'
      : window.location.origin + '/api';
  }

  function _getToken() {
    var tok = localStorage.getItem('lx_co_token');
    if (tok) return tok;
    try {
      var s = JSON.parse(sessionStorage.getItem('kl_s') || localStorage.getItem('kl_s') || 'null');
      if (s && s.token) return s.token;
    } catch (e) {}
    return null;
  }

  /* Devuelve una Promise con el JSON crudo de /athlete/dashboard,
     idéntico al que usa dashboard.html. No toca el DOM. */
  function fetchDashboard(opts) {
    opts = opts || {};
    var tok = _getToken();
    if (!tok) return Promise.reject(new Error('sin sesión'));

    var fresh = opts.fresh ? '?fresh=true' : '';
    return fetch(_apiBase() + '/athlete/dashboard' + fresh, {
      headers: { Authorization: 'Bearer ' + tok },
      cache: 'no-store',
    }).then(function (r) {
      if (!r.ok) throw new Error('dashboard fetch failed: ' + r.status);
      return r.json();
    });
  }

  function fetchProfile() {
    var tok = _getToken();
    if (!tok) return Promise.reject(new Error('sin sesión'));

    return fetch(_apiBase() + '/athlete/profile', {
      headers: { Authorization: 'Bearer ' + tok },
    }).then(function (r) {
      if (!r.ok) throw new Error('profile fetch failed: ' + r.status);
      return r.json();
    });
  }

  global.LabXData = { fetchDashboard: fetchDashboard, fetchProfile: fetchProfile, getToken: _getToken };
})(window);
