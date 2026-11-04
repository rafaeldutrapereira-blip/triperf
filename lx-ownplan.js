/* CQ7 -- Mi Plan propio vive en el servidor (GET/POST/PUT/DELETE /api/athlete/own-plan).
 * localStorage queda solo como cache de lectura (kl_own_plan_cache): nunca es la fuente.
 *
 *   LXOwnPlan.cached()      -> sesiones propias (sincrono, desde el cache)
 *   LXOwnPlan.load()        -> migra una vez desde kl_training_plan, pide al servidor y refresca el cache
 *   LXOwnPlan.sync(next)    -> aplica el diff (crear/editar/borrar) contra el servidor
 *   LXOwnPlan.add(session)  -> POST de una sesion (usado por Indoor "+ Mi Plan")
 *
 * CQ13: la marca de migrado es por usuario (kl_own_plan_migrated:<user_id>) y el
 * plan local solo se importa si kl_training_plan_owner coincide con la cuenta
 * actual; si es otra cuenta o no hay atribucion, queda intacto sin subirse.
 *
 * Migracion suave: las sesiones propias que hubiera en localStorage.kl_training_plan
 * (las del coach llevan api_assignment_id y NO se migran) se suben UNA vez con
 * legacy_id (el servidor no duplica) y se retiran del almacenamiento local.
 */
