/**
 * community.js — modulo unico de Comunidad (CC2).
 *
 * Tres vistas: Feed · Ranking · Clubes. Se monta en un contenedor y no
 * depende de ninguna cascara (web o app): la navegacion externa entra por
 * callbacks.
 *
 *   var c = LXCommunity.mount(el, {
 *     view: 'feed' | 'ranking' | 'clubs',   // vista inicial (default 'feed')
 *     canWrite: true|false,                 // default: plan de kl_s !== 'basic'
 *     userId: '...',                        // opcional (para crear retos)
 *     isCoach: false,                       // opcional (coach/admin crean retos)
 *     apiBase: '/api',
 *     getToken: function(){ return '...' }, // default: localStorage.lx_co_token
 *     rankingScopes: ['social','club','country','global'],
 *     onOpenActivity: function(card){},     // tocar la tarjeta (detalle GPS)
 *     onUpgrade: function(){},              // boton "mejorar plan"
 *     onViewChange: function(view){},
 *     fetch, t, confirm                     // inyectables (tests)
 *   });
 *   c.setView('ranking'); c.reload(); c.destroy();
 *
 * Consume SOLO el contrato actual: /community/* y /athlete/activities/*.
 * Todo texto de usuario pasa por esc().
 */
(function (root) {
  'use strict';

  var VIEWS = ['feed', 'ranking', 'clubs'];
  var SCOPES = ['social', 'club', 'country', 'global'];
  var PERIODS = ['week', 'month', 'year'];
  var SPORTS = ['triathlon', 'running', 'cycling', 'swimming'];
  var METRICS = ['km', 'tss', 'activities', 'hours'];
  var PAGE = 10;

  /* ───────────────────────── utilidades ───────────────────────── */

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // Solo http(s) o ruta absoluta del mismo origen (nada de javascript:, data:, //host).
  function safeUrl(u) {
    u = String(u == null ? '' : u).trim();
    if (/^https?:\/\//i.test(u)) return u;
    if (u.charAt(0) === '/' && u.charAt(1) !== '/') return u;
    return '';
  }

  function num(v, d) {
    var n = Number(v);
    return isFinite(n) ? n : d == null ? 0 : d;
  }

  function fmt(v, dec) {
    return num(v).toFixed(dec == null ? 1 : dec).replace(/\.0$/, '');
  }

  function makeT(opts) {
    return function (key, fallback) {
      if (opts && typeof opts.t === 'function') {
        var o = opts.t(key);
        if (o && o !== key) return o;
      } else if (root.i18n && typeof root.i18n.t === 'function') {
        var v = root.i18n.t(key);
        if (v && v !== key) return v;
      }
      return fallback;
    };
  }

  function normUser(u) {
    u = u || {};
    var name = u.name || u.nombre || '—';
    return {
      id: u.id || u.user_id || null,
      name: name,
      initial: u.avatar_initial || String(name).charAt(0).toUpperCase() || '?',
      avatar_url: u.avatar_url || null,
      flag: u.country_flag || '',
      reason: u.reason || '',
      is_following: !!u.is_following,
      ctl: u.ctl == null ? null : u.ctl,
    };
  }

  function avatarHtml(u) {
    var url = safeUrl(u.avatar_url);
    if (url) return '<span class="lxc-av"><img src="' + esc(url) + '" alt="" loading="lazy"></span>';
    return '<span class="lxc-av">' + esc(u.initial) + '</span>';
  }

  /* ───────────────────────── mini-mapa SVG ───────────────────────── */

  var SPORT_COLOR = { run: '#10B981', swim: '#0EA5E9' };

  function mapColor(sport) {
    sport = String(sport || '').toLowerCase();
    if (sport.indexOf('run') >= 0) return SPORT_COLOR.run;
    if (sport.indexOf('swim') >= 0) return SPORT_COLOR.swim;
    return '#FF6535';
  }

  function miniMap(points, color) {
    var pts = (points || []).filter(function (p) {
      return p && isFinite(Number(p[0])) && isFinite(Number(p[1]));
    });
    if (pts.length < 2) return '';
    var lats = pts.map(function (p) { return Number(p[0]); });
    var lons = pts.map(function (p) { return Number(p[1]); });
    var minLat = Math.min.apply(null, lats), maxLat = Math.max.apply(null, lats);
    var minLon = Math.min.apply(null, lons), maxLon = Math.max.apply(null, lons);
    var W = 90, H = 90, pad = 6;
    var spanLat = maxLat - minLat || 0.0005;
    var spanLon = maxLon - minLon || 0.0005;
    var scale = Math.min((W - pad * 2) / spanLon, (H - pad * 2) / spanLat);
    var offX = (W - spanLon * scale) / 2;
    var offY = (H - spanLat * scale) / 2;
    var d = pts.map(function (p, i) {
      var x = offX + (Number(p[1]) - minLon) * scale;
      var y = H - (offY + (Number(p[0]) - minLat) * scale);
      return (i === 0 ? 'M' : 'L') + x.toFixed(1) + ',' + y.toFixed(1);
    }).join(' ');
    var c = /^#[0-9a-fA-F]{3,8}$/.test(color) ? color : '#FF6535';
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMid meet" aria-hidden="true">' +
      '<path d="' + d + '" fill="none" stroke="' + c + '" stroke-width="6" stroke-opacity=".18" stroke-linecap="round" stroke-linejoin="round"/>' +
      '<path d="' + d + '" fill="none" stroke="' + c + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  }

  /* ───────────────────────── render puro (testeable) ───────────────────────── */

  function photosHtml(photos, c, ctx) {
    var t = ctx.t;
    var items = (photos || []).map(function (p) {
      var url = safeUrl(p.url);
      if (!url) return '';
      var del = p.deletable && ctx.canWrite && p.photo_id
        ? '<button type="button" class="lxc-photo-del" data-act="photo-del" data-activity="' + esc(c.activity_id) +
          '" data-photo="' + esc(p.photo_id) + '" data-post="' + esc(c.id) + '" aria-label="' + esc(t('com_delete', 'Borrar')) + '">✕</button>'
        : '';
      return '<span class="lxc-photo"><img src="' + esc(url) + '" alt="" loading="lazy" data-act="lightbox" data-url="' + esc(url) + '">' + del + '</span>';
    }).join('');
    var add = c.can_add_photos && ctx.canWrite
      ? '<label class="lxc-photo-add">+ ' + esc(t('com_add_photo', 'Foto')) +
        '<input type="file" accept="image/*" multiple hidden data-act="photo-file" data-activity="' + esc(c.activity_id) + '" data-post="' + esc(c.id) + '"></label>'
      : '';
    if (!items && !add) return '';
    return '<div class="lxc-photos" id="lxc-photos-' + esc(c.id) + '">' + items + add + '</div>';
  }

  function commentHtml(cm) {
    return '<div class="lxc-comment"><b>' + esc(cm.author || '—') + '</b> ' + esc(cm.body) + '</div>';
  }

  function commentsBoxHtml(c, ctx, state) {
    var t = ctx.t;
    var list = state.comments[c.id];
    var body = list == null
      ? '<div class="lxc-muted">' + esc(t('com_loading', 'Cargando...')) + '</div>'
      : list.map(commentHtml).join('') || '<div class="lxc-muted">' + esc(t('com_no_comments', 'Aún no hay comentarios.')) + '</div>';
    var form = ctx.canWrite
      ? '<div class="lxc-row"><input class="lxc-input" maxlength="500" placeholder="' + esc(t('com_comment_ph', 'Escribe un comentario')) +
        '" data-draft="cm-' + esc(c.id) + '" value="' + esc(state.drafts['cm-' + c.id] || '') + '">' +
        '<button type="button" class="lxc-btn" data-act="comment-send" data-id="' + esc(c.id) + '">' + esc(t('com_send', 'Enviar')) + '</button></div>'
      : '';
    return '<div class="lxc-comments">' + body + form + '</div>';
  }

  function cardHtml(c, ctx, state) {
    state = state || { comments: {}, openComments: {}, drafts: {} };
    var t = ctx.t;
    var u = normUser(c.user);
    var kudos = num(c.kudo_count);
    var mine = !!c.my_kudo;
    var map = c.route_preview && c.route_preview.length >= 2
      ? '<div class="lxc-map">' + miniMap(c.route_preview, mapColor(c.sport)) + '</div>' : '';
    var stats = [];
    if (num(c.distance_km) > 0) stats.push('<span><b>' + esc(fmt(c.distance_km, 1)) + '</b> km</span>');
    if (num(c.duration_min) > 0) stats.push('<span><b>' + esc(fmt(c.duration_min, 0)) + '</b> min</span>');
    if (c.tss != null) stats.push('<span><b>' + esc(fmt(c.tss, 0)) + '</b> TSS</span>');
    if (c.avg_hr) stats.push('<span><b>' + esc(fmt(c.avg_hr, 0)) + '</b> bpm</span>');
    var kudoBtn = ctx.canWrite
      ? '<button type="button" class="lxc-act' + (mine ? ' on' : '') + '" data-act="kudo" data-id="' + esc(c.id) + '" aria-pressed="' + (mine ? 'true' : 'false') + '">🔥 <span class="lxc-n">' + esc(kudos) + '</span></button>'
      : '<span class="lxc-act ro">🔥 <span class="lxc-n">' + esc(kudos) + '</span></span>';
    var nCm = num(c.n_comments);
    var cmBtn = '<button type="button" class="lxc-act" data-act="comments" data-id="' + esc(c.id) + '">💬 <span class="lxc-n">' + esc(nCm) + '</span></button>';
    return '<article class="lxc-card" data-post="' + esc(c.id) + '">' +
      '<div class="lxc-card-head">' + avatarHtml(u) +
      '<div class="lxc-grow"><div class="lxc-name">' + esc(u.name) + (u.flag ? ' ' + esc(u.flag) : '') + '</div>' +
      '<div class="lxc-muted">' + esc(c.date_iso || '') + '</div></div></div>' +
      '<div class="lxc-card-main" data-act="open-activity" data-id="' + esc(c.id) + '" role="button" tabindex="0">' +
      '<div class="lxc-grow"><div class="lxc-title">' + esc(c.sport_emoji || '') + ' ' + esc(c.name || '') + '</div>' +
      '<div class="lxc-stats">' + stats.join('') + '</div></div>' + map + '</div>' +
      (c.caption ? '<p class="lxc-caption">' + esc(c.caption) + '</p>' : '') +
      photosHtml(c.photos, c, ctx) +
      '<div class="lxc-actions">' + kudoBtn + cmBtn + '</div>' +
      (state.openComments[c.id] ? commentsBoxHtml(c, ctx, state) : '') +
      '</article>';
  }

  function personRowHtml(p, ctx) {
    var u = normUser(p);
    var btn = ctx.canWrite && u.id
      ? '<button type="button" class="lxc-btn' + (u.is_following ? ' ghost' : '') + '" data-act="follow" data-id="' + esc(u.id) + '">' +
        esc(u.is_following ? ctx.t('com_following', 'Siguiendo') : ctx.t('com_follow', 'Seguir')) + '</button>'
      : '';
    return '<div class="lxc-person">' + avatarHtml(u) + '<div class="lxc-grow"><div class="lxc-name">' + esc(u.name) +
      (u.flag ? ' ' + esc(u.flag) : '') + '</div>' + (u.reason ? '<div class="lxc-muted">' + esc(u.reason) + '</div>' : '') +
      '</div>' + btn + '</div>';
  }

  function rankingRowsHtml(rows, ctx) {
    return (rows || []).map(function (r) {
      var u = normUser(r.user);
      return '<div class="lxc-rank' + (r.is_me ? ' me' : '') + '"><span class="lxc-pos">' + esc(r.rank) + '</span>' +
        avatarHtml(u) + '<div class="lxc-grow"><div class="lxc-name">' + esc(u.name) + (u.flag ? ' ' + esc(u.flag) : '') + '</div>' +
        '<div class="lxc-muted">' + esc(fmt(r.hours_week, 1)) + ' h ' + esc(ctx.t('com_this_week', 'esta semana')) + '</div></div>' +
        '<b>' + esc(fmt(r.value, 0)) + '</b> <span class="lxc-muted">TSS</span></div>';
    }).join('');
  }

  function clubCardHtml(g, ctx) {
    var sport = ctx.t('com_sport_' + g.sport, g.sport || '');
    var join = '';
    if (!g.is_member && !g.is_private && ctx.canWrite) {
      join = '<button type="button" class="lxc-btn" data-act="club-join" data-id="' + esc(g.id) + '">' + esc(ctx.t('com_join', 'Unirme')) + '</button>';
    } else if (g.is_member) {
      join = '<span class="lxc-chip">' + esc(ctx.t('com_member', 'Miembro')) + '</span>';
    }
    return '<div class="lxc-club"><div class="lxc-club-main" data-act="club-open" data-id="' + esc(g.id) + '" role="button" tabindex="0">' +
      '<div class="lxc-name">' + (g.is_private ? '🔒 ' : '') + esc(g.name) + '</div>' +
      '<div class="lxc-muted">' + esc(sport) + ' · ' + esc(num(g.n_members)) + ' ' + esc(ctx.t('com_members', 'miembros')) + '</div></div>' + join + '</div>';
  }

  function challengeHtml(ch, ctx, board) {
    var t = ctx.t;
    var pct = Math.max(0, Math.min(100, num(ch.my_pct)));
    var metric = t('com_metric_' + ch.metric, ch.metric || '');
    var boardHtml = '';
    if (board) {
      boardHtml = '<div class="lxc-board">' + board.map(function (b) {
        return '<div class="lxc-rank' + (b.is_me ? ' me' : '') + '"><span class="lxc-pos">' + esc(b.rank) + '</span><div class="lxc-grow">' +
          esc(b.nombre) + '</div><b>' + esc(fmt(b.progress, 1)) + '</b></div>';
      }).join('') + '</div>';
    }
    return '<div class="lxc-chal"><div class="lxc-name">' + esc(ch.name) + (ch.is_active === false ? ' <span class="lxc-chip">' + esc(t('com_ended', 'Finalizado')) + '</span>' : '') + '</div>' +
      (ch.description ? '<div class="lxc-muted">' + esc(ch.description) + '</div>' : '') +
      '<div class="lxc-muted">' + esc(metric) + ' · ' + esc(fmt(ch.target, 1)) + ' · ' + esc(ch.start_date || '') + ' → ' + esc(ch.end_date || '') + '</div>' +
      '<div class="lxc-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + esc(pct) + '"><i style="width:' + pct + '%"></i></div>' +
      '<div class="lxc-muted">' + esc(fmt(ch.my_progress, 1)) + ' / ' + esc(fmt(ch.target, 1)) + ' (' + esc(fmt(pct, 0)) + '%)</div>' +
      '<button type="button" class="lxc-btn ghost" data-act="chal-board" data-id="' + esc(ch.id) + '">' + esc(t('com_see_ranking', 'Ver ranking')) + '</button>' + boardHtml + '</div>';
  }

  /* ───────────────────────── estilos ───────────────────────── */

  var CSS = '.lxc{font-family:inherit;color:var(--text,#e5e7eb);max-width:720px;margin:0 auto}' +
    '.lxc *{box-sizing:border-box}.lxc-muted{color:var(--muted,#9ca3af);font-size:.78rem}' +
    '.lxc-tabs{display:flex;gap:.4rem;margin-bottom:.8rem}.lxc-tab{flex:1;padding:.55rem;border-radius:10px;border:1px solid var(--border,#2a2f3a);background:var(--surface,#161a22);color:inherit;cursor:pointer;font-weight:600}' +
    '.lxc-tab.on{background:var(--accent,#FF6535);border-color:var(--accent,#FF6535);color:#fff}' +
    '.lxc-card,.lxc-club,.lxc-chal,.lxc-note,.lxc-panel{background:var(--surface,#161a22);border:1px solid var(--border,#2a2f3a);border-radius:12px;padding:.8rem;margin-bottom:.7rem}' +
    '.lxc-note{color:var(--muted,#9ca3af);font-size:.82rem}.lxc-msg{color:#f87171;font-size:.82rem;margin:.4rem 0}' +
    '.lxc-card-head,.lxc-person,.lxc-rank,.lxc-row,.lxc-club{display:flex;align-items:center;gap:.6rem}.lxc-club{justify-content:space-between}' +
    '.lxc-grow{flex:1;min-width:0}.lxc-name{font-weight:600;overflow-wrap:anywhere}.lxc-title{font-weight:600;margin-top:.4rem;overflow-wrap:anywhere}' +
    '.lxc-av{width:34px;height:34px;border-radius:50%;background:var(--border,#2a2f3a);display:inline-flex;align-items:center;justify-content:center;overflow:hidden;font-weight:700;flex:none}.lxc-av img{width:100%;height:100%;object-fit:cover}' +
    '.lxc-card-main{display:flex;gap:.6rem;cursor:pointer}.lxc-map{width:90px;height:90px;flex:none}.lxc-map svg{width:100%;height:100%}' +
    '.lxc-stats{display:flex;flex-wrap:wrap;gap:.7rem;font-size:.85rem;margin-top:.3rem}.lxc-caption{margin:.5rem 0;overflow-wrap:anywhere}' +
    '.lxc-photos{display:flex;gap:.4rem;overflow-x:auto;margin:.4rem 0}.lxc-photo{position:relative;flex:none}.lxc-photo img{height:90px;border-radius:8px;display:block;cursor:zoom-in}' +
    '.lxc-photo-del{position:absolute;top:2px;right:2px;border:0;border-radius:50%;width:20px;height:20px;background:#000a;color:#fff;cursor:pointer}' +
    '.lxc-photo-add{flex:none;height:90px;min-width:70px;display:flex;align-items:center;justify-content:center;border:1px dashed var(--border,#2a2f3a);border-radius:8px;cursor:pointer;font-size:.8rem}' +
    '.lxc-actions{display:flex;gap:.5rem;margin-top:.4rem}.lxc-act{border:1px solid var(--border,#2a2f3a);background:transparent;color:inherit;border-radius:999px;padding:.25rem .7rem;cursor:pointer}' +
    '.lxc-act.on{border-color:var(--accent,#FF6535);color:var(--accent,#FF6535)}.lxc-act.ro{cursor:default;opacity:.8}' +
    '.lxc-input,.lxc-select{width:100%;padding:.5rem;border-radius:8px;border:1px solid var(--border,#2a2f3a);background:var(--bg,#0f1218);color:inherit;font:inherit;margin:.25rem 0}' +
    '.lxc-btn{border:0;border-radius:8px;padding:.45rem .9rem;background:var(--accent,#FF6535);color:#fff;font-weight:600;cursor:pointer;white-space:nowrap}.lxc-btn.ghost{background:transparent;border:1px solid var(--border,#2a2f3a);color:inherit}' +
    '.lxc-btn[disabled]{opacity:.5;cursor:default}.lxc-comments{margin-top:.5rem;border-top:1px solid var(--border,#2a2f3a);padding-top:.5rem}.lxc-comment{font-size:.85rem;margin:.25rem 0;overflow-wrap:anywhere}' +
    '.lxc-toolbar{display:flex;gap:.5rem;margin-bottom:.7rem}.lxc-pos{width:1.6rem;text-align:center;font-weight:700}.lxc-rank{padding:.4rem 0;border-bottom:1px solid var(--border,#2a2f3a)}.lxc-rank.me{color:var(--accent,#FF6535)}' +
    '.lxc-filters{display:flex;gap:.5rem;margin-bottom:.7rem}.lxc-chip{font-size:.72rem;border:1px solid var(--border,#2a2f3a);border-radius:999px;padding:.1rem .5rem}' +
    '.lxc-bar{height:8px;border-radius:99px;background:var(--border,#2a2f3a);margin:.4rem 0;overflow:hidden}.lxc-bar i{display:block;height:100%;background:var(--accent,#FF6535)}' +
    '.lxc-h{font-weight:700;margin:.8rem 0 .4rem}.lxc-club-main{cursor:pointer;flex:1;min-width:0}.lxc-people{display:flex;flex-direction:column;gap:.4rem}.lxc-person{padding:.3rem 0}' +
    '.lxc-lb{position:fixed;inset:0;background:#000d;display:flex;align-items:center;justify-content:center;z-index:9999}.lxc-lb img{max-width:92vw;max-height:92vh}';

  function injectCss() {
    if (typeof document === 'undefined' || !document.head || document.getElementById('lxc-css')) return;
    var s = document.createElement('style');
    s.id = 'lxc-css';
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  /* ───────────────────────── montaje ───────────────────────── */

  function defaultCanWrite() {
    try {
      var s = JSON.parse(root.sessionStorage.getItem('kl_s') || root.localStorage.getItem('kl_s') || 'null');
      return !(s && (s.plan === 'basic' || s.plan === 'basico'));
    } catch (e) {
      return true;
    }
  }

  function defaultToken() {
    try {
      return root.localStorage.getItem('lx_co_token') || '';
    } catch (e) {
      return '';
    }
  }

  function mount(container, opts) {
    opts = opts || {};
    var t = makeT(opts);
    var api = opts.apiBase || '/api';
    var doFetch = opts.fetch || function () { return root.fetch.apply(root, arguments); };
    var getToken = opts.getToken || defaultToken;
    var canWrite = opts.canWrite == null ? defaultCanWrite() : !!opts.canWrite;
    var scopes = (opts.rankingScopes || SCOPES).filter(function (s) { return SCOPES.indexOf(s) >= 0; });
    var destroyed = false;

    var S = {
      view: VIEWS.indexOf(opts.view) >= 0 ? opts.view : 'feed',
      msg: '',
      drafts: {},
      comments: {},
      openComments: {},
      lightbox: '',
      feed: { items: [], offset: 0, hasMore: false, loading: false, loaded: false, error: false, followingCount: null },
      share: { open: false, acts: null },
      search: { open: false, results: null, q: '' },
      suggestions: null,
      rank: { scope: scopes[0] || 'social', period: 'week', rows: null, loading: false, error: '', myClubs: null },
      clubs: { mine: null, dir: null, loading: false, error: false, form: false, detail: null, challenges: null, boards: {}, chalForm: false },
    };

    function ctx() { return { t: t, canWrite: canWrite }; }

    /* ── red ── */
    function req(method, path, body, raw) {
      var headers = { Authorization: 'Bearer ' + getToken() };
      var init = { method: method, headers: headers, credentials: 'include' };
      if (body !== undefined && !raw) {
        headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(body);
      } else if (raw) {
        init.body = raw; // FormData: nunca fijar Content-Type a mano
      }
      return Promise.resolve(doFetch(api + path, init)).then(function (r) {
        return Promise.resolve(r.json ? r.json().catch(function () { return null; }) : null).then(function (d) {
          return { ok: !!r.ok, status: r.status, data: d };
        });
      }, function () {
        return { ok: false, status: 0, data: null };
      });
    }

    function errText(r, fallback) {
      if (r && r.status === 403) return t('com_err_plan', 'Tu plan actual solo permite leer la comunidad. Mejora tu plan para participar.');
      if (r && r.status === 0) return t('com_err_net', 'Sin conexión. Inténtalo de nuevo.');
      var d = r && r.data;
      var m = d && ((d.errors && d.errors[0] && d.errors[0].message) || d.message || (typeof d.detail === 'string' && d.detail));
      return (typeof m === 'string' && m) || fallback;
    }

    function flash(text) {
      S.msg = text || '';
      render();
    }

    /* ── render ── */
    function render() {
      if (destroyed) return;
      var tabs = VIEWS.map(function (v) {
        return '<button type="button" class="lxc-tab' + (S.view === v ? ' on' : '') + '" data-act="tab" data-view="' + v + '">' + esc(t('com_tab_' + v, v)) + '</button>';
      }).join('');
      var note = !canWrite
        ? '<div class="lxc-note" data-lxc="readonly">' + esc(t('com_readonly_note', 'Estás en modo lectura: puedes ver la comunidad, pero para publicar, comentar, dar fuego, seguir o unirte a clubes necesitas mejorar tu plan.')) +
          (typeof opts.onUpgrade === 'function' ? ' <button type="button" class="lxc-btn" data-act="upgrade">' + esc(t('com_upgrade', 'Mejorar plan')) + '</button>' : '') + '</div>'
        : '';
      var body = S.view === 'ranking' ? rankingView() : S.view === 'clubs' ? clubsView() : feedView();
      container.innerHTML = '<div class="lxc" data-view="' + S.view + '"><div class="lxc-tabs" role="tablist">' + tabs + '</div>' + note +
        (S.msg ? '<div class="lxc-msg" role="alert">' + esc(S.msg) + '</div>' : '') + body +
        (S.lightbox ? '<div class="lxc-lb" data-act="lightbox-close"><img src="' + esc(S.lightbox) + '" alt=""></div>' : '') + '</div>';
    }

    /* ── FEED ── */
    function feedView() {
      var F = S.feed, c = ctx();
      var tools = '<div class="lxc-toolbar">' +
        (canWrite ? '<button type="button" class="lxc-btn" data-act="share-toggle">' + esc(t('com_share', 'Compartir')) + '</button>' : '') +
        '<button type="button" class="lxc-btn ghost" data-act="search-toggle" aria-label="' + esc(t('com_search', 'Buscar atletas')) + '">🔍</button></div>';
      var share = '';
      if (canWrite && S.share.open) {
        var opts_ = (S.share.acts || []).map(function (a) {
          return '<option value="' + esc(a.id) + '"' + (String(S.drafts['share-act']) === String(a.id) ? ' selected' : '') + '>' + esc((a.date_iso || '') + ' · ' + (a.name || a.sport || '') + ' · ' + fmt(a.dist_km, 1) + ' km') + '</option>';
        }).join('');
        share = '<div class="lxc-panel" data-lxc="share">' +
          '<select class="lxc-select" data-draft="share-act"><option value="">' + esc(t('com_pick_activity', 'Elige una actividad')) + '</option>' + opts_ + '</select>' +
          '<input class="lxc-input" maxlength="280" data-draft="share-caption" placeholder="' + esc(t('com_caption_ph', 'Añade un texto (opcional)')) + '" value="' + esc(S.drafts['share-caption'] || '') + '">' +
          '<select class="lxc-select" data-draft="share-vis">' +
          ['followers', 'public', 'private'].map(function (v) {
            return '<option value="' + v + '"' + ((S.drafts['share-vis'] || 'followers') === v ? ' selected' : '') + '>' + esc(t('com_vis_' + v, v)) + '</option>';
          }).join('') + '</select>' +
          '<button type="button" class="lxc-btn" data-act="share-send">' + esc(t('com_publish', 'Publicar')) + '</button></div>';
      }
      var search = '';
      if (S.search.open) {
        search = '<div class="lxc-panel" data-lxc="search"><div class="lxc-row"><input class="lxc-input" data-draft="search-q" placeholder="' + esc(t('com_search_ph', 'Nombre del atleta (mín. 2 letras)')) +
          '" value="' + esc(S.drafts['search-q'] || '') + '"><button type="button" class="lxc-btn" data-act="search-go">' + esc(t('com_search_btn', 'Buscar')) + '</button></div>' +
          (S.search.results == null ? '' : S.search.results.length
            ? '<div class="lxc-people">' + S.search.results.map(function (p) { return personRowHtml(p, c); }).join('') + '</div>'
            : '<div class="lxc-muted">' + esc(t('com_no_results', 'Sin resultados.')) + '</div>') + '</div>';
      }
      var list = F.items.map(function (it) { return cardHtml(it, c, S); }).join('');
      var empty = F.loaded && !F.items.length
        ? '<div class="lxc-note">' + esc(t('com_feed_empty', 'Tu feed está vacío. Sigue a otros atletas o comparte una actividad.')) + '</div>' : '';
      var more = F.hasMore
        ? '<button type="button" class="lxc-btn ghost" data-act="feed-more"' + (F.loading ? ' disabled' : '') + '>' + esc(t('com_load_more', 'Cargar más')) + '</button>' : '';
      var err = F.error ? '<div class="lxc-msg">' + esc(t('com_err_load', 'No se pudo cargar.')) + ' <button type="button" class="lxc-btn ghost" data-act="feed-retry">' + esc(t('com_retry', 'Reintentar')) + '</button></div>' : '';
      var loading = F.loading && !F.items.length ? '<div class="lxc-muted">' + esc(t('com_loading', 'Cargando...')) + '</div>' : '';
      var sugg = '';
      if (F.loaded && !F.hasMore && S.suggestions && S.suggestions.length) {
        sugg = '<div class="lxc-h">' + esc(t('com_who_to_follow', 'A quién seguir')) + '</div><div class="lxc-people" data-lxc="suggestions">' +
          S.suggestions.slice(0, 4).map(function (p) { return personRowHtml(p, c); }).join('') + '</div>';
      }
      return tools + share + search + loading + err + empty + list + more + sugg;
    }

    function loadFeed(reset) {
      var F = S.feed;
      if (F.loading) return Promise.resolve();
      if (reset) { F.items = []; F.offset = 0; }
      F.loading = true; F.error = false;
      render();
      return req('GET', '/community/activity-feed?limit=' + PAGE + '&offset=' + F.offset).then(function (r) {
        F.loading = false;
        if (!r.ok) { F.error = true; F.loaded = true; render(); return; }
        var d = r.data || {};
        F.items = F.items.concat(d.feed || []);
        F.hasMore = !!d.has_more;
        F.offset = d.next_offset != null ? d.next_offset : F.items.length;
        F.followingCount = d.following_count;
        F.loaded = true;
        render();
        if (!F.hasMore && S.suggestions == null) return loadSuggestions();
      });
    }

    function loadSuggestions() {
      return req('GET', '/community/suggestions').then(function (r) {
        S.suggestions = r.ok && Array.isArray(r.data) ? r.data : [];
        render();
      });
    }

    function findCard(id) {
      for (var i = 0; i < S.feed.items.length; i++) if (String(S.feed.items[i].id) === String(id)) return S.feed.items[i];
      return null;
    }

    function setFollowLocal(id, val) {
      [S.suggestions || [], (S.search.results || [])].forEach(function (arr) {
        arr.forEach(function (p) { if (String(p.id || p.user_id) === String(id)) p.is_following = val; });
      });
    }

    function findPerson(id) {
      var all = (S.suggestions || []).concat(S.search.results || []);
      for (var i = 0; i < all.length; i++) if (String(all[i].id || all[i].user_id) === String(id)) return all[i];
      return null;
    }

    function toggleFollow(id) {
      var p = findPerson(id);
      var was = !!(p && p.is_following);
      return req(was ? 'DELETE' : 'POST', '/community/follow/' + encodeURIComponent(id)).then(function (r) {
        if (!r.ok) return flash(errText(r, t('com_err_action', 'No se pudo completar la acción.')));
        setFollowLocal(id, !was);
        S.msg = '';
        render();
      });
    }

    function toggleKudo(id) {
      var c = findCard(id);
      if (!c) return Promise.resolve();
      var had = !!c.my_kudo;
      return (had ? req('DELETE', '/community/posts/' + encodeURIComponent(id) + '/kudo')
        : req('POST', '/community/posts/' + encodeURIComponent(id) + '/kudo', { kudo_type: 'fire' })).then(function (r) {
        if (!r.ok) return flash(errText(r, t('com_err_action', 'No se pudo completar la acción.')));
        c.my_kudo = had ? null : 'fire';
        c.kudo_count = Math.max(0, num(c.kudo_count) + (had ? -1 : 1));
        S.msg = '';
        render();
      });
    }

    function toggleComments(id) {
      S.openComments[id] = !S.openComments[id];
      if (S.openComments[id] && S.comments[id] == null) {
        render();
        return req('GET', '/community/posts/' + encodeURIComponent(id) + '/comments').then(function (r) {
          S.comments[id] = r.ok && Array.isArray(r.data) ? r.data : [];
          render();
        });
      }
      render();
      return Promise.resolve();
    }

    function sendComment(id) {
      var body = String(S.drafts['cm-' + id] || '').trim();
      if (!body) return Promise.resolve();
      return req('POST', '/community/posts/' + encodeURIComponent(id) + '/comments', { body: body }).then(function (r) {
        if (!r.ok) return flash(errText(r, t('com_err_action', 'No se pudo completar la acción.')));
        (S.comments[id] = S.comments[id] || []).push(r.data);
        var c = findCard(id);
        if (c) c.n_comments = num(c.n_comments) + 1;
        S.drafts['cm-' + id] = '';
        S.msg = '';
        render();
      });
    }

    function toggleShare() {
      S.share.open = !S.share.open;
      render();
      if (S.share.open && S.share.acts == null) {
        return req('GET', '/athlete/activities?per_page=10').then(function (r) {
          S.share.acts = r.ok && r.data ? (r.data.items || []) : [];
          render();
        });
      }
      return Promise.resolve();
    }

    function sendShare() {
      var act = S.drafts['share-act'];
      if (!act) return flash(t('com_err_pick', 'Elige una actividad.'));
      return req('POST', '/community/posts', {
        activity_id: act,
        body: String(S.drafts['share-caption'] || '').slice(0, 280),
        visibility: S.drafts['share-vis'] || 'followers',
      }).then(function (r) {
        if (!r.ok) return flash(errText(r, t('com_err_publish', 'No se pudo publicar. Inténtalo de nuevo.')));
        S.drafts['share-act'] = ''; S.drafts['share-caption'] = '';
        S.share.open = false; S.msg = '';
        return loadFeed(true);
      });
    }

    function doSearch() {
      var q = String(S.drafts['search-q'] || '').trim();
      if (q.length < 2) return flash(t('com_err_search_min', 'Escribe al menos 2 letras.'));
      return req('GET', '/community/search?q=' + encodeURIComponent(q)).then(function (r) {
        if (!r.ok) return flash(errText(r, t('com_err_load', 'No se pudo cargar.')));
        S.search.results = (r.data && r.data.results) || [];
        S.msg = '';
        render();
      });
    }

    function refreshPhotos(postId, activityId) {
      var c = findCard(postId);
      if (!c) return Promise.resolve();
      return req('GET', '/athlete/activities/' + encodeURIComponent(activityId) + '/photos').then(function (r) {
        if (!r.ok) return;
        var manual = ((r.data && r.data.photos) || []).map(function (p) {
          return { url: p.url, photo_id: p.id, deletable: !!p.is_mine };
        });
        var external = (c.photos || []).filter(function (p) { return !p.photo_id; });
        c.photos = manual.concat(external);
        render();
      });
    }

    function uploadPhotos(input) {
      var files = input.files;
      if (!files || !files.length) return Promise.resolve();
      var fd = new root.FormData();
      for (var i = 0; i < files.length; i++) fd.append('files', files[i]);
      var activityId = input.getAttribute('data-activity'), postId = input.getAttribute('data-post');
      return req('POST', '/athlete/activities/' + encodeURIComponent(activityId) + '/photos', undefined, fd).then(function (r) {
        if (!r.ok) return flash(errText(r, t('com_err_photo', 'No se pudo subir la foto.')));
        return refreshPhotos(postId, activityId);
      });
    }

    function deletePhoto(el) {
      var ask = opts.confirm || (root.confirm ? root.confirm.bind(root) : function () { return true; });
      if (!ask(t('com_delete_photo_q', '¿Borrar esta foto?'))) return Promise.resolve();
      var a = el.getAttribute('data-activity'), p = el.getAttribute('data-photo'), post = el.getAttribute('data-post');
      return req('DELETE', '/athlete/activities/' + encodeURIComponent(a) + '/photos/' + encodeURIComponent(p)).then(function (r) {
        if (!r.ok) return flash(errText(r, t('com_err_action', 'No se pudo completar la acción.')));
        return refreshPhotos(post, a);
      });
    }

    /* ── RANKING ── */
    function scopeValue() { return S.rank.scope + (S.rank.scope === 'club' && S.rank.clubId ? ':' + S.rank.clubId : ''); }

    function rankingView() {
      var R = S.rank, c = ctx();
      var scopeOpts = [];
      scopes.forEach(function (s) {
        if (s === 'club') {
          (R.myClubs || []).forEach(function (g) { scopeOpts.push({ v: 'club:' + g.id, label: t('com_scope_club', 'Club') + ': ' + g.name }); });
        } else scopeOpts.push({ v: s, label: t('com_scope_' + s, s) });
      });
      var cur = scopeValue();
      var selScope = '<select class="lxc-select" data-act="rank-scope" aria-label="' + esc(t('com_scope', 'Alcance')) + '">' + scopeOpts.map(function (o) {
        return '<option value="' + esc(o.v) + '"' + (o.v === cur ? ' selected' : '') + '>' + esc(o.label) + '</option>';
      }).join('') + '</select>';
      var selPeriod = '<select class="lxc-select" data-act="rank-period" aria-label="' + esc(t('com_period', 'Periodo')) + '">' + PERIODS.map(function (p) {
        return '<option value="' + p + '"' + (R.period === p ? ' selected' : '') + '>' + esc(t('com_period_' + p, p)) + '</option>';
      }).join('') + '</select>';
      var body = R.loading ? '<div class="lxc-muted">' + esc(t('com_loading', 'Cargando...')) + '</div>'
        : R.error ? '<div class="lxc-msg">' + esc(R.error) + '</div>'
        : R.rows == null ? ''
        : R.rows.length ? '<div class="lxc-panel" data-lxc="ranking">' + rankingRowsHtml(R.rows, c) + '</div>'
        : '<div class="lxc-note">' + esc(t('com_rank_empty', 'Aún no hay datos para este ranking.')) + '</div>';
      return '<div class="lxc-filters">' + selScope + selPeriod + '</div><div class="lxc-muted">' + esc(t('com_rank_metric', 'Ranking por carga de entrenamiento (TSS)')) + '</div>' + body;
    }

    function loadRanking() {
      var R = S.rank;
      R.loading = true; R.error = '';
      render();
      var q = '/community/leaderboard?metric=tss&limit=25&period=' + R.period + '&scope=' + R.scope + (R.scope === 'club' ? '&group_id=' + encodeURIComponent(R.clubId || '') : '');
      return req('GET', q).then(function (r) {
        R.loading = false;
        if (!r.ok) {
          R.rows = null;
          R.error = r.status === 400 ? t('com_err_country', 'Configura tu país en el perfil para ver este ranking.') : errText(r, t('com_err_load', 'No se pudo cargar.'));
        } else R.rows = (r.data && r.data.leaderboard) || [];
        render();
      });
    }

    function openRanking() {
      var R = S.rank;
      var pre = R.myClubs == null && scopes.indexOf('club') >= 0
        ? req('GET', '/community/groups?mine=true&per_page=50').then(function (r) { R.myClubs = r.ok && r.data ? (r.data.items || []) : []; })
        : Promise.resolve();
      return pre.then(function () {
        if (R.scope === 'club' && !R.clubId) { R.scope = scopes.filter(function (s) { return s !== 'club'; })[0] || 'social'; }
        return loadRanking();
      });
    }

    /* ── CLUBES ── */
    function clubsView() {
      var C = S.clubs, c = ctx();
      if (C.detail) return clubDetailView();
      var create = canWrite
        ? '<div class="lxc-toolbar"><button type="button" class="lxc-btn" data-act="club-form">' + esc(t('com_create_club', 'Crear club')) + '</button></div>' : '';
      var form = '';
      if (canWrite && C.form) {
        form = '<div class="lxc-panel" data-lxc="club-form"><input class="lxc-input" maxlength="60" data-draft="club-name" placeholder="' + esc(t('com_club_name', 'Nombre del club')) + '" value="' + esc(S.drafts['club-name'] || '') + '">' +
          '<select class="lxc-select" data-draft="club-sport">' + SPORTS.map(function (s) {
            return '<option value="' + s + '"' + ((S.drafts['club-sport'] || 'triathlon') === s ? ' selected' : '') + '>' + esc(t('com_sport_' + s, s)) + '</option>';
          }).join('') + '</select>' +
          '<label class="lxc-muted"><input type="checkbox" data-draft="club-private"' + (S.drafts['club-private'] ? ' checked' : '') + '> ' + esc(t('com_club_private', 'Club privado')) + '</label> ' +
          '<button type="button" class="lxc-btn" data-act="club-create">' + esc(t('com_create', 'Crear')) + '</button></div>';
      }
      if (C.loading && !C.mine) return create + '<div class="lxc-muted">' + esc(t('com_loading', 'Cargando...')) + '</div>';
      if (C.error) return create + '<div class="lxc-msg">' + esc(t('com_err_load', 'No se pudo cargar.')) + ' <button type="button" class="lxc-btn ghost" data-act="clubs-retry">' + esc(t('com_retry', 'Reintentar')) + '</button></div>';
      var mine = C.mine || [];
      var mineIds = {};
      mine.forEach(function (g) { mineIds[g.id] = true; });
      var dir = (C.dir || []).filter(function (g) { return !mineIds[g.id]; });
      return create + form +
        '<div class="lxc-h">' + esc(t('com_my_clubs', 'Mis clubes')) + '</div>' +
        (mine.length ? mine.map(function (g) { return clubCardHtml(g, c); }).join('') : '<div class="lxc-note">' + esc(t('com_no_clubs', 'Aún no perteneces a ningún club.')) + '</div>') +
        '<div class="lxc-h">' + esc(t('com_directory', 'Directorio')) + '</div>' +
        (dir.length ? dir.map(function (g) { return clubCardHtml(g, c); }).join('') : '<div class="lxc-note">' + esc(t('com_no_dir', 'No hay más clubes públicos.')) + '</div>');
    }

    function canCreateChallenge(g) {
      return canWrite && g.is_member && (!!opts.isCoach || (opts.userId && g.owner_id === opts.userId));
    }

    function clubDetailView() {
      var C = S.clubs, g = C.detail, c = ctx();
      var leave = canWrite && g.is_member && !(opts.userId && g.owner_id === opts.userId)
        ? '<button type="button" class="lxc-btn ghost" data-act="club-leave" data-id="' + esc(g.id) + '">' + esc(t('com_leave', 'Salir del club')) + '</button>' : '';
      var join = !g.is_member && !g.is_private && canWrite
        ? '<button type="button" class="lxc-btn" data-act="club-join" data-id="' + esc(g.id) + '">' + esc(t('com_join', 'Unirme')) + '</button>' : '';
      var chals = C.challenges == null ? '<div class="lxc-muted">' + esc(t('com_loading', 'Cargando...')) + '</div>'
        : C.challenges.length ? C.challenges.map(function (ch) { return challengeHtml(ch, c, C.boards[ch.id]); }).join('')
        : '<div class="lxc-note">' + esc(t('com_no_challenges', 'Este club aún no tiene desafíos.')) + '</div>';
      var cform = '';
      if (canCreateChallenge(g)) {
        cform = '<button type="button" class="lxc-btn ghost" data-act="chal-form">' + esc(t('com_create_challenge', 'Crear desafío')) + '</button>';
        if (C.chalForm) {
          cform += '<div class="lxc-panel" data-lxc="chal-form"><input class="lxc-input" maxlength="80" data-draft="ch-name" placeholder="' + esc(t('com_ch_name', 'Nombre del desafío')) + '" value="' + esc(S.drafts['ch-name'] || '') + '">' +
            '<select class="lxc-select" data-draft="ch-metric">' + METRICS.map(function (m) {
              return '<option value="' + m + '"' + ((S.drafts['ch-metric'] || 'km') === m ? ' selected' : '') + '>' + esc(t('com_metric_' + m, m)) + '</option>';
            }).join('') + '</select>' +
            '<input class="lxc-input" type="number" min="1" data-draft="ch-target" placeholder="' + esc(t('com_ch_target', 'Meta')) + '" value="' + esc(S.drafts['ch-target'] || '') + '">' +
            '<input class="lxc-input" type="date" data-draft="ch-start" value="' + esc(S.drafts['ch-start'] || '') + '" aria-label="' + esc(t('com_ch_start', 'Inicio')) + '">' +
            '<input class="lxc-input" type="date" data-draft="ch-end" value="' + esc(S.drafts['ch-end'] || '') + '" aria-label="' + esc(t('com_ch_end', 'Fin')) + '">' +
            '<button type="button" class="lxc-btn" data-act="chal-create">' + esc(t('com_create', 'Crear')) + '</button></div>';
        }
      }
      return '<button type="button" class="lxc-btn ghost" data-act="club-back">← ' + esc(t('com_back', 'Volver')) + '</button>' +
        '<div class="lxc-panel" data-lxc="club-detail"><div class="lxc-name">' + (g.is_private ? '🔒 ' : '') + esc(g.name) + '</div>' +
        '<div class="lxc-muted">' + esc(t('com_sport_' + g.sport, g.sport || '')) + ' · ' + esc(num(g.n_members)) + ' ' + esc(t('com_members', 'miembros')) + '</div>' +
        (g.description ? '<p>' + esc(g.description) + '</p>' : '') + join + leave + '</div>' +
        '<div class="lxc-h">' + esc(t('com_challenges', 'Desafíos')) + '</div>' + chals + cform;
    }

    function loadClubs() {
      var C = S.clubs;
      C.loading = true; C.error = false;
      render();
      return Promise.all([req('GET', '/community/groups?mine=true&per_page=50'), req('GET', '/community/groups?per_page=50')]).then(function (rs) {
        C.loading = false;
        if (!rs[0].ok || !rs[1].ok) { C.error = true; render(); return; }
        C.mine = (rs[0].data && rs[0].data.items) || [];
        C.dir = (rs[1].data && rs[1].data.items) || [];
        render();
      });
    }

    function joinClub(id) {
      return req('POST', '/community/groups/' + encodeURIComponent(id) + '/join').then(function (r) {
        if (!r.ok) return flash(errText(r, t('com_err_action', 'No se pudo completar la acción.')));
        S.msg = '';
        if (S.clubs.detail && S.clubs.detail.id === id) S.clubs.detail.is_member = true;
        S.rank.myClubs = null;
        return loadClubs();
      });
    }

    function leaveClub(id) {
      return req('DELETE', '/community/groups/' + encodeURIComponent(id) + '/leave').then(function (r) {
        if (!r.ok) return flash(errText(r, t('com_err_action', 'No se pudo completar la acción.')));
        S.clubs.detail = null; S.msg = ''; S.rank.myClubs = null;
        return loadClubs();
      });
    }

    function openClub(id) {
      var all = (S.clubs.mine || []).concat(S.clubs.dir || []);
      var g = null;
      all.forEach(function (x) { if (x.id === id) g = x; });
      if (!g) return Promise.resolve();
      S.clubs.detail = g; S.clubs.challenges = null; S.clubs.boards = {}; S.clubs.chalForm = false;
      render();
      return req('GET', '/community/groups/' + encodeURIComponent(id) + '/challenges').then(function (r) {
        S.clubs.challenges = r.ok && Array.isArray(r.data) ? r.data : [];
        render();
      });
    }

    function createClub() {
      var name = String(S.drafts['club-name'] || '').trim();
      if (name.length < 3) return flash(t('com_err_club_name', 'El nombre debe tener al menos 3 caracteres.'));
      return req('POST', '/community/groups', {
        name: name,
        sport: S.drafts['club-sport'] || 'triathlon',
        is_private: !!S.drafts['club-private'],
      }).then(function (r) {
        if (!r.ok) return flash(errText(r, t('com_err_action', 'No se pudo completar la acción.')));
        S.drafts['club-name'] = ''; S.drafts['club-private'] = false;
        S.clubs.form = false; S.msg = ''; S.rank.myClubs = null;
        return loadClubs();
      });
    }

    function createChallenge() {
      var g = S.clubs.detail, D = S.drafts;
      var target = Number(D['ch-target']);
      if (!String(D['ch-name'] || '').trim() || !(target > 0) || !D['ch-start'] || !D['ch-end']) {
        return flash(t('com_err_challenge', 'Completa nombre, meta y fechas.'));
      }
      return req('POST', '/community/groups/' + encodeURIComponent(g.id) + '/challenges', {
        name: String(D['ch-name']).trim(), metric: D['ch-metric'] || 'km', sport: 'all',
        target: target, start_date: D['ch-start'], end_date: D['ch-end'],
      }).then(function (r) {
        if (!r.ok) return flash(errText(r, t('com_err_action', 'No se pudo completar la acción.')));
        S.clubs.chalForm = false; S.msg = '';
        ['ch-name', 'ch-target', 'ch-start', 'ch-end'].forEach(function (k) { D[k] = ''; });
        return openClub(g.id);
      });
    }

    function loadBoard(id) {
      return req('GET', '/community/challenges/' + encodeURIComponent(id) + '/leaderboard').then(function (r) {
        if (!r.ok) return flash(errText(r, t('com_err_load', 'No se pudo cargar.')));
        S.clubs.boards[id] = (r.data && r.data.board) || [];
        render();
      });
    }

    /* ── navegacion ── */
    function enter(view) {
      S.view = view; S.msg = '';
      render();
      if (view === 'feed' && !S.feed.loaded) return loadFeed(true);
      if (view === 'ranking' && S.rank.rows == null) return openRanking();
      if (view === 'clubs' && !S.clubs.mine) return loadClubs();
      return Promise.resolve();
    }

    function setView(view) {
      if (VIEWS.indexOf(view) < 0) return Promise.resolve();
      if (typeof opts.onViewChange === 'function') opts.onViewChange(view);
      return enter(view);
    }

    /* ── eventos (delegados) ── */
    function closest(el, sel) {
      return el && el.closest ? el.closest(sel) : null;
    }

    function onClick(e) {
      var inFileLabel = closest(e.target, '.lxc-photo-add');
      var el = closest(e.target, '[data-act]');
      if (!el) return;
      var act = el.getAttribute('data-act');
      var id = el.getAttribute('data-id');
      // Los controles internos de la tarjeta no abren el detalle.
      if (act === 'photo-file' || inFileLabel) return;
      switch (act) {
        case 'tab': return setView(el.getAttribute('data-view'));
        case 'upgrade': if (typeof opts.onUpgrade === 'function') opts.onUpgrade(); return;
        case 'feed-more': return loadFeed(false);
        case 'feed-retry': return loadFeed(S.feed.items.length === 0);
        case 'kudo': return canWrite ? toggleKudo(id) : undefined;
        case 'comments': return toggleComments(id);
        case 'comment-send': return canWrite ? sendComment(id) : undefined;
        case 'open-activity': {
          var c = findCard(id);
          if (c && typeof opts.onOpenActivity === 'function') opts.onOpenActivity(c);
          return;
        }
        case 'share-toggle': return canWrite ? toggleShare() : undefined;
        case 'share-send': return canWrite ? sendShare() : undefined;
        case 'search-toggle': S.search.open = !S.search.open; render(); return;
        case 'search-go': return doSearch();
        case 'follow': return canWrite ? toggleFollow(id) : undefined;
        case 'lightbox': S.lightbox = safeUrl(el.getAttribute('data-url')); render(); return;
        case 'lightbox-close': S.lightbox = ''; render(); return;
        case 'photo-del': return canWrite ? deletePhoto(el) : undefined;
        case 'club-join': return canWrite ? joinClub(id) : undefined;
        case 'club-leave': return canWrite ? leaveClub(id) : undefined;
        case 'club-open': return openClub(id);
        case 'club-back': S.clubs.detail = null; render(); return;
        case 'club-form': S.clubs.form = !S.clubs.form; render(); return;
        case 'club-create': return canWrite ? createClub() : undefined;
        case 'clubs-retry': return loadClubs();
        case 'chal-form': S.clubs.chalForm = !S.clubs.chalForm; render(); return;
        case 'chal-create': return canWrite ? createChallenge() : undefined;
        case 'chal-board': return loadBoard(id);
      }
    }

    function onInput(e) {
      var el = e.target;
      var key = el && el.getAttribute && el.getAttribute('data-draft');
      if (key) S.drafts[key] = el.type === 'checkbox' ? !!el.checked : el.value;
    }

    function onChange(e) {
      var el = e.target;
      if (!el || !el.getAttribute) return;
      onInput(e);
      var act = el.getAttribute('data-act');
      if (act === 'photo-file' && canWrite) uploadPhotos(el);
      else if (act === 'rank-scope') {
        var v = String(el.value).split(':');
        S.rank.scope = v[0]; S.rank.clubId = v[1] || null;
        loadRanking();
      } else if (act === 'rank-period') {
        S.rank.period = el.value;
        loadRanking();
      }
    }

    function onKey(e) {
      if (e.key !== 'Enter') return;
      var el = e.target, key = el && el.getAttribute && el.getAttribute('data-draft');
      if (key === 'search-q') { onInput(e); doSearch(); }
      else if (key && key.indexOf('cm-') === 0 && canWrite) { onInput(e); sendComment(key.slice(3)); }
      else {
        var a = el && el.getAttribute && el.getAttribute('data-act');
        if (a === 'open-activity' || a === 'club-open') onClick(e);
      }
    }

    function onEsc(e) {
      if (e.key === 'Escape' && S.lightbox) { S.lightbox = ''; render(); }
    }

    injectCss();
    container.addEventListener('click', onClick);
    container.addEventListener('input', onInput);
    container.addEventListener('change', onChange);
    container.addEventListener('keydown', onKey);
    if (root.document && root.document.addEventListener) root.document.addEventListener('keydown', onEsc);

    var started = enter(S.view);

    return {
      setView: setView,
      reload: function () {
        S.feed.loaded = false; S.suggestions = null; S.rank.rows = null; S.clubs.mine = null;
        return enter(S.view);
      },
      destroy: function () {
        destroyed = true;
        container.removeEventListener && container.removeEventListener('click', onClick);
        container.removeEventListener && container.removeEventListener('input', onInput);
        container.removeEventListener && container.removeEventListener('change', onChange);
        container.removeEventListener && container.removeEventListener('keydown', onKey);
        if (root.document && root.document.removeEventListener) root.document.removeEventListener('keydown', onEsc);
        container.innerHTML = '';
      },
      ready: started,
      state: S,
      _onClick: onClick,
      _onChange: onChange,
    };
  }

  var api = {
    mount: mount,
    esc: esc,
    safeUrl: safeUrl,
    miniMap: miniMap,
    cardHtml: cardHtml,
    personRowHtml: personRowHtml,
    rankingRowsHtml: rankingRowsHtml,
    clubCardHtml: clubCardHtml,
    challengeHtml: challengeHtml,
    VIEWS: VIEWS,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.LXCommunity = api;
})(typeof window !== 'undefined' ? window : globalThis);
