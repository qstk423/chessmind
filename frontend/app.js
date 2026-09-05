// ChessMind 前端逻辑——人机 / AI vs AI 算法对抗
const API = '/api';
let board = null;
let game = new Chess();
let orientation = 'white';
let selectedSquare = null;
let serverState = {
  mode: 'ai_vs_ai',
  controller: null,
  human_color: 'white',
  is_game_over: false,
};
let autoPlay = false;
let autoTimer = null;
let busy = false;
const STEP_DELAY_MS = 1200;
const FAST_STEP_DELAY_MS = 450;
/** 上一步起终点（JJ 象棋风格：起点留白点） */
let lastMoveFrom = null;
let lastMoveTo = null;
/** 识谱纠错模式 */
let editMode = false;
let editPiece = ''; // '' = erase, else KQRBNPkqrbnp
let editBoard = null; // Chess instance while editing
let autoDelayMs = STEP_DELAY_MS;
let progressTimer = null;

/** 联机房间 */
let online = {
  active: false,
  roomId: null,
  token: null,
  color: null,
  name: '',
  ws: null,
  reconnectTimer: null,
};

/** 名谱自动演示 */
let libraryAuto = false;
let libraryAutoTimer = null;
let libraryFilter = '';
let currentLibraryHasScript = false;

const PIECE_GLYPH = {
  K: '♔', Q: '♕', R: '♖', B: '♗', N: '♘', P: '♙',
  k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟',
  '': '空',
};

function setProgress(msg) {
  if (!msg) {
    $('#council-progress').prop('hidden', true);
    if (progressTimer) {
      clearInterval(progressTimer);
      progressTimer = null;
    }
    return;
  }
  const started = Date.now();
  $('#council-progress').prop('hidden', false);
  const tick = () => {
    const s = Math.round((Date.now() - started) / 1000);
    $('#council-progress-text').text(`${msg}（${s}s）`);
  };
  tick();
  if (progressTimer) clearInterval(progressTimer);
  progressTimer = setInterval(tick, 1000);
}

function initBoard() {
  board = Chessboard('board', {
    position: 'start',
    orientation: orientation,
    draggable: false,
    pieceTheme: 'vendor/pieces/{piece}.png',
  });

  $('#board').on('click', '.square-55d63', function () {
    const square = $(this).attr('data-square');
    handleSquareClick(square);
  });

  updateStatus();
  refreshModeControls();
}

function humanMayMove() {
  if (busy || serverState.is_game_over) return false;
  if (online.active) {
    if (!online.color) return false;
    const my = online.color === 'white' ? 'w' : 'b';
    return game.turn() === my;
  }
  if (serverState.mode === 'ai_vs_ai') return false;
  if (serverState.mode === 'human_vs_human') return true;
  // human_vs_ai：仅人类回合
  return serverState.controller === 'human';
}

function handleSquareClick(square) {
  if (editMode) {
    placeEditPiece(square);
    return;
  }
  if (!humanMayMove()) return;

  if (selectedSquare === null) {
    const piece = game.get(square);
    if (piece && piece.color === game.turn()) {
      selectPiece(square);
    }
    return;
  }

  if (square === selectedSquare) {
    deselectPiece();
    return;
  }

  const piece = game.get(square);
  if (piece && piece.color === game.turn()) {
    deselectPiece();
    selectPiece(square);
    return;
  }

  const move = game.move({
    from: selectedSquare,
    to: square,
    promotion: 'q',
  });

  if (move === null) return;

  const uci = move.from + move.to + (move.promotion || '');
  deselectPiece();
  board.position(game.fen(), false);
  markLastMove(move.from, move.to);
  updateStatus();
  submitHumanMove(uci);
}

async function submitHumanMove(uci) {
  busy = true;
  try {
    if (online.active) {
      if (online.ws && online.ws.readyState === WebSocket.OPEN) {
        online.ws.send(JSON.stringify({ type: 'move', uci }));
      } else {
        const r = await fetch(`${API}/rooms/${online.roomId}/move`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: online.token, uci }),
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) {
          alert(data.detail || '走子失败');
          await syncOnlineState();
          return;
        }
        applyOnlineMovePayload(data);
      }
      return;
    }

    const r = await fetch(`${API}/game/move`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uci }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      console.error('走子被服务器拒绝:', data);
      $('#game-status').text('走子失败，已与服务器棋局同步');
      await syncFromServer();
      return;
    }
    applyMoveResult(data);
    if (!data.game_over && data.next_controller && data.next_controller !== 'human') {
      await sleep(400);
      await runAiStep();
    }
  } catch (err) {
    console.error('分析请求失败:', err);
  } finally {
    busy = false;
  }
}

async function syncFromServer() {
  const r = await fetch(`${API}/game/state`);
  const state = await r.json();
  applyServerState(state);
  game.load(state.fen);
  board.position(state.fen, false);
  selectedSquare = null;
  clearHighlights();
  // 同步时若无逐步信息，保留或清除上一步标记
  paintLastMoveMarkers();
  updateStatus();
}

function applyServerState(state) {
  serverState = {
    mode: state.mode || 'human_vs_human',
    controller: state.controller,
    human_color: state.human_color || 'white',
    is_game_over: !!state.is_game_over,
  };
  if (state.llm_model) {
    const on = state.llm_enabled ? '已启用' : '未配置 Key（纯引擎）';
    $('#llm-status').text(`模型：${state.llm_model} · ${on}`);
  }
  refreshModeControls();
}

const FINALE_PRESETS = [
  { id: 'ladder', title: '双车错', subtitle: 'Ladder Mate', blurb: '双车梯次封锁，王退到边线无路。', winner: 'white' },
  { id: 'back_rank', title: '底线杀', subtitle: 'Back-Rank Mate', blurb: '底线被车/后切开，退路被己方堵死。', winner: 'white' },
  { id: 'smothered', title: '闷杀', subtitle: 'Smothered Mate', blurb: '马步将军，王被己方棋子围死。', winner: 'white' },
  { id: 'queen', title: '后到功成', subtitle: 'Queen Mate', blurb: '后完成绝杀。', winner: 'white' },
  { id: 'checkmate', title: '将死！', subtitle: 'Checkmate', blurb: '无路可逃，对局结束。', winner: 'white' },
];
let finalePreviewIdx = 0;

function inferFinaleClient(data) {
  if (!data || !data.game_over) return null;
  const result = data.result || '';
  if (result.includes('逼和') || result.includes('和棋')) {
    return {
      id: result.includes('逼和') ? 'stalemate' : 'draw',
      title: result.includes('逼和') ? '逼和' : '和棋',
      subtitle: result.includes('逼和') ? 'Stalemate' : 'Draw',
      blurb: result,
      winner: null,
      highlight_squares: [],
    };
  }
  return {
    id: 'checkmate',
    title: '将死！',
    subtitle: 'Checkmate',
    blurb: result || '对局结束',
    winner: result.includes('黑') ? 'black' : 'white',
    highlight_squares: [],
  };
}

function clearMateHighlights() {
  $('#board .square-55d63').removeClass('mate-glow mate-king');
  $('.board-frame').removeClass('finale-pulse');
}

