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

/** 残局闯关 */
const CHALLENGE_STORAGE_KEY = 'cc_challenge_cleared_v1';
let challengeState = {
  active: false,
  level: null,
  id: null,
  title: '',
  goal: '',
  humanColor: 'white',
};
let challengeLevelsCache = [];

/** 本局着法回放（机机象棋式着法列表） */
const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
let plyLog = []; // {number,san,uci,fen,classification?}
let viewPly = 0; // 0=开局，n=第 n 步后
let browsingHistory = false;

const PIECE_GLYPH = {
  K: '♔', Q: '♕', R: '♖', B: '♗', N: '♘', P: '♙',
  k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟',
  '': '空',
};

const COUNCIL_STAGES = [
  '战术分析师出牌…',
  '战略分析师出牌…',
  '风险审查员挑刺…',
  '比对分歧…',
  '教练翻译结论…',
];

function setProgress(msg, { cycleCouncil = false } = {}) {
  if (!msg) {
    $('#council-progress').prop('hidden', true);
    if (progressTimer) {
      clearInterval(progressTimer);
      progressTimer = null;
    }
    return;
  }
  const started = Date.now();
  let stageIdx = 0;
  $('#council-progress').prop('hidden', false);
  const tick = () => {
    const s = Math.round((Date.now() - started) / 1000);
    if (cycleCouncil) {
      stageIdx = Math.min(COUNCIL_STAGES.length - 1, Math.floor(s / 2));
      $('#council-progress-text').text(`${COUNCIL_STAGES[stageIdx]}（${s}s）`);
      markAgentThinking(stageIdx);
    } else {
      $('#council-progress-text').text(`${msg}（${s}s）`);
    }
  };
  tick();
  if (progressTimer) clearInterval(progressTimer);
  progressTimer = setInterval(tick, 500);
}

function markAgentThinking(stageIdx) {
  const roles = ['tactical', 'strategic', 'risk'];
  roles.forEach((role, i) => {
    const card = $(`.dg-card[data-role="${role}"]`);
    card.removeClass('is-thinking is-ready is-dissent is-agree');
    if (i < stageIdx) {
      card.addClass('is-ready');
      $(`#dg-state-${role}`).text('已发言');
    } else if (i === stageIdx && stageIdx < 3) {
      card.addClass('is-thinking');
      $(`#dg-state-${role}`).text('思考中…');
      $(`#dg-move-${role}`).text('…');
    } else if (stageIdx < 3) {
      $(`#dg-state-${role}`).text('排队');
    }
  });
}

function firstSentence(text) {
  if (!text) return '';
  const cleaned = String(text).replace(/\s+/g, ' ').trim();
  const m = cleaned.match(/^(.+?[。！？.!?]|.+$)/);
  const s = (m ? m[1] : cleaned).trim();
  return s.length > 90 ? `${s.slice(0, 88)}…` : s;
}

function showCoachTakeaway(council) {
  const coach = council?.agents?.coach;
  const verdict = council?.verdict;
  const line =
    firstSentence(coach?.summary) ||
    firstSentence(verdict?.summary) ||
    (verdict?.recommended_move ? `理事会倾向 ${verdict.recommended_move}` : '');
  if (!line) {
    $('#coach-takeaway').prop('hidden', true);
    return;
  }
  $('#coach-takeaway-text').text(line);
  $('#coach-takeaway').prop('hidden', false);
}

