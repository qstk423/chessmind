/* Full-screen, non-blocking check announcement shared by both chess boards. */
(() => {
  let lastKey = null;
  let hideTimer = null;

  function element() {
    let host = document.getElementById('check-flash');
    if (host) return host;
    host = document.createElement('div');
    host.id = 'check-flash';
    host.className = 'check-flash';
    host.hidden = true;
    host.setAttribute('role', 'status');
    host.setAttribute('aria-live', 'assertive');
    host.innerHTML = '<span class="check-flash__beam" aria-hidden="true"></span><strong class="check-flash__text"></strong>';
    document.body.appendChild(host);
    return host;
  }

  function show({ attacker, viewer = null, key = null, variant = 'chess' } = {}) {
    if (!attacker || (key && key === lastKey)) return;
    if (key) lastKey = key;
    const host = element();
    const side = attacker === 'white' ? '白方' : attacker === 'black' ? '黑方' : '红方';
    const label = viewer ? (attacker === viewer ? '将军！' : '被将军！') : `${side}将军！`;
    host.classList.toggle('check-flash--xiangqi', variant === 'xiangqi');
    host.querySelector('.check-flash__text').textContent = label;
    if (hideTimer) clearTimeout(hideTimer);
    host.hidden = false;
    host.classList.remove('is-visible');
    void host.offsetWidth;
    host.classList.add('is-visible');
    hideTimer = setTimeout(() => {
      host.hidden = true;
      host.classList.remove('is-visible');
      hideTimer = null;
    }, 1350);
  }

  function reset() {
    lastKey = null;
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = null;
    const host = document.getElementById('check-flash');
    if (host) {
      host.hidden = true;
      host.classList.remove('is-visible');
    }
  }

  window.ChessCouncilCheckFlash = { show, reset };
})();