function paintMateHighlights(squares) {
  clearMateHighlights();
  $('.board-frame').addClass('finale-pulse');
  (squares || []).forEach((sq, i) => {
    const el = $(`#board .square-55d63[data-square="${sq}"]`);
    if (!el.length) return;
    if (i === 0) el.addClass('mate-king');
    else el.addClass('mate-glow');
  });
}

function hideFinale() {
  const overlay = $('#finale-overlay');
  overlay.prop('hidden', true).attr('aria-hidden', 'true');
  clearMateHighlights();
}

function showFinale(finale) {
  if (!finale) return;
  stopAuto();
  const id = finale.id || 'checkmate';
  const winnerLabel = finale.winner === 'white' ? '白方胜' : finale.winner === 'black' ? '黑方胜' : '和棋';
  $('#finale-overlay .finale-stage').attr('data-mate', id);
  $('#finale-kicker').text(winnerLabel);
  $('#finale-title').text(finale.title || '将死！');
  $('#finale-sub').text(finale.subtitle || '');
  $('#finale-blurb').text(finale.blurb || '');
  paintMateHighlights(finale.highlight_squares || []);
  // 重触发 CSS 动画
  const stage = document.querySelector('#finale-overlay .finale-stage');
  if (stage) {
    stage.style.animation = 'none';
    // eslint-disable-next-line no-unused-expressions
    stage.offsetHeight;
    stage.style.animation = '';
  }
  $('#finale-overlay').prop('hidden', false).attr('aria-hidden', 'false');
  $('#ai-meta').text(`${finale.title || '终局'} · ${winnerLabel}`);
}

$('#finale-close').click(() => hideFinale());
$('#finale-review').click(() => {
  hideFinale();
  $('#btn-review').click();
});
$('#finale-new').click(() => {
  hideFinale();
  startNewGame();
});
$('#btn-preview-finale').click(() => {
  const preset = FINALE_PRESETS[finalePreviewIdx % FINALE_PRESETS.length];
  finalePreviewIdx += 1;
  showFinale({ ...preset, highlight_squares: [] });
});

function applyMoveResult(data) {
  if (data.error) {
    console.error(data.error);
    return;
  }
  game.load(data.fen);
  board.position(data.fen, false);
  serverState.is_game_over = !!data.game_over;
  serverState.controller = data.next_controller;
  serverState.mode = data.mode || serverState.mode;

  // 从 UCI 解析上一步起终点（局面分析无 uci 则不动标记）
  const uci = data.move && data.move.uci;
  if (uci && uci.length >= 4) {
    markLastMove(uci.slice(0, 2), uci.slice(2, 4));
  } else {
    paintLastMoveMarkers();
  }

  updateAnalysis(data);
  updateStatus();
  if (data.ai) {
    const src = data.ai.source || '';
    const reason = data.ai.reason || '';
    const san = (data.move && data.move.san) || '';
    $('#ai-meta').text(`AI [${data.ai.controller || ''}/${src}] ${san} — ${reason}`);
  } else if (data.move && data.move.san) {
    $('#ai-meta').text(`人类 ${data.move.san}`);
  }
  if (data.game_over) {
    stopAuto();
    showFinale(data.finale || inferFinaleClient(data));
  }
}

function markLastMove(from, to) {
  lastMoveFrom = from || null;
  lastMoveTo = to || null;
  paintLastMoveMarkers();
  requestAnimationFrame(() => paintLastMoveMarkers());
}

function clearLastMoveMarkers() {
  lastMoveFrom = null;
  lastMoveTo = null;
  $('#board .jj-origin-dot').remove();
  $('#board .jj-move-path').remove();
  $('#board .square-55d63').removeClass('last-move-from last-move-to');
}

function squareCenterInBoard(square) {
  const boardEl = document.getElementById('board');
  const sq = document.querySelector(`#board .square-55d63[data-square="${square}"]`);
  if (!boardEl || !sq) return null;
  const br = boardEl.getBoundingClientRect();
  const sr = sq.getBoundingClientRect();
  return {
    x: sr.left - br.left + sr.width / 2,
    y: sr.top - br.top + sr.height / 2,
  };
}

function paintLastMoveMarkers() {
  $('#board .jj-origin-dot').remove();
  $('#board .jj-move-path').remove();
  $('#board .square-55d63').removeClass('last-move-from last-move-to');

  if (lastMoveFrom) {
    const $from = $(`#board .square-55d63[data-square="${lastMoveFrom}"]`);
    $from.addClass('last-move-from');
    if ($from.length) {
      $from.append('<span class="jj-origin-dot" aria-hidden="true"></span>');
    }
  }
  if (lastMoveTo) {
    $(`#board .square-55d63[data-square="${lastMoveTo}"]`).addClass('last-move-to');
  }

  // 起终点之间画半透明虚线路径
  if (lastMoveFrom && lastMoveTo) {
    const a = squareCenterInBoard(lastMoveFrom);
    const b = squareCenterInBoard(lastMoveTo);
    const boardEl = document.getElementById('board');
    if (a && b && boardEl) {
      const w = boardEl.clientWidth;
      const h = boardEl.clientHeight;
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('class', 'jj-move-path');
      svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
      svg.setAttribute('width', String(w));
      svg.setAttribute('height', String(h));
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', String(a.x));
      line.setAttribute('y1', String(a.y));
      line.setAttribute('x2', String(b.x));
      line.setAttribute('y2', String(b.y));
      svg.appendChild(line);
      boardEl.appendChild(svg);
    }
  }
}

function selectPiece(square) {
  selectedSquare = square;
  $('.square-55d63').removeClass('highlight-selected');
  $(`.square-55d63[data-square="${square}"]`).addClass('highlight-selected');
  highlightLegalMoves(square);
}

function deselectPiece() {
  selectedSquare = null;
  clearHighlights();
}

function highlightLegalMoves(square) {
  clearHighlights();
  const moves = game.moves({ square: square, verbose: true });
  moves.forEach(m => {
    const $sq = $(`.square-55d63[data-square="${m.to}"]`);
    const piece = game.get(m.to);
    $sq.addClass(piece ? 'highlight-capture' : 'highlight-move');
  });
}

function clearHighlights() {
  $('.square-55d63').removeClass('highlight-selected highlight-move highlight-capture');
  // 选中高亮清掉后，把上一步标记画回去
  paintLastMoveMarkers();
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text == null ? '' : String(text);
  return div.innerHTML;
}

function formatText(text) {
  if (!text) return '<p class="placeholder">暂无分析</p>';
  return text
    .split('\n')
    .filter(l => l.trim())
    .map(l => `<p>${escapeHtml(l)}</p>`)
    .join('');
}