function resetAgentCompare() {
  ['tactical', 'strategic', 'risk'].forEach((role) => {
    const card = $(`.dg-card[data-role="${role}"]`);
    card.removeClass('is-thinking is-ready is-dissent is-agree');
    $(`#dg-move-${role}`).text('—');
    $(`#dg-state-${role}`).text('待命');
  });
  $('#coach-takeaway').prop('hidden', true);
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
  if (browsingHistory) return false;
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

function syncPlyLogFromMoves(moves) {
  plyLog = (moves || []).map((m) => ({
    number: m.number,
    san: m.san,
    uci: m.uci,
    fen: m.fen,
    classification: m.classification || null,
  }));
  viewPly = plyLog.length;
  browsingHistory = false;
  renderMoveList();
  updatePlyNavLabel();
}

function appendPlyFromMove(data) {
  const move = data && data.move;
  if (!move || !move.uci || move.uci.length < 4) return;
  const cls = (data.evaluation && data.evaluation.classification) || null;
  plyLog.push({
    number: move.number || plyLog.length + 1,
    san: move.san,
    uci: move.uci,
    fen: data.fen,
    classification: cls,
  });
  viewPly = plyLog.length;
  browsingHistory = false;
  renderMoveList();
  updatePlyNavLabel();
}

function renderMoveList() {
  const box = $('#move-list');
  if (!box.length) return;
  if (!plyLog.length) {
    box.html('<span class="move-list-empty">尚无着法</span>');
    return;
  }
  let html = '';
  for (let i = 0; i < plyLog.length; i += 2) {
    const w = plyLog[i];
    const b = plyLog[i + 1];
    const round = Math.floor(i / 2) + 1;
    html += `<span class="move-round">${round}.</span>`;
    html += plyChip(w, i + 1);
    if (b) html += plyChip(b, i + 2);
  }
  box.html(html);
}

function plyChip(entry, plyIndex) {
  const active = viewPly === plyIndex ? ' is-active' : '';
  const cls = entry.classification ? ` cls-${escapeHtml(entry.classification)}` : '';
  return `<button type="button" class="move-ply${active}${cls}" data-ply="${plyIndex}">${escapeHtml(entry.san)}</button>`;
}

function updatePlyNavLabel() {
  const label = $('#ply-nav-label');
  if (!label.length) return;
  if (viewPly <= 0) {
    label.text(browsingHistory ? '回放 · 开局' : '开局');
  } else {
    const m = plyLog[viewPly - 1];
    label.text(
      (browsingHistory ? '回放 · ' : '') +
        `第${viewPly}步 ${m ? m.san : ''}`
    );
  }
}

function gotoPly(ply, { fromBrowse = true } = {}) {
  const max = plyLog.length;
  const target = Math.max(0, Math.min(max, ply));
  viewPly = target;
  browsingHistory = fromBrowse && target < max;
  const fen = target === 0 ? START_FEN : (plyLog[target - 1] && plyLog[target - 1].fen);
  if (!fen) return;
  game.load(fen);
  board.position(fen, false);
  selectedSquare = null;
  clearHighlights();
  if (target > 0) {
    const m = plyLog[target - 1];
    if (m && m.uci && m.uci.length >= 4) {
      markLastMove(m.uci.slice(0, 2), m.uci.slice(2, 4));
    }
  } else {
    lastMoveFrom = null;
    lastMoveTo = null;
    paintLastMoveMarkers();
  }
  renderMoveList();
  updatePlyNavLabel();
  if (browsingHistory) {
    $('#ai-meta').text('回放中 · 点「|&gt;」回到最新后再走棋');
  }
  updateStatus();
}

function jumpToFen(fen, meta) {
  if (meta && meta.ply === 0) {
    gotoPly(0);
    return;
  }
  if (fen && (fen === START_FEN || fen.startsWith('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR'))) {
    gotoPly(0);
    return;
  }
  if (fen) {
    const idx = plyLog.findIndex((m) => m.fen === fen);
    if (idx >= 0) {
      gotoPly(idx + 1);
      return;
    }
  }
  if (meta && meta.ply != null) {
    const byNum = plyLog.findIndex((m) => m.number === meta.ply);
    if (byNum >= 0) {
      gotoPly(byNum + 1);
      return;
    }
  }
  if (!fen) return;
  game.load(fen);
  board.position(fen, false);
  browsingHistory = true;
  selectedSquare = null;
  clearHighlights();
  $('#ai-meta').text(
    meta && meta.san
      ? `复盘跳转 · ${meta.san}（白优 ${meta.advantage > 0 ? '+' : ''}${meta.advantage}%）`
      : '复盘跳转'
  );
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
  clearHintHighlights();
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

    const useCouncil = $('#with-analysis').is(':checked');
    // 人人局：对局中不跑 AI 评价，终局后统一生成
    const h2h = serverState.mode === 'human_vs_human';
    const blockOnCouncil = useCouncil && !h2h;
    if (blockOnCouncil) setProgress('Council 开会中', { cycleCouncil: true });
    const analysisMode = $('#analysis-mode').val() || 'fast';
    const r = await fetch(`${API}/game/move`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        uci,
        with_analysis: blockOnCouncil,
        analysis_mode: analysisMode,
      }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      console.error('走子被服务器拒绝:', data);
      $('#game-status').text('走子失败，已与服务器棋局同步');
      await syncFromServer();
      return;
    }
    applyMoveResult(data);
    if (h2h && data.game_over) {
      await runPostGameReview();
    }
    if (!data.game_over && data.next_controller && data.next_controller !== 'human') {
      await sleep(400);
      await runAiStep({ nested: true });
    }
  } catch (err) {
    console.error('分析请求失败:', err);
  } finally {
    setProgress(null);
    busy = false;
  }
}

let analysisGen = 0;

