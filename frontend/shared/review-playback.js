/* Read-only snapshots: never sends a move, undo, or load-FEN request. */
window.ChessCouncilReview = {
  create({ canOpen, onStart, render, onExit, controls, notify }) {
    let current = null;
    let disabled = [];
    let origin = null;
    const bar = document.getElementById('review-playback-bar');
    function show(phase) {
      if (!current) return;
      current.phase = phase;
      render(current);
      const label = document.getElementById('review-playback-label');
      if (label) label.textContent = `关键招数 · 第${current.move.number}步 ${current.move.san || ''} · ${phase === 'before' ? '落子前' : '落子后'}（只读回看）`;
      for (const name of ['before', 'after']) {
        document.getElementById(`review-${name}`)?.setAttribute('aria-pressed', String(name === phase));
      }
    }
    function close({ focus = false } = {}) {
      if (!current) return;
      current = null;
      if (bar) bar.hidden = true;
      for (const [el, wasDisabled] of disabled) el.disabled = wasDisabled;
      disabled = [];
      onExit();
      if (focus && origin?.isConnected) origin.focus();
      origin = null;
    }
    document.getElementById('review-before')?.addEventListener('click', () => show('before'));
    document.getElementById('review-after')?.addEventListener('click', () => show('after'));
    document.getElementById('review-exit')?.addEventListener('click', () => close({ focus: true }));
    return {
      get active() { return !!current; },
      close,
      open(move, source) {
        if (!move?.fen_before || !move?.fen_after) {
          notify('这条旧记录缺少棋盘快照，请重新生成复盘。');
          return false;
        }
        if (!canOpen()) {
          notify('正在走棋，请等本步完成后再查看关键招数。');
          return false;
        }
        if (!current) {
          onStart();
          disabled = [...document.querySelectorAll(controls)].map(el => [el, el.disabled]);
          for (const [el] of disabled) el.disabled = true;
        }
        origin = source;
        current = { move: { ...move }, phase: 'after' };
        if (bar) bar.hidden = false;
        show('after');
        document.querySelector('.board-frame')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        document.getElementById('review-before')?.focus({ preventScroll: true });
        return true;
      },
    };
  },
};