(function (root, factory) {
  var api = { create: factory };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else {
    root.LXOwnPlanFactory = api;
    root.LXOwnPlan = factory({});
  }
})(typeof window !== 'undefined' ? window : this, function (env) {
  'use strict';
  var CACHE_KEY = 'kl_own_plan_cache';
  var MIGRATED_KEY = 'kl_own_plan_migrated'; // CQ13: se le agrega ':<user_id>'
  var OWNER_KEY = 'kl_training_plan_owner'; // CQ13: user_id que dejo el plan local
  var LEGACY_KEY = 'kl_training_plan';

  function store() {
    return env.storage || (typeof localStorage !== 'undefined' ? localStorage : null);
  }
  function rd(k, dflt) {
    try {
      var s = store();
      var v = s && s.getItem(k);
      return v ? JSON.parse(v) : dflt;
    } catch (e) {
      return dflt;
    }
  }
  function wr(k, v) {
    try {
      store().setItem(k, JSON.stringify(v));
    } catch (e) {}
  }
  function token() {
    if (env.token) return env.token();
    var s = store();
    var t = (s && (s.getItem('lx_ath_token') || s.getItem('lx_co_token'))) || '';
    if (!t) {
      try {
        var ks = JSON.parse(
          (typeof sessionStorage !== 'undefined' && sessionStorage.getItem('kl_s')) ||
            (s && s.getItem('kl_s')) || 'null');
        t = ks && ks.token ? ks.token : '';
      } catch (e) {}
    }
    return t;
  }
  function base() {
    if (env.api) return env.api;
    if (typeof location === 'undefined') return '/api';
    return location.protocol === 'file:' ? 'http://localhost:8000/api' : location.origin + '/api';
  }
  function req(method, path, body) {
    var f = env.fetch || (typeof fetch !== 'undefined' ? fetch.bind(null) : null);
    var tk = token();
    if (!f || !tk) return Promise.reject(new Error('no-token'));
    var opts = { method: method, headers: { Authorization: 'Bearer ' + tk } };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    return f(base() + '/athlete/own-plan' + path, opts).then(function (r) {
      if (!r.ok) {
        var e = new Error('http-' + r.status);
        e.status = r.status;
        throw e;
      }
      return r.json();
    });
  }

  var list = rd(CACHE_KEY, []);
  if (!Array.isArray(list)) list = [];
  var idMap = {}; // id temporal (creado offline-first) -> id del servidor
  var queue = Promise.resolve();
  var loading = null;
  var api = { onError: null };

  function setList(a) {
    list = a;
    wr(CACHE_KEY, list);
  }
  function resolveId(id) {
    return idMap[id] || id;
  }
  /* CQ13: id del usuario autenticado (sesion kl_s.user_id) o '' si no hay. */
  function userId() {
    try {
      if (env.userId) return String(env.userId() || '');
      var s = store();
      var raw =
        (typeof sessionStorage !== 'undefined' && sessionStorage.getItem('kl_s')) ||
        (s && s.getItem('kl_s')) || 'null';
      var ks = JSON.parse(raw);
      return ks && ks.user_id != null ? String(ks.user_id) : '';
    } catch (e) {
      return '';
    }
  }
  function migratedKey(uid) {
    return MIGRATED_KEY + ':' + uid;
  }
  function isMigrated() {
    var uid = userId();
    var s = store();
    return !!(uid && s && s.getItem(migratedKey(uid)));
  }
  function note(msg) {
    try {
      if (typeof console !== 'undefined' && console.info) console.info('[LXOwnPlan] ' + msg);
    } catch (e) {}
  }
  /* El plan local es de esta cuenta solo si quedo marcado con su user_id. */
  function localIsMine() {
    var uid = userId();
    var s = store();
    return !!(uid && s && s.getItem(OWNER_KEY) === uid);
  }
  /* Sesiones propias que aun viven en kl_training_plan (sin api_assignment_id). */
  function legacyLocal() {
    var arr = rd(LEGACY_KEY, []);
    return (Array.isArray(arr) ? arr : []).filter(function (s) {
      return s && s.id && !s.api_assignment_id && s.source !== 'api' && s.date_iso;
    });
  }
  function stripLegacy(uid) {
    var arr = rd(LEGACY_KEY, []);
    wr(LEGACY_KEY, (Array.isArray(arr) ? arr : []).filter(function (s) {
      return s && (s.api_assignment_id || s.source === 'api');
    }));
    var s = store();
    if (s) {
      s.setItem(migratedKey(uid), '1');
      if (s.removeItem) s.removeItem(OWNER_KEY);
      else s.setItem(OWNER_KEY, '');
    }
  }
  function fail(err) {
    if (err && (err.status === 401 || err.status === 403)) setList([]);
    if (typeof api.onError === 'function') api.onError(err);
    return false;
  }

  api.cached = function () {
    var out = list.slice();
    if (!isMigrated() && localIsMine()) {
      // antes de migrar se siguen viendo las locales (sin duplicar las ya subidas)
      var known = {};
      out.forEach(function (s) { if (s.legacy_id) known[s.legacy_id] = true; known[s.id] = true; });
      legacyLocal().forEach(function (s) { if (!known[s.id]) out.push(s); });
    }
    return out;
  };

  /* Marca el plan local como de la cuenta actual (lo llama quien guarda
     sesiones propias en localStorage). Sin sesion no marca nada. */
  api.stampOwner = function () {
    var uid = userId();
    var s = store();
    if (uid && s && !s.getItem(OWNER_KEY)) s.setItem(OWNER_KEY, uid);
  };

  api.migrated = isMigrated;

  api.migrate = function () {
    var uid = userId();
    if (!uid) return Promise.resolve(null); // sin sesion: no se importa ni se marca
    var s = store();
    if (isMigrated()) return Promise.resolve(null);
    var local = legacyLocal();
    if (!local.length) {
      if (s) s.setItem(migratedKey(uid), '1');
      return Promise.resolve(null);
    }
    if (!localIsMine()) {
      // otro usuario (o nadie atribuible) dejo este plan: queda intacto, sin subir
      note('plan local no atribuible a esta cuenta; no se importa');
      return Promise.resolve(null);
    }
    return req('POST', '/import', { sessions: local }).then(function (res) {
      stripLegacy(uid);
      return res;
    });
  };

  api.load = function () {
    if (loading) return loading;
    loading = api.migrate()
      .then(function (res) {
        return res && res.sessions ? res.sessions : req('GET', '').then(function (r) { return r.sessions; });
      })
      .then(function (sessions) {
        setList(sessions || []);
        return api.cached();
      })
      .catch(function (e) {
        fail(e);
        return api.cached();
      })
      .then(function (v) {
        loading = null;
        return v;
      });
    return loading;
  };

  function enqueue(fn) {
    var p = queue.then(fn);
    queue = p.catch(function () {});
    return p;
  }

  function bodyOf(s) {
    var b = {};
    Object.keys(s).forEach(function (k) {
      if (k !== 'id' && k !== 'created_at' && k !== 'updated_at') b[k] = s[k];
    });
    return b;
  }
  function same(a, b) {
    return JSON.stringify(a) === JSON.stringify(b);
  }

  /* next = lista COMPLETA de sesiones propias deseada. Se actualiza el cache al
     instante y se envia el diff al servidor en orden. Resuelve true/false. */
  api.sync = function (next) {
    next = (next || []).filter(function (s) { return s && !s.api_assignment_id; });
    var prev = list.slice();
    var prevById = {};
    prev.forEach(function (s) { prevById[s.id] = s; });
    var nextById = {};
    next.forEach(function (s) { nextById[s.id] = s; });
    var ops = [];
    next.forEach(function (s) {
      var p = prevById[s.id];
      if (!p) ops.push({ t: 'create', s: s });
      else if (!same(bodyOf(p), bodyOf(s))) ops.push({ t: 'update', s: s });
    });
    prev.forEach(function (s) {
      if (!nextById[s.id]) ops.push({ t: 'delete', s: s });
    });
    setList(next.map(function (s) { return Object.assign({}, s); }));
    if (!ops.length) return Promise.resolve(true);
    return enqueue(function () {
      return ops.reduce(function (chain, op) {
        return chain.then(function () {
          var id = resolveId(op.s.id);
          if (op.t === 'create') {
            var b = bodyOf(op.s);
            if (/^plan-/.test(op.s.id) && !b.legacy_id) b.legacy_id = op.s.id;
            return req('POST', '', b).then(function (saved) {
              idMap[op.s.id] = saved.id;
              setList(list.map(function (x) { return x.id === op.s.id ? saved : x; }));
            });
          }
          if (op.t === 'update') return req('PUT', '/' + encodeURIComponent(id), bodyOf(op.s));
          return req('DELETE', '/' + encodeURIComponent(id));
        });
      }, Promise.resolve());
    }).then(
      function () { return true; },
      function (e) {
        fail(e);
        return api.load().then(function () { return false; });
      }
    );
  };

  /* Alta de una sesion (Indoor "+ Mi Plan"). Resuelve la sesion guardada
     (duplicate:true si ya estaba ese workout ese dia) o rechaza si falla. */
  api.add = function (session) {
    return enqueue(function () {
      return req('POST', '', session).then(function (saved) {
        var rest = list.filter(function (x) { return x.id !== saved.id; });
        rest.push(saved);
        setList(rest);
        return saved;
      });
    });
  };

  api._state = function () { return { list: list.slice(), idMap: idMap }; };
  return api;
});