async function runPostGameReview() {
  const gen = ++analysisGen;
  setProgress('终局复盘生成中…', { cycleCouncil: true });
  $('#move-class').text('对局结束 · 正在生成统一评价');
  $('#ai-meta').text('人人局终局复盘生成中…');
  try {
    const r = await fetch(`${API}/game/post-review`, { method: 'POST' });
    const data = await r.json().catch(() => ({}));
    if (gen !== analysisGen) return;
    if (!r.ok) {
      $('#ai-meta').text(apiErrorText(data, '终局复盘失败'));
      return;
    }
    const final = data.final_analysis || {};
    applyMoveResult({
      ...final,
      game_over: true,
      result: data.result || final.result,
      move: { san: '终局复盘', uci: '', number: 0 },
      skip_finale: true,
    });
    $('#ai-meta').text('人人局 · 终局评价已生成');
    $('#move-class').text(data.result || '对局结束 · 复盘就绪');
    // 打开复盘面板
    try {
      await showReviewFromData(data.review);
    } catch (_) {
      $('#btn-review').click();
    }
  } catch (err) {
    console.error(err);
    if (gen === analysisGen) $('#ai-meta').text('终局复盘请求失败');
  } finally {
    if (gen === analysisGen) setProgress(null);
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
  syncPlyLogFromMoves(state.moves);
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
  appendPlyFromMove(data);
  if (data.game_over) {
    stopAuto();
    if (!data.skip_finale) {
      showFinale(data.finale || inferFinaleClient(data));
    }
    maybeCompleteChallenge(data);
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
  $('.square-55d63').removeClass(
    'highlight-selected highlight-move highlight-capture highlight-hint highlight-hint-to'
  );
  // 选中高亮清掉后，把上一步标记画回去
  paintLastMoveMarkers();
}

function clearHintHighlights() {
  $('.square-55d63').removeClass('highlight-hint highlight-hint-to');
}

function showHintSquares(from, to) {
  clearHintHighlights();
  if (from) $(`.square-55d63[data-square="${from}"]`).addClass('highlight-hint');
  if (to) $(`.square-55d63[data-square="${to}"]`).addClass('highlight-hint-to');
}

function apiErrorText(data, fallback) {
  const d = data && data.detail;
  if (typeof d === 'string') return d;
  if (d && typeof d === 'object' && d.error) return d.error;
  if (data && data.error) return data.error;
  return fallback;
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
    $('#dg-label').text('等待你的着法…');
    resetAgentCompare();
    return;
  }
  const dg = council.disagreement;
  const pct = Math.round((dg.disagreement_score || 0) * 100);
  $('#dg-fill').css('width', pct + '%');
  const debateOn = !!(council.debate && council.debate.triggered);
  $('#dg-label').text(
    `${dg.badge || ''} · 争议 ${pct}%` + (debateOn ? ' · 已开辩论' : '')
  );

  const rm = dg.recommended_moves || {};
  const moves = {
    tactical: rm.tactical || council.agents?.tactical?.recommended_move || '—',
    strategic: rm.strategic || council.agents?.strategic?.recommended_move || '—',
    risk: rm.risk || council.agents?.risk?.recommended_move || '—',
  };
  const unique = new Set(Object.values(moves).filter((m) => m && m !== '—'));
  const dissent = unique.size > 1;

  Object.entries(moves).forEach(([role, move]) => {
    const card = $(`.dg-card[data-role="${role}"]`);
    card.removeClass('is-thinking is-ready is-dissent is-agree');
    $(`#dg-move-${role}`).text(move);
    if (dissent && move !== '—') {
      const agreesWithMost =
        [...unique].filter((m) => Object.values(moves).filter((x) => x === m).length >= 2)[0];
      if (agreesWithMost && move === agreesWithMost) {
        card.addClass('is-agree');
        $(`#dg-state-${role}`).text('多数意见');
      } else {
        card.addClass('is-dissent');
        $(`#dg-state-${role}`).text('唱反调');
      }
    } else {
      card.addClass('is-ready');
      $(`#dg-state-${role}`).text(move === '—' ? '无推荐' : '一致');
    }
  });
}

let revealTimers = [];

function clearRevealTimers() {
  revealTimers.forEach((t) => clearTimeout(t));
  revealTimers = [];
}

function revealCouncilTabs(council) {
  clearRevealTimers();
  const sequence = [
    ['tactical', () => $('#tab-tactical').html(renderOpinion(council.agents.tactical, '战术'))],
    ['strategic', () => $('#tab-strategic').html(renderOpinion(council.agents.strategic, '战略'))],
    ['risk', () => $('#tab-risk').html(renderOpinion(council.agents.risk, '风险'))],
    ['debate', () => $('#tab-debate').html(renderDebate(council))],
    ['summary', () => {
      $('#tab-summary').html(renderOpinion(council.agents.coach, '教练'));
      showCoachTakeaway(council);
      // 有辩论时自动切到辩论 Tab 一眼看见吵架
      if (council.debate?.triggered) {
        $('.tab').removeClass('active');
        $('.tab-content').removeClass('active');
        $('.tab[data-tab="debate"]').addClass('active');
        $('#tab-debate').addClass('active is-revealing');
      } else {
        $('.tab').removeClass('active');
        $('.tab-content').removeClass('active');
        $('.tab[data-tab="summary"]').addClass('active');
        $('#tab-summary').addClass('active is-revealing');
      }
    }],
  ];

  $('#tab-tactical, #tab-strategic, #tab-risk, #tab-debate, #tab-summary').html(
    '<p class="placeholder">Council 正在入座…</p>'
  );

  sequence.forEach(([tab, fn], i) => {
    revealTimers.push(setTimeout(() => {
      fn();
      const el = $(`#tab-${tab}`);
      el.addClass('is-revealing');
      setTimeout(() => el.removeClass('is-revealing'), 450);
    }, 180 + i * 220));
  });
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
    revealCouncilTabs(council);
  } else {
    clearRevealTimers();
    $('#coach-takeaway').prop('hidden', true);
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
  const humanField = $('#human-color').closest('.field');
  const whiteAiField = $('#white-ai').closest('.field');
  const councilField = $('#with-analysis').closest('.field');
  const analysisModeField = $('#analysis-mode-field');
  $('#human-color').prop('disabled', mode !== 'human_vs_ai');
  $('#white-ai').prop('disabled', mode !== 'ai_vs_ai');
  // PC 上隐藏无关控件，避免功能栏显得错乱
  if (mode === 'human_vs_ai') {
    humanField.removeAttr('hidden');
    whiteAiField.attr('hidden', true);
    councilField.removeAttr('hidden');
    analysisModeField.removeAttr('hidden');
    $('#with-analysis').prop('disabled', false);
  } else if (mode === 'ai_vs_ai') {
    humanField.attr('hidden', true);
    whiteAiField.removeAttr('hidden');
    councilField.removeAttr('hidden');
    analysisModeField.removeAttr('hidden');
    $('#with-analysis').prop('disabled', false);
  } else {
    // 人人局：对局中不实时 Council，终局统一生成
    humanField.attr('hidden', true);
    whiteAiField.attr('hidden', true);
    councilField.attr('hidden', true);
    analysisModeField.attr('hidden', true);
    $('#ai-meta').text('人人局 · 对局中不实时评价，结束后统一生成复盘');
  }
}

function newGamePayload() {
  const mode = $('#game-mode').val();
  return {
    mode,
    human_color: $('#human-color').val(),
    white_ai: $('#white-ai').val(),
    engine_depth: parseInt($('#engine-depth').val(), 10),
    // 人人局永不实时 Council
    with_analysis: mode === 'human_vs_human' ? false : $('#with-analysis').is(':checked'),
    analysis_mode: $('#analysis-mode').val() || 'fast',
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
  clearRevealTimers();
  resetAgentCompare();
  $('#move-class').text('你走一步，理事会就开会').attr('class', 'move-class');
  $('#eval-white, #eval-black').css('height', '50%');
  $('#white-prob').text('白方 50%');
  $('#black-prob').text('黑方 50%');
  $('.tab-content').html('<p class="placeholder">对局进行中…</p>');
  $('#tab-summary').addClass('active');
  $('#ai-meta').text('人 vs AI · 走棋后看 Council 怎么吵');
  plyLog = [];
  viewPly = 0;
  browsingHistory = false;
  renderMoveList();
  updatePlyNavLabel();
  analysisGen += 1;
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
      await runAiStep({ nested: true });
    }
  } finally {
    busy = false;
  }
}

