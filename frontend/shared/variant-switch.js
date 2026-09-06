/** 棋种切换：记住上次选择，在同级页面间跳转（对弈↔对弈、学习↔学习）。 */
(function () {
  const KEY = 'cc_variant';
  const path = location.pathname || '';
  const isXiangqi = path.includes('/xiangqi');
  const current = isXiangqi ? 'xiangqi' : 'chess';
  try {
    localStorage.setItem(KEY, current);
  } catch (_) {}

  function pageName() {
    const m = path.match(/\/(index|learn|online|tools)(?:\.html)?\/?$/);
    if (m) return m[1] === 'index' ? 'index.html' : `${m[1]}.html`;
    if (path.endsWith('/xiangqi') || path.endsWith('/xiangqi/') || path.endsWith('/chess') || path.endsWith('/chess/')) {
      return 'index.html';
    }
    return 'index.html';
  }

  function wire() {
    document.querySelectorAll('[data-variant-link]').forEach((el) => {
      const v = el.getAttribute('data-variant-link');
      if (!v) return;
      el.classList.toggle('is-active', v === current);
      if (v === current) el.setAttribute('aria-current', 'true');
      else el.removeAttribute('aria-current');
      el.addEventListener('click', (ev) => {
        if (v === current) {
          ev.preventDefault();
          return;
        }
        ev.preventDefault();
        try {
          localStorage.setItem(KEY, v);
        } catch (_) {}
        location.href = `/${v}/${pageName()}${location.search || ''}`;
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
})();