function renderOpinion(op, title) {
  if (!op) return `<p class="placeholder">${escapeHtml(title)}暂无数据</p>`;
  const points = (op.reasoning_points || []).map(p => `<li>${escapeHtml(p)}</li>`).join('');
  const concerns = (op.concerns || []).map(p => `<li>${escapeHtml(p)}</li>`).join('');
  return `
    <div class="agent-card">
      <div class="agent-meta">
        <span>推荐 ${escapeHtml(op.recommended_move || '—')}</span>
        <span>置信 ${Math.round((op.confidence || 0) * 100)}%</span>
        <span>风险 ${Math.round((op.risk || 0) * 100)}%</span>
        <span>评估 ${op.evaluation ?? '—'}</span>
        ${op.parse_ok === false ? '<span>⚠ 解析降级</span>' : ''}
      </div>
      ${formatText(op.summary)}
      ${points ? `<p><strong>要点</strong></p><ul class="agent-list">${points}</ul>` : ''}
      ${concerns ? `<p><strong>顾虑</strong></p><ul class="agent-list">${concerns}</ul>` : ''}
    </div>`;
}

function renderDebate(council) {
  if (!council) return '<p class="placeholder">本步未启用 Council</p>';
  const d = council.debate || {};
  const v = council.verdict || {};
  if (!d.triggered) {
    return `
      <p>未触发辩论（争议度不足阈值）。</p>
      <div class="verdict-box">
        <p><strong>共识裁决</strong>：${escapeHtml(v.recommended_move || '—')}</p>
        ${formatText(v.summary || '')}
      </div>`;
  }
  const rounds = (d.rounds || []).map(r => `
    <div class="debate-round">
      <div class="who">${escapeHtml(r.speaker)} · ${escapeHtml(r.role)}</div>
      ${formatText(r.text)}
    </div>`).join('');
  return `
    <p>已触发交叉质询与仲裁。</p>
    ${rounds}
    <div class="verdict-box">
      <p><strong>仲裁结果</strong>：${escapeHtml(v.recommended_move || '—')}
        （置信 ${Math.round((v.confidence || 0) * 100)}%）</p>
      ${formatText(v.summary || '')}
    </div>`;
}

function updateDisagreement(council) {
  if (!council || !council.disagreement) {
    $('#dg-fill').css('width', '0%');
    $('#dg-label').text('等待分析…');
    $('#dg-moves').text('');
    return;
  }
  const dg = council.disagreement;
  const pct = Math.round((dg.disagreement_score || 0) * 100);
  $('#dg-fill').css('width', pct + '%');
  $('#dg-label').text(`${dg.badge || ''} · 争议度 ${pct}% · ${dg.label || ''}`);
  const rm = dg.recommended_moves || {};
  $('#dg-moves').text(`⚔️${rm.tactical || '—'}  🧠${rm.strategic || '—'}  🛡️${rm.risk || '—'}`);
}

function updateAnalysis(data) {
  if (data.error) return;

  const e = data.evaluation || {};
  const a = data.analysis || {};
  const council = a.council;
  const after = e.after || {};

  const wp = Math.round((after.win_prob_white != null ? after.win_prob_white : 0.5) * 100);
  const bp = Math.round((after.win_prob_black != null ? after.win_prob_black : 0.5) * 100);
  $('#eval-white').css('height', wp + '%');
  $('#eval-black').css('height', bp + '%');
  $('#white-prob').text(`白方 ${wp}%`);
  $('#black-prob').text(`黑方 ${bp}%`);

  const clsLabels = {
    brilliant: '✨ 妙手！', great: '👍 好棋', good: '✓ 正常',
    inaccuracy: '🤔 缓着', mistake: '⚠️ 漏着', blunder: '💀 大漏',
    position: '📍 局面',
  };
  const cls = e.classification || 'good';
  $('#move-class')
    .text(clsLabels[cls] || cls)
    .attr('class', 'move-class ' + cls);

  updateDisagreement(council);

  if (council && council.agents) {
    $('#tab-summary').html(renderOpinion(council.agents.coach, '教练'));
    $('#tab-tactical').html(renderOpinion(council.agents.tactical, '战术'));
    $('#tab-strategic').html(renderOpinion(council.agents.strategic, '战略'));
    $('#tab-risk').html(renderOpinion(council.agents.risk, '风险'));
    $('#tab-debate').html(renderDebate(council));
  } else {
    $('#tab-summary').html(formatText(a.summary));
    $('#tab-tactical').html(formatText(a.tactical));
    $('#tab-strategic').html(formatText(a.strategic));
    $('#tab-risk').html(formatText(a.pattern));
    $('#tab-debate').html('<p class="placeholder">本步跳过 Council</p>');
  }

  if (data.game_over) {
    $('#game-status').text('对局结束 — ' + (data.result || ''));
  }
}

function updateStatus() {
  if (serverState.is_game_over || game.game_over()) {
    $('#game-status').text('对局结束');
    return;
  }
  const turn = game.turn() === 'w' ? '白方' : '黑方';
  if (online.active) {
    const mine = online.color === 'white' ? '白' : online.color === 'black' ? '黑' : '?';
    const myTurn = humanMayMove();
    $('#game-status').text(`${turn}走棋 · 你执${mine}${myTurn ? ' · 轮到你' : ' · 等待对手'}`);
    return;
  }
  const ctrl = serverState.controller;
  const ctrlLabel = ctrl === 'llm' ? 'LLM' : ctrl === 'engine' ? 'Stockfish' : ctrl === 'human' ? '人类' : '';
  $('#game-status').text(ctrlLabel ? `${turn}走棋（${ctrlLabel}）` : `${turn}走棋`);
}

function refreshModeControls() {
  const mode = $('#game-mode').val();
  $('#human-color').prop('disabled', mode !== 'human_vs_ai');
  $('#white-ai').prop('disabled', mode !== 'ai_vs_ai');
}

function newGamePayload() {
  return {
    mode: $('#game-mode').val(),
    human_color: $('#human-color').val(),
    white_ai: $('#white-ai').val(),
    engine_depth: parseInt($('#engine-depth').val(), 10),
    with_analysis: $('#with-analysis').is(':checked'),
    coach_level: $('#coach-level').val(),
  };
}

function resetPanels() {
  game = new Chess();
  board.position('start', false);
  orientation = 'white';
  board.orientation('white');
  selectedSquare = null;
  clearLastMoveMarkers();
  clearHighlights();
  $('#move-class').text('等待走棋…').attr('class', 'move-class');
  $('#eval-white, #eval-black').css('height', '50%');
  $('#white-prob').text('白方 50%');
  $('#black-prob').text('黑方 50%');
  $('.tab-content').html('<p class="placeholder">对局进行中…</p>');
  $('#tab-summary').addClass('active');
  $('#ai-meta').text('新对局已开始');
  updateStatus();
}

