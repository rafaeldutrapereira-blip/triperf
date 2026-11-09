/* CUENTA-BORRADO (BUILD 367): modal "Eliminar mi cuenta" compartido por la web
 * (athlete_profile.html) y la app (athlete-app.html, Perfil).
 * Muestra que se borra y que se conserva anonimizado, pide la contrasena actual y
 * llama a POST /api/account/deletion-request. Textos ES/PT/EN en este archivo. */
(function (root) {
  'use strict';

  var TX = {
    es: {
      title: 'Eliminar mi cuenta',
      lead: 'Esta acción desactiva tu cuenta ahora mismo y elimina tus datos. No se puede deshacer.',
      del_h: 'Se elimina',
      del: 'Tu perfil y métricas, actividades, sueño y bienestar, laboratorios, nutrición, equipamiento, carreras, planes y entrenamientos, mensajes, actividad en Comunidad y tus fotos y archivos. Se revocan al instante tus conexiones con Garmin, Strava, intervals.icu, Polar y Wahoo.',
      keep_h: 'Se conserva, solo de forma anónima',
      keep: 'Los registros de suscripciones y pagos, por el plazo que exige la ley tributaria, sin tu nombre, correo ni identificadores. Y un registro de auditoría de esta eliminación, sin datos personales.',
      when_h: 'Plazos',
      when: 'Tu cuenta queda desactivada de inmediato (no podrás iniciar sesión y se cortan los cobros). Tus datos se eliminan en un plazo máximo de 30 días; normalmente a los 7 días.',
      pw: 'Confirma con tu contraseña actual',
      cancel: 'Cancelar',
      go: 'Eliminar mi cuenta',
      busy: 'Eliminando…',
      empty: 'Escribe tu contraseña para continuar.',
      bad: 'Contraseña incorrecta.',
      fail: 'No se pudo completar. Inténtalo de nuevo.',
      done_h: 'Tu cuenta quedó desactivada',
      done: 'Tus datos se eliminarán a más tardar el {date}. Si cambias de opinión, escríbenos a partnerships@labxperformanceapp.com antes de esa fecha.',
      ok: 'Entendido'
    },
    pt: {
      title: 'Excluir minha conta',
      lead: 'Esta ação desativa sua conta agora mesmo e exclui seus dados. Não pode ser desfeita.',
      del_h: 'É excluído',
      del: 'Seu perfil e métricas, atividades, sono e bem-estar, exames, nutrição, equipamentos, provas, planos e treinos, mensagens, atividade na Comunidade e suas fotos e arquivos. Suas conexões com Garmin, Strava, intervals.icu, Polar e Wahoo são revogadas na hora.',
      keep_h: 'É mantido, apenas de forma anônima',
      keep: 'Os registros de assinaturas e pagamentos, pelo prazo exigido pela lei tributária, sem nome, e-mail nem identificadores. E um registro de auditoria desta exclusão, sem dados pessoais.',
      when_h: 'Prazos',
      when: 'Sua conta é desativada imediatamente (não será possível entrar e as cobranças são encerradas). Seus dados são excluídos em no máximo 30 dias; normalmente em 7 dias.',
      pw: 'Confirme com sua senha atual',
      cancel: 'Cancelar',
      go: 'Excluir minha conta',
      busy: 'Excluindo…',
      empty: 'Digite sua senha para continuar.',
      bad: 'Senha incorreta.',
      fail: 'Não foi possível concluir. Tente novamente.',
      done_h: 'Sua conta foi desativada',
      done: 'Seus dados serão excluídos até {date}. Se mudar de ideia, escreva para partnerships@labxperformanceapp.com antes dessa data.',
      ok: 'Entendi'
    },
    en: {
      title: 'Delete my account',
      lead: 'This deactivates your account right now and deletes your data. It cannot be undone.',
      del_h: 'Deleted',
      del: 'Your profile and metrics, activities, sleep and wellness, blood labs, nutrition, gear, races, plans and workouts, messages, Community activity and your photos and files. Your Garmin, Strava, intervals.icu, Polar and Wahoo connections are revoked immediately.',
      keep_h: 'Kept, anonymously only',
      keep: 'Subscription and payment records, for the period required by tax law, without your name, email or identifiers. And an audit record of this deletion, with no personal data.',
      when_h: 'Timeline',
      when: 'Your account is deactivated immediately (you cannot sign in and billing stops). Your data is deleted within 30 days at most; usually within 7 days.',
      pw: 'Confirm with your current password',
      cancel: 'Cancel',
      go: 'Delete my account',
      busy: 'Deleting…',
      empty: 'Enter your password to continue.',
      bad: 'Wrong password.',
      fail: 'Could not complete. Please try again.',
      done_h: 'Your account has been deactivated',
      done: 'Your data will be deleted by {date} at the latest. If you change your mind, write to partnerships@labxperformanceapp.com before then.',
      ok: 'Got it'
    }
  };

  function lang() {
    var l = 'es';
    try {
      l = (root.i18n && root.i18n.lang) || localStorage.getItem('lx_lang') || 'es';
    } catch (e) {}
    return TX[l] ? l : 'es';
  }

  function apiBase() {
    if (root.Capacitor && root.Capacitor.isNativePlatform && root.Capacitor.isNativePlatform())
      return 'https://labxperformanceapp.com/api';
    if (root.location.protocol === 'file:') return 'http://localhost:8000/api';
    return root.location.origin + '/api';
  }

  function token() {
    try {
      return localStorage.getItem('lx_co_token') || localStorage.getItem('lxapp_token') || '';
    } catch (e) {
      return '';
    }
  }

  function el(tag, css, text) {
    var n = document.createElement(tag);
    if (css) n.style.cssText = css;
    if (text != null) n.textContent = text;
    return n;
  }

  function section(box, head, body) {
    box.appendChild(el('div', 'font-weight:600;font-size:13px;margin:14px 0 4px;color:var(--text,#e6edf3)', head));
    box.appendChild(el('div', 'font-size:13px;line-height:1.55;color:var(--muted,#9aa7b4)', body));
  }

  function fmtDate(iso, l) {
    try {
      return new Date(iso).toLocaleDateString(l === 'en' ? 'en-US' : l === 'pt' ? 'pt-BR' : 'es-CL',
        { day: 'numeric', month: 'long', year: 'numeric' });
    } catch (e) {
      return String(iso).slice(0, 10);
    }
  }

  function closeModal() {
    var m = document.getElementById('lx-del-modal');
    if (m) m.parentNode.removeChild(m);
  }

  function finish() {
    try { localStorage.clear(); sessionStorage.clear(); } catch (e) {}
    root.location.href = 'landing.html';
  }

  function open() {
    closeModal();
    var l = lang(), t = TX[l];
    var back = el('div', 'position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.6);display:flex;' +
      'align-items:center;justify-content:center;padding:16px');
    back.id = 'lx-del-modal';
    var box = el('div', 'background:var(--card,#161b22);color:var(--text,#e6edf3);border:1px solid var(--border,#30363d);' +
      'border-radius:14px;max-width:460px;width:100%;max-height:90vh;overflow:auto;padding:20px 22px;' +
      'font-family:Inter,sans-serif');
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.appendChild(el('div', 'font-size:18px;font-weight:700;color:var(--red,#f85149);margin-bottom:6px', t.title));
    box.appendChild(el('div', 'font-size:13px;line-height:1.55;color:var(--muted,#9aa7b4)', t.lead));
    section(box, t.del_h, t.del);
    section(box, t.keep_h, t.keep);
    section(box, t.when_h, t.when);

    var lab = el('label', 'display:block;font-size:13px;font-weight:600;margin:16px 0 6px', t.pw);
    var pw = el('input', 'width:100%;padding:10px 12px;border-radius:8px;border:1px solid var(--border,#30363d);' +
      'background:var(--bg,#0d1117);color:var(--text,#e6edf3);font-size:14px;box-sizing:border-box');
    pw.type = 'password';
    pw.id = 'lx-del-pw';
    pw.autocomplete = 'current-password';
    lab.htmlFor = 'lx-del-pw';
    var err = el('div', 'min-height:18px;font-size:12px;color:var(--red,#f85149);margin-top:6px');
    err.id = 'lx-del-err';
    err.setAttribute('role', 'alert');
    var row = el('div', 'display:flex;gap:10px;justify-content:flex-end;margin-top:12px');
    var bCancel = el('button', 'padding:9px 16px;border-radius:8px;border:1px solid var(--border,#30363d);' +
      'background:transparent;color:var(--text,#e6edf3);cursor:pointer;font-size:13px', t.cancel);
    var bGo = el('button', 'padding:9px 16px;border-radius:8px;border:0;background:var(--red,#f85149);' +
      'color:#fff;cursor:pointer;font-size:13px;font-weight:600', t.go);
    bCancel.type = bGo.type = 'button';
    bCancel.id = 'lx-del-cancel';
    bGo.id = 'lx-del-go';
    row.appendChild(bCancel);
    row.appendChild(bGo);
    box.appendChild(lab);
    box.appendChild(pw);
    box.appendChild(err);
    box.appendChild(row);
    back.appendChild(box);
    document.body.appendChild(back);
    pw.focus();

    bCancel.addEventListener('click', closeModal);
    back.addEventListener('click', function (e) { if (e.target === back) closeModal(); });
    pw.addEventListener('keydown', function (e) { if (e.key === 'Enter') bGo.click(); });

    bGo.addEventListener('click', function () {
      err.textContent = '';
      if (!pw.value) { err.textContent = t.empty; return; }
      bGo.disabled = true;
      bGo.textContent = t.busy;
      var h = { 'Content-Type': 'application/json' };
      var tk = token();
      if (tk) h['Authorization'] = 'Bearer ' + tk;
      fetch(apiBase() + '/account/deletion-request', {
        method: 'POST', credentials: 'include', headers: h,
        body: JSON.stringify({ password: pw.value })
      }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) { return { ok: r.ok, status: r.status, j: j }; });
      }).then(function (res) {
        if (res.ok) {
          box.textContent = '';
          box.appendChild(el('div', 'font-size:18px;font-weight:700;margin-bottom:8px', t.done_h));
          box.appendChild(el('div', 'font-size:13px;line-height:1.6;color:var(--muted,#9aa7b4)',
            t.done.replace('{date}', fmtDate(res.j.deadline_at, l))));
          var ok = el('button', 'margin-top:16px;padding:9px 16px;border-radius:8px;border:0;' +
            'background:var(--cyan,#2ea8ff);color:#04121f;cursor:pointer;font-size:13px;font-weight:600', t.ok);
          ok.type = 'button';
          ok.id = 'lx-del-ok';
          ok.addEventListener('click', finish);
          box.appendChild(ok);
          return;
        }
        err.textContent = res.status === 400 ? t.bad : t.fail;
        bGo.disabled = false;
        bGo.textContent = t.go;
      }).catch(function () {
        err.textContent = t.fail;
        bGo.disabled = false;
        bGo.textContent = t.go;
      });
    });
  }

  root.LXDeleteAccount = { open: open, close: closeModal, _tx: TX };
})(window);