async function runAiStep(opts = {}) {
  const nested = !!opts.nested;
  if (busy && !autoPlay && !nested) return;
  if (serverState.is_game_over) return;
  if (serverState.controller === 'human') return;

  busy = true;
  const useCouncil = $('#with-analysis').is(':checked');
  $('#game-status').text(useCouncil ? 'AI + Council…' : 'AI 思考中…');
  if (useCouncil) setProgress('AI 走子与 Council 开会', { cycleCouncil: true });
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
    if (!nested) busy = false;
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
$('#btn-ply-start').click(() => gotoPly(0));
$('#btn-ply-prev').click(() => gotoPly(viewPly - 1));
$('#btn-ply-next').click(() => gotoPly(viewPly + 1));
$('#btn-ply-end').click(() => gotoPly(plyLog.length));
$(document).on('click', '.move-ply', function () {
  const ply = parseInt($(this).attr('data-ply'), 10);
  if (!Number.isNaN(ply)) gotoPly(ply);
});
$(document).on('keydown', (e) => {
  if (e.target && /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
  if (e.key === 'ArrowLeft') {
    e.preventDefault();
    gotoPly(viewPly - 1);
  } else if (e.key === 'ArrowRight') {
    e.preventDefault();
    gotoPly(viewPly + 1);
  }
});
$('#btn-undo').click(async () => {
  if (busy || online.active) return;
  analysisGen += 1;
  setProgress(null);
  busy = true;
  clearHintHighlights();
  try {
    const r = await fetch(`${API}/game/undo`, { method: 'POST' });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      $('#ai-meta').text(apiErrorText(data, '无法悔棋'));
      return;
    }
    applyServerState(data);
    game.load(data.fen);
    board.position(data.fen, false);
    selectedSquare = null;
    clearHighlights();
    syncPlyLogFromMoves(data.moves);
    const hist = game.history({ verbose: true });
    if (hist.length) {
      const last = hist[hist.length - 1];
      markLastMove(last.from, last.to);
    } else {
      lastMoveFrom = null;
      lastMoveTo = null;
      paintLastMoveMarkers();
    }
    updateStatus();
    $('#ai-meta').text(
      serverState.mode === 'human_vs_ai'
        ? '已悔棋 · 回到你的回合'
        : '已悔棋'
    );
    $('#move-class').text('悔棋完成');
    resetAgentCompare();
  } catch (err) {
    console.error(err);
  } finally {
    busy = false;
  }
});
$('#btn-hint').click(async () => {
  if (busy || online.active || serverState.is_game_over) return;
  if (!humanMayMove() && serverState.mode !== 'human_vs_human') {
    $('#ai-meta').text('当前不是你的回合');
    return;
  }
  busy = true;
  $('#ai-meta').text('引擎算提示…');
  try {
    const r = await fetch(`${API}/game/hint`, { method: 'POST' });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      $('#ai-meta').text(apiErrorText(data, '提示失败'));
      return;
    }
    showHintSquares(data.from, data.to);
    $('#ai-meta').text(`提示 ${data.san}（${data.uci} · 引擎 depth ${data.depth}）`);
    $('#move-class').text(`引擎提示：${data.san}`);
  } catch (err) {
    console.error(err);
    $('#ai-meta').text('提示请求失败');
  } finally {
    busy = false;
  }
});
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
    await showReviewFromData(data);
  } catch (e) {
    alert('复盘请求失败');
  }
});