async function startNewGame() {
  stopAuto();
  hideFinale();
  if (online.active) {
    if (online.ws && online.ws.readyState === WebSocket.OPEN) {
      online.ws.send(JSON.stringify({ type: 'reset' }));
    } else {
      await fetch(`${API}/rooms/${online.roomId}/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: online.token }),
      });
      await syncOnlineState();
    }
    return;
  }
  busy = true;
  try {
    const r = await fetch(`${API}/game/new`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newGamePayload()),
    });
    const state = await r.json();
    applyServerState(state);
    resetPanels();
    // 人机且人类执黑，或 AI vs AI：需要 AI 先走 / 可自动
    if (state.mode === 'human_vs_ai' && state.controller && state.controller !== 'human') {
      await runAiStep();
    }
  } finally {
    busy = false;
  }
}

async function runAiStep() {
  if (busy && !autoPlay) return;
  if (serverState.is_game_over) return;
  if (serverState.controller === 'human') return;

  busy = true;
  const useCouncil = $('#with-analysis').is(':checked');
  $('#game-status').text(useCouncil ? 'AI + Council…' : 'AI 思考中…');
  if (useCouncil) setProgress('AI 走子与 Council 分析中');
  try {
    const r = await fetch(`${API}/game/ai-step`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      console.error('AI 走子失败:', data);
      $('#ai-meta').text('AI 走子失败：' + escapeHtml(JSON.stringify(data.detail || data)));
      stopAuto();
      await syncFromServer();
      return;
    }
    applyMoveResult(data);
  } catch (err) {
    console.error(err);
    stopAuto();
  } finally {
    setProgress(null);
    busy = false;
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function stopAuto() {
  autoPlay = false;
  if (autoTimer) {
    clearTimeout(autoTimer);
    autoTimer = null;
  }
  $('#btn-auto').text('自动对战').prop('disabled', false);
  $('#btn-pause').prop('disabled', true);
}

function scheduleAuto() {
  if (!autoPlay || serverState.is_game_over) {
    stopAuto();
    return;
  }
  autoTimer = setTimeout(async () => {
    if (!autoPlay) return;
    await runAiStep();
    if (autoPlay && !serverState.is_game_over) {
      scheduleAuto();
    } else {
      stopAuto();
    }
  }, autoDelayMs);
}

function startAuto() {
  if (serverState.mode !== 'ai_vs_ai' && serverState.mode !== 'human_vs_ai') {
    alert('请先选择「AI vs AI」或「人 vs AI」模式并开新对局');
    return;
  }
  autoDelayMs = $('#with-analysis').is(':checked') ? STEP_DELAY_MS : FAST_STEP_DELAY_MS;
  autoPlay = true;
  $('#btn-auto').text('对战中…').prop('disabled', true);
  $('#btn-pause').prop('disabled', false);
  scheduleAuto();
}

$('#btn-new-game').click(() => startNewGame());
$('#btn-flip').click(() => {
  orientation = orientation === 'white' ? 'black' : 'white';
  board.orientation(orientation);
  requestAnimationFrame(() => paintLastMoveMarkers());
});
$('#btn-ai-step').click(async () => {
  if (busy || autoPlay) return;
  await runAiStep();
});
$('#btn-auto').click(() => startAuto());
$('#btn-pause').click(() => stopAuto());
$('#game-mode').change(refreshModeControls);

$('#btn-review').click(async () => {
  try {
    const data = await fetch(`${API}/game/review`).then(r => r.json());
    const narr = (data.narrative || []).map(t => `<li>${escapeHtml(t)}</li>`).join('');
    const highs = (data.highlights || []).map(h =>
      `<li>第${escapeHtml(String(h.number))}步 ${escapeHtml(h.san)} · ${escapeHtml(h.classification)} · 争议 ${Math.round((h.disagreement_score || 0) * 100)}%</li>`
    ).join('');
    const debates = (data.debates || []).map(d =>
      `<li>第${escapeHtml(String(d.number))}步 ${escapeHtml(d.san)} → 仲裁 ${escapeHtml(d.verdict || '—')}</li>`
    ).join('');
    $('#review-section').show();
    $('#review-result').html(`
      <div class="review-block">
        <p><strong>${escapeHtml(data.title || '复盘')}</strong> · 共 ${data.total_moves} 步 · 辩论 ${data.debate_count || 0} 次 · 平均争议 ${Math.round((data.avg_disagreement || 0) * 100)}%</p>
        <p><strong>叙事</strong></p><ul>${narr || '<li>暂无</li>'}</ul>
        <p><strong>关键局面</strong></p><ul>${highs || '<li>暂无</li>'}</ul>
        <p><strong>辩论回合</strong></p><ul>${debates || '<li>本局未触发辩论</li>'}</ul>
        <pre style="white-space:pre-wrap;font-size:0.78rem;opacity:0.8">${escapeHtml(data.pgn || '')}</pre>
      </div>`);
    document.getElementById('review-section').scrollIntoView({ behavior: 'smooth' });
  } catch (e) {
    alert('复盘请求失败');
  }
});

async function runDemoById(demoId, title) {
  if (busy) return;
  busy = true;
  stopAuto();
  setProgress(`路演 Council：${title || demoId}`);
  $('#ai-meta').text(`加载 Demo：${title || demoId} …`);
  try {
    const r = await fetch(`${API}/demos/${encodeURIComponent(demoId)}/run`, { method: 'POST' });
    const payload = await r.json();
    if (!r.ok) {
      alert('Demo 失败：' + JSON.stringify(payload.detail || payload));
      return;
    }
    const state = payload.state || {};
    applyServerState(state);
    clearLastMoveMarkers();
    game.load(state.fen);
    board.position(state.fen, false);
    selectedSquare = null;
    clearHighlights();
    updateStatus();
    if (payload.analysis) {
      applyMoveResult({
        ...payload.analysis,
        move: { san: '局面分析', uci: '', number: 0 },
        game_over: payload.analysis.game_over,
        result: payload.analysis.result,
      });
      $('#ai-meta').text(`Demo「${title || demoId}」Council 完成 · 可点复盘`);
      if (payload.analysis.analysis?.council?.debate?.triggered) {
        $('.tab').removeClass('active');
        $('.tab-content').removeClass('active');
        $('.tab[data-tab="debate"]').addClass('active');
        $('#tab-debate').addClass('active');
      }
    }
  } finally {
    setProgress(null);
    busy = false;
  }
}

async function loadDemos() {
  try {
    const data = await fetch(`${API}/demos`).then(r => r.json());
    const box = $('#demo-buttons').empty();
    (data.demos || []).forEach(d => {
      const btn = $(`<button type="button" title="${escapeHtml(d.blurb)}">${escapeHtml(d.title)}</button>`);
      btn.click(() => runDemoById(d.id, d.title));
      box.append(btn);
    });
  } catch (e) {
    $('#demo-buttons').text('Demo 列表加载失败');
  }
}

$('#btn-pitch-demo').click(() => runDemoById('greek_gift', '希腊赠礼（攻王弃象）'));

$('#btn-pitch-fast').click(async () => {
  if (busy) return;
  stopAuto();
  $('#game-mode').val('ai_vs_ai');
  $('#with-analysis').prop('checked', false);
  $('#engine-depth').val('8');
  autoDelayMs = FAST_STEP_DELAY_MS;
  refreshModeControls();
  await startNewGame();
  $('#ai-meta').text('快速对战：Council 已关 · 深度 8');
  startAuto();
});

$('#btn-show-logs').click(() => {
  const el = document.getElementById('logs-section');
  if (el) {
    el.open = true;
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  refreshLogs();
});

async function refreshLogs() {
  const box = $('#logs-list');
  try {
    const data = await fetch(`${API}/logs/recent?limit=15`).then((r) => r.json());
    const logs = data.logs || [];
    if (!logs.length) {
      box.html('<div class="history-empty">尚无调用记录（跑一次 Demo 后刷新）</div>');
      return;
    }
    box.empty();
    logs.slice().reverse().forEach((row) => {
      const ok = row.success !== false;
      const item = $('<div class="log-item"></div>');
      item.html(
        `<div><strong>${escapeHtml(row.agent || '?')}</strong> · ${escapeHtml(row.model || '')}` +
          ` <span class="meta">${ok ? 'OK' : 'FAIL'} · ${Math.round(row.latency_ms || 0)}ms` +
          (row.total_tokens != null || row.usage?.total_tokens != null
            ? ` · ${row.total_tokens ?? row.usage.total_tokens} tok`
            : '') +
          `</span></div>` +
          `<div class="meta">${escapeHtml((row.ts || row.timestamp || '').toString().slice(0, 19))}` +
          (row.error ? ` · ${escapeHtml(String(row.error).slice(0, 80))}` : '') +
          `</div>`
      );
      box.append(item);
    });
  } catch (_) {
    box.html('<div class="history-empty">日志加载失败</div>');
  }
}

$('#btn-refresh-logs').click(() => refreshLogs());
$('#btn-ping-llm').click(async () => {
  setProgress('Ping LLM…');
  try {
    const h = await fetch(`${API}/health?ping_llm=true`).then((r) => r.json());
    $('#llm-status').text(
      `模型：${h.llm_model || '?'} · ping ${h.llm_ping || '?'} · 引擎${h.stockfish ? '就绪' : '降级'}`
    );
    $('#ai-meta').text(
      h.llm_ping === 'ok'
        ? `LLM ping OK · ${h.llm_latency_ms || '?'}ms`
        : `LLM ping：${h.llm_ping || 'fail'} ${h.llm_error || ''}`
    );
    refreshLogs();
  } finally {
    setProgress(null);
  }
});

$('#btn-analyze-pos').click(async () => {
  if (busy) return;
  busy = true;
  setProgress('分析当前局面…');
  $('#ai-meta').text('正在分析当前局面…');
  try {
    const r = await fetch(`${API}/game/analyze-position`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ with_analysis: true }),
    });
    const data = await r.json();
    if (!r.ok) {
      alert('分析失败');
      return;
    }
    applyMoveResult({
      ...data,
      move: { san: '局面分析', uci: '', number: 0 },
    });
    $('#ai-meta').text('当前局面 Council 完成');
  } finally {
    setProgress(null);
    busy = false;
  }
});

async function compressImageFile(file, maxSide = 1280, quality = 0.82) {
  if (!file || !file.type.startsWith('image/')) return file;
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    const w = Math.max(1, Math.round(bitmap.width * scale));
    const h = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(bitmap, 0, 0, w, h);
    bitmap.close();
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', quality));
    if (!blob) return file;
    return new File([blob], (file.name || 'board').replace(/\.\w+$/, '') + '.jpg', { type: 'image/jpeg' });
  } catch (_) {
    return file;
  }
}

function showVisionPreview(file) {
  if (!file) {
    $('#vision-preview').attr('hidden', true).attr('src', '');
    $('#vision-preview-empty').show();
    return;
  }
  const url = URL.createObjectURL(file);
  $('#vision-preview-empty').hide();
  $('#vision-preview').attr('hidden', false).attr('src', url);
}

$('#vision-file').on('change', function () {
  const file = this.files && this.files[0];
  showVisionPreview(file || null);
  if (file) $('#vision-status').text(`已选择：${file.name}`);
});

$('#btn-vision').click(async () => {
  const input = $('#vision-file')[0];
  const file = input.files && input.files[0];
  if (!file) {
    alert('请先拍照或选择棋盘照片');
    return;
  }
  if (busy) return;
  busy = true;
  stopAuto();
  $('#vision-status').text('压缩并识别中…');
  $('#ai-meta').text('正在把照片映射到棋盘…');
  try {
    const compressed = await compressImageFile(file);
    const side = $('#vision-side').val() || '';
    const analyze = $('#vision-analyze').is(':checked');
    const fd = new FormData();
    fd.append('file', compressed, compressed.name || 'board.jpg');
    const qs = new URLSearchParams({
      apply: 'true',
      analyze: analyze ? 'true' : 'false',
    });
    if (side) qs.set('side_to_move', side);
    const r = await fetch(`${API}/vision/fen?${qs.toString()}`, { method: 'POST', body: fd });
    const data = await r.json();
    if (!r.ok) {
      const detail = data.detail || data;
      $('#vision-status').text('识别失败');
      alert('识谱失败：' + (typeof detail === 'string' ? detail : JSON.stringify(detail)));
      return;
    }
    const state = data.state || {};
    applyServerState(state);
    clearLastMoveMarkers();
    game.load(state.fen);
    board.position(state.fen, false);
    selectedSquare = null;
    clearHighlights();
    updateStatus();
    const fenShort = (data.vision && data.vision.fen) ? data.vision.fen.split(' ').slice(0, 2).join(' ') : '';
    $('#vision-status').text(
      `已映射 · ${data.vision?.vision_model || ''} · ${Math.round(data.vision?.latency_ms || 0)}ms`
    );
    $('#ai-meta').text(`照片局面已加载：${fenShort}`);

    if (data.analysis) {
      applyMoveResult({
        ...data.analysis,
        move: { san: '识谱分析', uci: '', number: 0 },
      });
      $('#ai-meta').text('照片已映射，Council 分析完成');
    } else {
      enterEditMode(state.fen);
      $('#vision-status').text(
        `已映射 · 请纠错后确认 · ${data.vision?.vision_model || ''} · ${Math.round(data.vision?.latency_ms || 0)}ms`
      );
    }
  } catch (e) {
    console.error(e);
    $('#vision-status').text('请求失败');
  } finally {
    busy = false;
  }
});

function buildPiecePalette() {
  const box = $('#piece-palette').empty();
  const order = ['K', 'Q', 'R', 'B', 'N', 'P', 'k', 'q', 'r', 'b', 'n', 'p', ''];
  order.forEach((sym) => {
    const btn = $('<button type="button" class="piece-btn"></button>')
      .attr('data-piece', sym)
      .text(PIECE_GLYPH[sym] || sym)
      .attr('title', sym || '清空格子');
    if (sym === editPiece) btn.addClass('active');
    btn.on('click', () => {
      editPiece = sym;
      $('.piece-btn').removeClass('active');
      btn.addClass('active');
    });
    box.append(btn);
  });
}

function syncEditFenPreview() {
  if (!editBoard) return;
  const parts = editBoard.fen().split(' ');
  parts[1] = $('#edit-turn').val() || 'w';
  $('#edit-fen-preview').text(parts.join(' '));
  board.position(editBoard.fen(), false);
}

function enterEditMode(fen) {
  stopAuto();
  deselectPiece();
  clearLastMoveMarkers();
  editMode = true;
  editBoard = new Chess();
  try {
    editBoard.load(fen);
  } catch (_) {
    editBoard.reset();
  }
  const turn = editBoard.turn() === 'b' ? 'b' : 'w';
  $('#edit-turn').val(turn);
  editPiece = 'P';
  buildPiecePalette();
  $('#fen-editor').prop('hidden', false);
  $('.board-frame').addClass('edit-mode');
  syncEditFenPreview();
  $('#ai-meta').text('纠错模式：点格子放置棋子');
}

function exitEditMode() {
  editMode = false;
  editBoard = null;
  $('#fen-editor').prop('hidden', true);
  $('.board-frame').removeClass('edit-mode');
}

function placeEditPiece(square) {
  if (!editBoard) return;
  editBoard.remove(square);
  if (editPiece) {
    const color = editPiece === editPiece.toUpperCase() ? 'w' : 'b';
    const type = editPiece.toLowerCase();
    editBoard.put({ type, color }, square);
  }
  syncEditFenPreview();
}

function currentEditFen() {
  if (!editBoard) return game.fen();
  const parts = editBoard.fen().split(' ');
  parts[1] = $('#edit-turn').val() || 'w';
  // 清掉易位/吃过路兵，避免随意摆子后非法
  parts[2] = '-';
  parts[3] = '-';
  return parts.join(' ');
}

async function applyEditedFen({ analyze }) {
  if (busy) return;
  busy = true;
  try {
    const fen = currentEditFen();
    const r = await fetch(`${API}/game/load-fen`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fen }),
    });
    const state = await r.json();
    if (!r.ok) {
      alert('应用失败：' + JSON.stringify(state.detail || state));
      return;
    }
    applyServerState(state);
    clearLastMoveMarkers();
    game.load(state.fen);
    board.position(state.fen, false);
    selectedSquare = null;
    clearHighlights();
    updateStatus();
    exitEditMode();
    $('#vision-status').text('纠错已确认');
    if (analyze) {
      const ar = await fetch(`${API}/game/analyze-position`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ with_analysis: true }),
      });
      const data = await ar.json();
      if (ar.ok) {
        applyMoveResult({
          ...data,
          move: { san: '纠错后分析', uci: '', number: 0 },
        });
        $('#ai-meta').text('纠错局面 Council 完成');
      }
    } else {
      $('#ai-meta').text('纠错局面已加载');
    }
    refreshHistory();
  } finally {
    busy = false;
  }
}

$('#btn-edit-fen').click(() => enterEditMode(game.fen()));
$('#btn-cancel-edit').click(() => {
  exitEditMode();
  board.position(game.fen(), false);
  updateStatus();
});
$('#edit-turn').on('change', syncEditFenPreview);
$('#btn-apply-fen').click(() => applyEditedFen({ analyze: false }));
$('#btn-apply-analyze').click(() => applyEditedFen({ analyze: true }));

async function refreshHistory() {
  const box = $('#history-list');
  try {
    const data = await fetch(`${API}/games?limit=20`).then((r) => r.json());
    const games = data.games || [];
    if (!games.length) {
      box.html('<div class="history-empty">暂无历史对局</div>');
      return;
    }
    box.empty();
    games.forEach((g) => {
      const item = $('<div class="history-item"></div>');
      const when = (g.updated_at || g.created_at || '').replace('T', ' ').slice(0, 19);
      item.append(
        $('<div></div>').html(
          `<strong>${g.title || g.id.slice(0, 8)}</strong>` +
            `<div class="meta">${when} · ${g.mode || '?'} · ${g.move_count || 0} 步` +
            (g.result ? ` · ${g.result}` : '') +
            `</div>`
        )
      );
      const actions = $('<div class="actions"></div>');
      const restore = $('<button type="button">恢复</button>').on('click', async () => {
        if (busy) return;
        busy = true;
        try {
          const r = await fetch(`${API}/games/${g.id}/restore`, { method: 'POST' });
          const state = await r.json();
          if (!r.ok) {
            alert('恢复失败');
            return;
          }
          stopAuto();
          exitEditMode();
          applyServerState(state);
          clearLastMoveMarkers();
          game.load(state.fen);
          board.position(state.fen, false);
          selectedSquare = null;
          clearHighlights();
          updateStatus();
          $('#ai-meta').text(`已恢复历史局面 ${g.id.slice(0, 8)}`);
        } finally {
          busy = false;
        }
      });
      const del = $('<button type="button">删除</button>').on('click', async () => {
        if (!confirm('删除该历史记录？')) return;
        await fetch(`${API}/games/${g.id}`, { method: 'DELETE' });
        refreshHistory();
      });
      actions.append(restore, del);
      item.append(actions);
      box.append(item);
    });
  } catch (_) {
    box.html('<div class="history-empty">历史加载失败</div>');
  }
}

$('#btn-refresh-history').click(() => refreshHistory());
$('#btn-save-game').click(async () => {
  const title = prompt('对局标题（可留空）', '') || null;
  const r = await fetch(`${API}/game/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, with_review: true }),
  });
  const data = await r.json();
  if (!r.ok) {
    alert('保存失败');
    return;
  }
  $('#ai-meta').text(`已保存 ${data.game?.id?.slice(0, 8) || ''}`);
  refreshHistory();
});

