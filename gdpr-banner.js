/**
 * S6/S11: Banner de consentimiento GDPR/cookies.
 * Auto-inyecta el banner si el usuario no ha dado consentimiento previo.
 * Al aceptar: guarda en localStorage + llama al API /api/auth/consent (si autenticado).
 *
 * Incluir en cualquier HTML: <script src="/gdpr-banner.js"></script>
 */
(function () {
  'use strict';

  var CONSENT_KEY = 'labx_gdpr_consent';

  function hasConsent() {
    try { return !!localStorage.getItem(CONSENT_KEY); } catch(e) { return true; }
  }

  function saveConsent() {
    try { localStorage.setItem(CONSENT_KEY, '1'); } catch(e) {}
  }

  function callConsentApi() {
    // Solo si hay token (usuario autenticado) — registrar en el servidor
    fetch('/api/auth/consent', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' }
    }).catch(function() { /* silencioso si falla o no está logado */ });
  }

  function dismiss() {
    var b = document.getElementById('gdpr-banner');
    if (b) { b.style.opacity = '0'; setTimeout(function() { b.remove(); }, 300); }
    saveConsent();
    callConsentApi();
  }

  function injectBanner() {
    var style = [
      '#gdpr-banner{',
      '  position:fixed;bottom:0;left:0;right:0;z-index:9999;',
      '  background:rgba(8,18,30,.97);border-top:1px solid rgba(8,116,174,.3);',
      '  padding:16px 24px;display:flex;align-items:center;gap:16px;',
      '  flex-wrap:wrap;font-family:Inter,sans-serif;font-size:13px;',
      '  color:#7FB3CC;backdrop-filter:blur(8px);',
      '  transition:opacity .3s;',
      '}',
      '#gdpr-banner a{color:#0EA5E9;text-decoration:underline}',
      '#gdpr-banner .gdpr-text{flex:1;min-width:200px}',
      '#gdpr-banner .gdpr-btns{display:flex;gap:8px;flex-shrink:0}',
      '#gdpr-banner button{',
      '  border:none;border-radius:8px;padding:8px 18px;cursor:pointer;',
      '  font-size:13px;font-weight:500;font-family:inherit;transition:.2s;',
      '}',
      '#gdpr-accept{background:#0EA5E9;color:#fff}',
      '#gdpr-accept:hover{background:#0284C7}',
      '#gdpr-reject{background:transparent;border:1px solid rgba(8,116,174,.4)!important;color:#7FB3CC}',
      '#gdpr-reject:hover{background:rgba(8,116,174,.1)}'
    ].join('');

    var styleEl = document.createElement('style');
    styleEl.textContent = style;
    document.head.appendChild(styleEl);

    var banner = document.createElement('div');
    banner.id = 'gdpr-banner';
    banner.setAttribute('role', 'dialog');
    banner.setAttribute('aria-live', 'polite');
    banner.innerHTML = [
      '<span class="gdpr-text">',
      '  Usamos cookies esenciales para el funcionamiento de la plataforma y análisis de rendimiento.',
      '  Al continuar, aceptas nuestra <a href="/privacy.html">Política de Privacidad</a>.',
      '</span>',
      '<div class="gdpr-btns">',
      '  <button id="gdpr-reject" onclick="window.__gdprDismiss(false)">Solo esenciales</button>',
      '  <button id="gdpr-accept" onclick="window.__gdprDismiss(true)">Aceptar</button>',
      '</div>'
    ].join('');
    document.body.appendChild(banner);
  }

  window.__gdprDismiss = function(accepted) {
    dismiss();
    // Punto de extensión: disparar analytics solo si accepted=true
    if (accepted && typeof window.gtag === 'function') {
      window.gtag('consent', 'update', { analytics_storage: 'granted' });
    }
  };

  // Inicializar cuando el DOM esté listo
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      if (!hasConsent()) injectBanner();
    });
  } else {
    if (!hasConsent()) injectBanner();
  }
})();