async function showReviewFromData(data) {
  if (!data) return;
  const narr = (data.narrative || []).map(t => `<li>${escapeHtml(t)}</li>`).join('');
  const highs = (data.highlights || []).map(h =>
    `<li>第${escapeHtml(String(h.number))}步 ${escapeHtml(h.san)} · ${escapeHtml(h.classification)} · 争议 ${Math.round((h.disagreement_score || 0) * 100)}%</li>`
  ).join('');
  const debates = (data.debates || []).map(d =>
    `<li>第${escapeHtml(String(d.number))}步 ${escapeHtml(d.san)} → 仲裁 ${escapeHtml(d.verdict || '—')}</li>`
  ).join('');
  switchWorkspace('more');
  $('#review-section').show();
  const reviewEl = document.getElementById('review-section');
  if (reviewEl) reviewEl.open = true;
  $('#review-result').html(`
    <div class="review-block">
      <p><strong>${escapeHtml(data.title || '复盘')}</strong> · 共 ${data.total_moves} 步 · 辩论 ${data.debate_count || 0} 次 · 平均争议 ${Math.round((data.avg_disagreement || 0) * 100)}%</p>
      ${renderAccuracyCard(data.accuracy)}
      ${renderEvalCurveChart(data.eval_curve || [])}
      <p><strong>叙事</strong></p><ul>${narr || '<li>暂无</li>'}</ul>
      <p><strong>关键局面</strong></p><ul>${highs || '<li>暂无</li>'}</ul>
      <p><strong>辩论回合</strong></p><ul>${debates || '<li>本局未触发辩论</li>'}</ul>
      <pre style="white-space:pre-wrap;font-size:0.78rem;opacity:0.8">${escapeHtml(data.pgn || '')}</pre>
    </div>`);
  reviewEl?.scrollIntoView({ behavior: 'smooth' });
}

function renderAccuracyCard(acc) {
  if (!acc || acc.overall == null) {
    return `<div class="accuracy-empty">暂无准确率（需有引擎走子分类）</div>`;
  }
  const ring = Math.max(0, Math.min(100, acc.overall));
  const white = acc.white != null ? `${acc.white}%` : '—';
  const black = acc.black != null ? `${acc.black}%` : '—';
  return `
    <div class="accuracy-panel">
      <div class="accuracy-score" aria-label="总准确率 ${ring}%">
        <span class="accuracy-num">${ring}</span>
        <span class="accuracy-unit">%</span>
      </div>
      <div class="accuracy-copy">
        <strong>准确率</strong>
        <span>白方 ${escapeHtml(String(white))} · 黑方 ${escapeHtml(String(black))}</span>
        <span class="accuracy-note">${escapeHtml(acc.note || '')}</span>
      </div>
    </div>`;
}