$('.tab').click(function () {
  $('.tab').removeClass('active');
  $('.tab-content').removeClass('active');
  $(this).addClass('active');
  $('#tab-' + $(this).data('tab')).addClass('active');
});

$('#btn-analyze-pgn').click(async () => {
  const pgn = $('#pgn-input').val().trim();
  if (!pgn) return;

  $('#btn-analyze-pgn').text('分析中…').prop('disabled', true);
  try {
    const res = await fetch(`${API}/analyze/pgn`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pgn }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      $('#pgn-result').html(`<p class="placeholder">分析失败：${escapeHtml(err.detail || res.statusText)}</p>`);
      return;
    }
    const data = await res.json();
    if (data.moves && data.moves.length) {
      $('#pgn-result').html(
        `<p>共分析 <strong>${data.total_moves}</strong> 步</p>` +
        data.moves.slice(-10).map(m =>
          `<div style="margin-bottom:8px;padding:8px;background:#2a2a4a;border-radius:4px">
            <strong>第${escapeHtml(String(m.move.number))}步 ${escapeHtml(m.move.san)}</strong> [${m.evaluation.classification}]
            <p style="margin-top:4px;font-size:0.85rem;color:#ccc">${escapeHtml(m.analysis.summary || '')}</p>
          </div>`
        ).join('')
      );
    } else {
      $('#pgn-result').html('<p class="placeholder">未解析出有效走法</p>');
    }
  } catch (err) {
    console.error('PGN 分析失败:', err);
    $('#pgn-result').html('<p class="placeholder">分析请求失败，请检查服务是否运行</p>');
  } finally {
    $('#btn-analyze-pgn').text('分析 PGN').prop('disabled', false);
  }
});

