// Respaldo progresivo del aviso: no depende de SignalR/Blazor para ocultarlo.
// Los enlaces de acceso usan navegación HTML completa (data-enhance-nav=false).
// La devolución del estado a Blazor sigue realizándose mediante @onclick cuando
// el circuito está disponible. @key restaura un diálogo limpio al reabrirlo.
(() => {
  if (window.__carsLoginFallbackInstalled) return;
  window.__carsLoginFallbackInstalled = true;
  document.addEventListener('click', (event) => {
    if (!(event.target instanceof Element)) return;
    const dismiss = event.target.closest('[data-login-prompt-dismiss]');
    const backdrop = dismiss?.closest('.login-required-backdrop')
      ?? (event.target.matches('.login-required-backdrop') ? event.target : null);
    if (!backdrop) return;
    backdrop.setAttribute('data-login-prompt-hidden', 'true');
    // Si Blazor confirmó el cierre, desmontará el nodo antes del plazo.
    // Si se perdió el circuito, la simple ocultación no basta: se recarga
    // la misma URL para restablecer el resto de los controles del aplicativo.
    window.setTimeout(() => {
      if (backdrop.isConnected && backdrop.getAttribute('data-login-prompt-hidden') === 'true') {
        window.location.reload();
      }
    }, 1200);
  }, { capture: true });
})();