function renderEvalCurveChart(curve) {
  if (!curve || curve.length < 2) {
    return `<div class="eval-curve-empty">本局尚无逐步胜率曲线（终局复盘后生成）</div>`;
  }
  const W = 640;
  const H = 220;
  const pad = { l: 44, r: 16, t: 18, b: 28 };
  const plotW = W - pad.l - pad.r;
  const plotH = H - pad.t - pad.b;
  const n = curve.length;
  const maxAbs = Math.max(20, ...curve.map((p) => Math.abs(Number(p.advantage) || 0)));
  const yScale = (adv) => pad.t + plotH / 2 - (Number(adv) / maxAbs) * (plotH / 2);
  const xScale = (i) => pad.l + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const pts = curve.map((p, i) => `${xScale(i).toFixed(1)},${yScale(p.advantage).toFixed(1)}`);
  const line = pts.join(' ');
  const zeroY = yScale(0);
  // 零线上下分区填充
  const areaWhite = [`${xScale(0)},${zeroY}`, ...pts, `${xScale(n - 1)},${zeroY}`].join(' ');
  const last = curve[curve.length - 1];
  const tip = last.advantage >= 0
    ? `终局白方优势 +${Math.abs(last.advantage).toFixed(1)}%`
    : `终局黑方优势 +${Math.abs(last.advantage).toFixed(1)}%`;

  const dots = curve.map((p, i) => {
    const cx = xScale(i);
    const cy = yScale(p.advantage);
    const title = `第${p.ply}步 ${p.san || ''} · 白 ${p.white_win}% / 黑 ${p.black_win}%（点击跳转）`;
    const fenAttr = p.fen ? ` data-fen="${escapeHtml(p.fen)}"` : '';
    return `<circle class="eval-dot" cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="4.5" data-ply="${escapeHtml(String(p.ply))}" data-san="${escapeHtml(p.san || '')}" data-adv="${escapeHtml(String(p.advantage))}"${fenAttr} style="cursor:pointer"><title>${escapeHtml(title)}</title></circle>`;
  }).join('');

  return `
    <div class="eval-curve-panel">
      <div class="eval-curve-head">
        <strong>胜率走势</strong>
        <span>关键节点连线 · 点圆点跳转局面 · ${escapeHtml(tip)}</span>
      </div>
      <svg class="eval-curve-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="白黑胜率折线图">
        <defs>
          <linearGradient id="evalFillWhite" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="rgba(239,231,216,0.35)"/>
            <stop offset="100%" stop-color="rgba(239,231,216,0)"/>
          </linearGradient>
          <linearGradient id="evalFillBlack" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stop-color="rgba(107,124,116,0.4)"/>
            <stop offset="100%" stop-color="rgba(107,124,116,0)"/>
          </linearGradient>
        </defs>
        <rect x="${pad.l}" y="${pad.t}" width="${plotW}" height="${plotH}" class="eval-plot-bg"/>
        <line x1="${pad.l}" y1="${zeroY}" x2="${W - pad.r}" y2="${zeroY}" class="eval-zero"/>
        <text x="${pad.l - 8}" y="${pad.t + 10}" class="eval-axis-label" text-anchor="end">白</text>
        <text x="${pad.l - 8}" y="${pad.t + plotH}" class="eval-axis-label" text-anchor="end">黑</text>
        <polyline class="eval-area-guide" points="${areaWhite}" fill="url(#evalFillWhite)" stroke="none"/>
        <polyline class="eval-line" points="${line}" fill="none"/>
        ${dots}
        <text x="${pad.l}" y="${H - 8}" class="eval-axis-label">开局</text>
        <text x="${W - pad.r}" y="${H - 8}" class="eval-axis-label" text-anchor="end">第${escapeHtml(String(last.ply))}步</text>
      </svg>
    </div>`;
}

$(document).on('click', '.eval-dot', function () {
  const fen = $(this).attr('data-fen') || null;
  const ply = parseInt($(this).attr('data-ply'), 10);
  const san = $(this).attr('data-san');
  const advantage = parseFloat($(this).attr('data-adv'));
  jumpToFen(fen, {
    ply: Number.isNaN(ply) ? null : ply,
    san,
    advantage: Number.isNaN(advantage) ? 0 : advantage,
  });
  // 跳转后滚回棋盘
  document.getElementById('board')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
});

async function openPitchReviewAndLogs() {
  switchWorkspace('more');
  $('#btn-review').click();
  const logsEl = document.getElementById('logs-section');
  if (logsEl) logsEl.open = true;
  refreshLogs();
}

function showPitchCue(html) {
  const el = $('#pitch-cue');
  el.html(html).prop('hidden', false);
}