function stopAuto() {
  autoPlay = false;
  if (autoTimer) {
    clearTimeout(autoTimer);
    autoTimer = null;
  }
  $('#btn-auto').text('自动对战').prop('disabled', false);
  $('#btn-pause').prop('disabled', true);
}

function stopLibraryAuto() {
  libraryAuto = false;
  if (libraryAutoTimer) {
    clearTimeout(libraryAutoTimer);
    libraryAutoTimer = null;
  }
  $('#btn-lib-auto').prop('disabled', !currentLibraryHasScript);
  $('#btn-lib-stop').prop('disabled', true);
}

function updateLibraryChrome(lib) {
  if (!lib) {
    currentLibraryHasScript = false;
    $('#lib-status').text('');
    $('#btn-lib-step, #btn-lib-auto, #btn-lib-ai').prop('disabled', true);
    $('#btn-lib-stop').prop('disabled', true);
    return;
  }
  currentLibraryHasScript = !!lib.has_script;
  const prog = lib.has_script
    ? `跟谱 ${lib.index || 0}/${lib.total_moves || 0}`
    : '局面体验（无固定名谱）';
  $('#lib-status').text(
    `${lib.title || ''} · ${prog}` + (lib.goal ? ` · 目标：${lib.goal}` : '')
  );
  $('#btn-lib-step').prop('disabled', !lib.has_script || !!lib.done);
  $('#btn-lib-auto').prop('disabled', !lib.has_script || !!lib.done || libraryAuto);
  $('#btn-lib-ai').prop('disabled', false);
  $('#btn-lib-stop').prop('disabled', !libraryAuto);
}

async function loadLibraryItem(itemId, { mode, forAi } = {}) {
  if (online.active) {
    alert('请先退出联机房间，再加载名局/残局');
    return;
  }
  stopAuto();
  stopLibraryAuto();
  hideFinale();
  const body = {
    mode: mode || (forAi ? 'ai_vs_ai' : 'human_vs_human'),
    with_analysis: false,
  };
  const r = await fetch(`${API}/library/${encodeURIComponent(itemId)}/load`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const state = await r.json();
  if (!r.ok) {
    alert(JSON.stringify(state.detail || state));
    return;
  }
  applyServerState(state);
  clearLastMoveMarkers();
  game.load(state.fen);
  board.position(state.fen, false);
  selectedSquare = null;
  clearHighlights();
  // 残局常执劣势方在下，保持白在下；若黑先行可翻面
  if ((state.turn || '').startsWith('b')) {
    orientation = 'black';
    board.orientation('black');
  } else {
    orientation = 'white';
    board.orientation('white');
  }
  updateStatus();
  updateLibraryChrome(state.library);
  $('#game-mode').val(body.mode);
  refreshModeControls();
  $('#ai-meta').text(`已加载：${state.library?.title || itemId}`);
  if (forAi) {
    autoDelayMs = FAST_STEP_DELAY_MS;
    startAuto();
  }
}

async function libraryStepOnce() {
  if (busy) return false;
  busy = true;
  try {
    const r = await fetch(`${API}/library/step`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ with_analysis: false }),
    });
    const data = await r.json();
    if (!r.ok) {
      stopLibraryAuto();
      $('#lib-status').text(data.detail?.error || data.detail || '演示结束');
      updateLibraryChrome(data.detail?.library || data.library);
      return false;
    }
    applyMoveResult(data);
    updateLibraryChrome(data.library);
    if (data.library?.done || data.game_over) {
      stopLibraryAuto();
      $('#ai-meta').text('名谱演示完成');
      return false;
    }
    return true;
  } finally {
    busy = false;
  }
}

function startLibraryAuto() {
  if (!currentLibraryHasScript) return;
  stopAuto();
  libraryAuto = true;
  $('#btn-lib-auto').prop('disabled', true);
  $('#btn-lib-stop').prop('disabled', false);
  const tick = async () => {
    if (!libraryAuto) return;
    const ok = await libraryStepOnce();
    if (ok && libraryAuto) {
      libraryAutoTimer = setTimeout(tick, 700);
    }
  };
  tick();
}

async function loadLibraryList() {
  const qs = libraryFilter ? `?category=${encodeURIComponent(libraryFilter)}` : '';
  const box = $('#library-list');
  try {
    const data = await fetch(`${API}/library${qs}`).then((r) => r.json());
    const items = data.items || [];
    if (!items.length) {
      box.html('<div class="history-empty">暂无条目</div>');
      return;
    }
    box.empty();
    items.forEach((it) => {
      const el = $('<div class="lib-item"></div>');
      el.append(`<h4>${escapeHtml(it.title)}</h4>`);
      el.append(
        `<div class="meta">${escapeHtml(it.category_label || it.category)}` +
          (it.year ? ` · ${it.year}` : '') +
          (it.players ? ` · ${escapeHtml(it.players)}` : '') +
          (it.has_script ? ` · ${it.move_count} 步名谱` : ' · 局面体验') +
          `</div>`
      );
      el.append(`<div class="blurb">${escapeHtml(it.blurb || '')}</div>`);
      const row = $('<div class="row"></div>');
      row.append(
        $('<button type="button">加载体验</button>').on('click', () =>
          loadLibraryItem(it.id, { mode: 'human_vs_human' })
        )
      );
      if (it.has_script) {
        row.append(
          $('<button type="button" class="accent">演示名谱</button>').on('click', async () => {
            await loadLibraryItem(it.id, { mode: 'human_vs_human' });
            startLibraryAuto();
          })
        );
      }
      row.append(
        $('<button type="button">AI 代下</button>').on('click', () =>
          loadLibraryItem(it.id, { forAi: true })
        )
      );
      if (it.tags && it.tags.includes('debate')) {
        row.append(
          $('<button type="button">Council 分析</button>').on('click', async () => {
            await loadLibraryItem(it.id, { mode: 'human_vs_human' });
            $('#btn-analyze-pos').click();
          })
        );
      }
      el.append(row);
      box.append(el);
    });
  } catch (_) {
    box.html('<div class="history-empty">学习库加载失败</div>');
  }
}

$('.lib-filter').click(function () {
  $('.lib-filter').removeClass('active');
  $(this).addClass('active');
  libraryFilter = $(this).data('cat') || '';
  loadLibraryList();
});
$('#btn-lib-step').click(() => libraryStepOnce());
$('#btn-lib-auto').click(() => startLibraryAuto());
$('#btn-lib-stop').click(() => stopLibraryAuto());
$('#btn-lib-ai').click(() => {
  if (online.active) return;
  $('#game-mode').val('ai_vs_ai');
  $('#with-analysis').prop('checked', false);
  autoDelayMs = FAST_STEP_DELAY_MS;
  refreshModeControls();
  startAuto();
});

function roomShareUrl(roomId) {
  const u = new URL(window.location.href);
  u.searchParams.set('room', roomId);
  return u.toString();
}

function saveOnlineSession() {
  if (!online.roomId || !online.token) return;
  localStorage.setItem(
    `chesscouncil_room_${online.roomId}`,
    JSON.stringify({ token: online.token, color: online.color, name: online.name })
  );
}

function loadOnlineSession(roomId) {
  try {
    return JSON.parse(localStorage.getItem(`chesscouncil_room_${roomId}`) || 'null');
  } catch (_) {
    return null;
  }
}

function updateOnlineChrome() {
  const bar = $('#online-bar');
  if (!online.active) {
    bar.removeClass('is-online');
    $('#online-status').text('本地模式 · 可开房间用手机互下');
    $('#btn-room-copy, #btn-room-leave').prop('hidden', true);
    $('#btn-room-create, #btn-room-join').prop('disabled', false);
    return;
  }
  bar.addClass('is-online');
  const colorLabel = online.color === 'white' ? '白' : '黑';
  $('#online-status').text(`房间 ${online.roomId} · 你执${colorLabel} · 已连接`);
  $('#online-room-code').val(online.roomId);
  $('#btn-room-copy, #btn-room-leave').prop('hidden', false);
}