async function runDemoById(demoId, title) {
  if (busy) return;
  busy = true;
  stopAuto();
  $('#pitch-cue').prop('hidden', true);
  setProgress(`路演 Council：${title || demoId}`, { cycleCouncil: true });
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
      showPitchCue(
        '<strong>路演下一步：</strong>已打开复盘与调用证明。然后到「对弈设置 → 高级选项 → 快速 AI 对战」演示算法对抗。'
      );
      await openPitchReviewAndLogs();
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

function switchWorkspace(panelId) {
  $('.ws-tab').removeClass('active').attr('aria-selected', 'false');
  $(`.ws-tab[data-panel="${panelId}"]`).addClass('active').attr('aria-selected', 'true');
  $('.ws-panel').each(function () {
    this.hidden = true;
  });
  const panel = document.getElementById(`panel-${panelId}`);
  if (panel) panel.hidden = false;
  // 棋盘占满首屏时，分区在折线下；不滚动会像「点不开」
  const nav = document.querySelector('.workspace-nav');
  const target = panel || nav;
  if (target) {
    requestAnimationFrame(() => {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }
  if (panelId === 'learn') {
    if ($('.learn-mode-tab.active').attr('data-learn') === 'challenge') {
      loadChallengeList();
    } else {
      loadLibraryList();
    }
  }
}

$(document).on('click', '.ws-tab', function (e) {
  e.preventDefault();
  const panel = $(this).attr('data-panel') || $(this).data('panel');
  if (panel) switchWorkspace(panel);
});

$('#btn-show-logs').click(() => {
  switchWorkspace('more');
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
    const r = await fetch(`${API}/library${qs}`);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      box.html(
        `<div class="history-empty">学习库接口不可用（${r.status} · ${API}/library）。请打开 http://127.0.0.1:8000/ 并用最新后端，勿用旧端口。</div>`
      );
      return;
    }
    const items = data.items || [];
    if (!items.length) {
      box.html('<div class="history-empty">暂无条目</div>');
      return;
    }
    box.empty();
    items.forEach((it) => {
      const el = $('<article class="lib-item"></article>');
      el.append(
        `<div class="lib-item-top">` +
          `<div class="lib-item-title">${escapeHtml(it.title)}</div>` +
          `<span class="lib-item-badge">${escapeHtml(it.category_label || it.category)}</span>` +
          `</div>`
      );
      el.append(
        `<div class="meta">` +
          (it.year ? `${it.year} · ` : '') +
          (it.players ? `${escapeHtml(it.players)} · ` : '') +
          (it.has_script ? `${it.move_count} 步名谱` : '局面体验') +
          (it.goal ? ` · 目标：${escapeHtml(it.goal)}` : '') +
          `</div>`
      );
      if (it.blurb) {
        el.append(`<div class="blurb">${escapeHtml(it.blurb)}</div>`);
      }
      const row = $('<div class="row"></div>');
      row.append(
        $('<button type="button">加载</button>').on('click', () => {
          clearChallenge();
          loadLibraryItem(it.id, { mode: 'human_vs_human' });
        })
      );
      if (it.has_script) {
        row.append(
          $('<button type="button" class="accent">演示</button>').on('click', async () => {
            clearChallenge();
            await loadLibraryItem(it.id, { mode: 'human_vs_human' });
            startLibraryAuto();
          })
        );
      }
      row.append(
        $('<button type="button">AI 代下</button>').on('click', () => {
          clearChallenge();
          loadLibraryItem(it.id, { forAi: true });
        })
      );
      if (it.tags && it.tags.includes('debate')) {
        row.append(
          $('<button type="button">Council</button>').on('click', async () => {
            clearChallenge();
            await loadLibraryItem(it.id, { mode: 'human_vs_human' });
            $('#btn-analyze-pos').click();
          })
        );
      }
      el.append(row);
      box.append(el);
    });
  } catch (err) {
    console.error(err);
    box.html('<div class="history-empty">学习库加载失败，请确认服务已重启到最新代码</div>');
  }
}

function getClearedChallenges() {
  try {
    const raw = localStorage.getItem(CHALLENGE_STORAGE_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? arr : [];
  } catch (_) {
    return [];
  }
}

function markChallengeCleared(id) {
  const set = new Set(getClearedChallenges());
  set.add(id);
  localStorage.setItem(CHALLENGE_STORAGE_KEY, JSON.stringify([...set]));
}

function clearChallenge() {
  challengeState = {
    active: false,
    level: null,
    id: null,
    title: '',
    goal: '',
    humanColor: 'white',
  };
  $('#challenge-hud').prop('hidden', true).text('');
}

function updateChallengeHud() {
  if (!challengeState.active) {
    $('#challenge-hud').prop('hidden', true);
    return;
  }
  $('#challenge-hud')
    .prop('hidden', false)
    .html(
      `<strong>闯关 ${challengeState.level}</strong> · ${escapeHtml(challengeState.title)}` +
        ` · 目标：${escapeHtml(challengeState.goal)}` +
        ` <button type="button" id="btn-challenge-quit" class="linkish">退出闯关</button>`
    );
}

function maybeCompleteChallenge(data) {
  if (!challengeState.active || !data || !data.game_over) return;
  const result = String(data.result || '');
  const human = challengeState.humanColor;
  const whiteWin = result.includes('白方');
  const blackWin = result.includes('黑方');
  const draw = result.includes('和棋') || result.includes('逼和');
  let ok = false;
  if (challengeState.goal && challengeState.goal.includes('守和')) {
    ok = draw;
  } else if (human === 'white') {
    ok = whiteWin;
  } else {
    ok = blackWin;
  }
  if (!ok) {
    $('#ai-meta').text(`闯关未过 · ${result || '再试一次'}`);
    return;
  }
  markChallengeCleared(challengeState.id);
  $('#ai-meta').text(`闯关成功！第 ${challengeState.level} 关已通关`);
  $('#move-class').text('通关');
  renderChallengeList();
  const next = (challengeLevelsCache || []).find((lv) => lv.level === challengeState.level + 1);
  if (next) {
    setTimeout(() => {
      if (confirm(`第 ${challengeState.level} 关通关！进入第 ${next.level} 关？`)) {
        startChallengeLevel(next);
      } else {
        clearChallenge();
      }
    }, 400);
  } else {
    clearChallenge();
    alert('全部关卡已通关！');
  }
}

async function loadChallengeList() {
  const box = $('#challenge-list');
  try {
    const r = await fetch(`${API}/challenges`);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      box.html(`<div class="history-empty">闯关接口不可用（${r.status}）</div>`);
      return;
    }
    challengeLevelsCache = data.levels || [];
    renderChallengeList();
  } catch (err) {
    console.error(err);
    box.html('<div class="history-empty">闯关列表加载失败</div>');
  }
}

function renderChallengeList() {
  const box = $('#challenge-list');
  const cleared = new Set(getClearedChallenges());
  const levels = challengeLevelsCache || [];
  if (!levels.length) {
    box.html('<div class="history-empty">暂无关卡</div>');
    return;
  }
  box.empty();
  levels.forEach((lv, idx) => {
    const prevId = idx > 0 ? levels[idx - 1].id : null;
    const unlocked = idx === 0 || cleared.has(prevId) || cleared.has(lv.id);
    const done = cleared.has(lv.id);
    const stars = '★'.repeat(lv.difficulty || 1) + '☆'.repeat(Math.max(0, 3 - (lv.difficulty || 1)));
    const el = $('<article class="challenge-item"></article>');
    if (!unlocked) el.addClass('is-locked');
    if (done) el.addClass('is-done');
    el.append(
      `<div class="challenge-top">` +
        `<span class="challenge-lv">第 ${lv.level} 关</span>` +
        `<span class="challenge-stars">${stars}</span>` +
        `</div>`
    );
    el.append(`<div class="challenge-title">${escapeHtml(lv.title)}</div>`);
    el.append(`<div class="meta">目标：${escapeHtml(lv.goal || '')}</div>`);
    if (lv.blurb) el.append(`<div class="blurb">${escapeHtml(lv.blurb)}</div>`);
    const row = $('<div class="row"></div>');
    if (!unlocked) {
      row.append('<span class="challenge-lock">先通上一关</span>');
    } else {
      row.append(
        $(`<button type="button" class="accent">${done ? '再战' : '开始'}</button>`).on(
          'click',
          () => startChallengeLevel(lv)
        )
      );
      if (done) row.append('<span class="challenge-done">已通关</span>');
    }
    el.append(row);
    box.append(el);
  });
}

async function startChallengeLevel(lv) {
  if (online.active) {
    alert('请先退出联机');
    return;
  }
  stopAuto();
  stopLibraryAuto();
  hideFinale();
  clearChallenge();
  const body = {
    mode: 'human_vs_ai',
    with_analysis: false,
    human_color: lv.human_color || 'white',
    free_play: true,
    engine_depth: 8,
  };
  const r = await fetch(`${API}/library/${encodeURIComponent(lv.id)}/load`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const state = await r.json().catch(() => ({}));
  if (!r.ok) {
    alert(JSON.stringify(state.detail || state));
    return;
  }
  challengeState = {
    active: true,
    level: lv.level,
    id: lv.id,
    title: lv.title,
    goal: lv.goal || '',
    humanColor: lv.human_color || 'white',
  };
  applyServerState(state);
  clearLastMoveMarkers();
  plyLog = [];
  viewPly = 0;
  browsingHistory = false;
  game.load(state.fen);
  board.position(state.fen, false);
  selectedSquare = null;
  clearHighlights();
  syncPlyLogFromMoves(state.moves || []);
  if ((lv.human_color || 'white') === 'black') {
    orientation = 'black';
    board.orientation('black');
  } else {
    orientation = 'white';
    board.orientation('white');
  }
  $('#game-mode').val('human_vs_ai');
  $('#human-color').val(lv.human_color || 'white');
  $('#with-analysis').prop('checked', false);
  refreshModeControls();
  updateStatus();
  updateChallengeHud();
  renderMoveList();
  $('#ai-meta').text(`闯关第 ${lv.level} 关 · ${lv.title}`);
  switchWorkspace('play');
}

$('.learn-mode-tab').click(function () {
  const mode = $(this).attr('data-learn');
  $('.learn-mode-tab').removeClass('active');
  $(this).addClass('active');
  if (mode === 'challenge') {
    $('#learn-library').attr('hidden', true);
    $('#learn-challenge').removeAttr('hidden');
    loadChallengeList();
  } else {
    $('#learn-challenge').attr('hidden', true);
    $('#learn-library').removeAttr('hidden');
    loadLibraryList();
  }
});

$(document).on('click', '#btn-challenge-quit', () => {
  clearChallenge();
  $('#ai-meta').text('已退出闯关');
});

$('.lib-filter').click(function () {
  $('.lib-filter').removeClass('active');
  $(this).addClass('active');
  libraryFilter = $(this).attr('data-cat') || '';
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