function applyOnlineBoardState(state) {
  if (!state) return;
  serverState.mode = 'human_vs_human';
  serverState.controller = 'human';
  serverState.is_game_over = !!state.is_game_over;
  serverState.human_color = online.color || 'white';
  try {
    game.load(state.fen);
  } catch (_) {
    game.reset();
  }
  board.position(state.fen, false);
  orientation = online.color === 'black' ? 'black' : 'white';
  board.orientation(orientation);
  selectedSquare = null;
  clearHighlights();
  updateStatus();
  const seats = state.seats || {};
  const w = seats.white ? `${seats.white.name}${seats.white.connected ? '' : '(离线)'}` : '空位';
  const b = seats.black ? `${seats.black.name}${seats.black.connected ? '' : '(离线)'}` : '空位';
  $('#ai-meta').text(`联机 ${online.roomId} · 白:${w} · 黑:${b}`);
  if (state.is_game_over && state.result) {
    // 等 move 包带 finale；纯 state 时用客户端兜底
  }
}

function applyOnlineMovePayload(data) {
  const state = data.state || {};
  applyOnlineBoardState(state);
  const mv = data.move;
  if (mv && mv.uci && mv.uci.length >= 4) {
    markLastMove(mv.uci.slice(0, 2), mv.uci.slice(2, 4));
  }
  busy = false;
  if (state.is_game_over) {
    showFinale(data.finale || inferFinaleClient({ game_over: true, result: state.result }));
  }
}

async function syncOnlineState() {
  if (!online.roomId) return;
  const state = await fetch(`${API}/rooms/${online.roomId}`).then((r) => r.json());
  applyOnlineBoardState(state);
}

function disconnectOnlineWs() {
  if (online.reconnectTimer) {
    clearTimeout(online.reconnectTimer);
    online.reconnectTimer = null;
  }
  if (online.ws) {
    try {
      online.ws.close();
    } catch (_) {}
    online.ws = null;
  }
}

function connectOnlineWs() {
  disconnectOnlineWs();
  if (!online.roomId || !online.token) return;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(
    `${proto}://${location.host}/api/rooms/${online.roomId}/ws?token=${encodeURIComponent(online.token)}`
  );
  online.ws = ws;
  ws.onopen = () => {
    updateOnlineChrome();
    $('#online-status').text(`房间 ${online.roomId} · 实时已连接`);
  };
  ws.onmessage = (ev) => {
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch (_) {
      return;
    }
    if (msg.type === 'hello' || msg.type === 'state' || msg.type === 'peer') {
      applyOnlineBoardState(msg.state);
      return;
    }
    if (msg.type === 'move') {
      applyOnlineMovePayload(msg);
      return;
    }
    if (msg.type === 'reset') {
      hideFinale();
      clearLastMoveMarkers();
      applyOnlineBoardState(msg.state);
      return;
    }
    if (msg.type === 'error') {
      busy = false;
      $('#ai-meta').text(msg.message || '联机错误');
      syncOnlineState();
    }
  };
  ws.onclose = () => {
    if (!online.active) return;
    $('#online-status').text(`房间 ${online.roomId} · 连接断开，重连中…`);
    online.reconnectTimer = setTimeout(connectOnlineWs, 1200);
  };
}

async function enterOnlineRoom(session) {
  stopAuto();
  hideFinale();
  online.active = true;
  online.roomId = session.room_id;
  online.token = session.token;
  online.color = session.color;
  online.name = session.name || $('#online-name').val() || '玩家';
  saveOnlineSession();
  $('#game-mode').val('human_vs_human');
  refreshModeControls();
  applyOnlineBoardState(session.state);
  updateOnlineChrome();
  connectOnlineWs();
  // 更新地址栏方便分享
  const u = new URL(window.location.href);
  u.searchParams.set('room', online.roomId);
  history.replaceState(null, '', u.toString());
}

function leaveOnlineRoom() {
  online.active = false;
  disconnectOnlineWs();
  online.roomId = null;
  online.token = null;
  online.color = null;
  updateOnlineChrome();
  const u = new URL(window.location.href);
  u.searchParams.delete('room');
  history.replaceState(null, '', u.toString());
  startNewGame();
}

async function joinRoomByCode(code, name) {
  code = (code || '').trim().toUpperCase();
  name = (name || $('#online-name').val() || '玩家').trim();
  if (!code) {
    alert('请输入房间码');
    return false;
  }
  const cached = loadOnlineSession(code);
  if (cached && cached.token) {
    try {
      const state = await fetch(`${API}/rooms/${code}`).then((r) => {
        if (!r.ok) throw new Error('gone');
        return r.json();
      });
      await enterOnlineRoom({
        room_id: code,
        token: cached.token,
        color: cached.color,
        name: cached.name || name,
        state,
      });
      return true;
    } catch (_) {
      /* fallthrough */
    }
  }
  const r = await fetch(`${API}/rooms/${code}/join`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  const data = await r.json();
  if (!r.ok) {
    alert(typeof data.detail === 'string' ? data.detail : '加入失败');
    return false;
  }
  await enterOnlineRoom(data);
  return true;
}

$('#btn-room-create').click(async () => {
  const name = ($('#online-name').val() || '玩家').trim();
  const r = await fetch(`${API}/rooms`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, color: 'white' }),
  });
  const data = await r.json();
  if (!r.ok) {
    alert(data.detail || '创建失败');
    return;
  }
  await enterOnlineRoom(data);
  alert(`房间 ${data.room_id} 已创建。点「复制链接」发给对手。`);
});

$('#btn-room-join').click(async () => {
  await joinRoomByCode($('#online-room-code').val());
});

$('#btn-room-copy').click(async () => {
  if (!online.roomId) return;
  const link = roomShareUrl(online.roomId);
  try {
    await navigator.clipboard.writeText(link);
    $('#ai-meta').text('房间链接已复制');
  } catch (_) {
    prompt('复制房间链接', link);
  }
});

$('#btn-room-leave').click(() => leaveOnlineRoom());

$(document).ready(async () => {
  initBoard();
  $(window).on('resize', () => {
    if (lastMoveFrom && lastMoveTo) paintLastMoveMarkers();
  });

  const roomParam = new URLSearchParams(location.search).get('room');
  if (roomParam) {
    $('#online-room-code').val(roomParam.toUpperCase());
    const ok = await joinRoomByCode(roomParam);
    if (!ok) await startNewGame();
  } else {
    await startNewGame();
  }

  await loadDemos();
  await loadLibraryList();
  refreshHistory();
  try {
    const h = await fetch(`${API}/health`).then(r => r.json());
    $('#llm-status').text(
      `模型：${h.llm_model || '?'} · ${h.llm_enabled ? '已启用' : '未配置 Key'} · 引擎${h.stockfish ? '就绪' : '降级'}`
    );
    if (!h.stockfish && h.stockfish_error) {
      $('#ai-meta').text('Stockfish 未连接（已降级）：' + h.stockfish_error);
    }
  } catch (_) {
    $('#llm-status').text('无法连接后端 /api/health');
  }
});
