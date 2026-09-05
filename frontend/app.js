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
/** 上一步起终点（JJ 象棋风格：起点留白点） */
let lastMoveFrom = null;
let lastMoveTo = null;

function initBoard() {
  board = Chessboard('board', {
    position: 'start',
    orientation: orientation,
    draggable: false,
    pieceTheme: 'https://chessboardjs.com/img/chesspieces/wikipedia/{piece}.png',
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
  if (serverState.mode === 'ai_vs_ai') return false;
  if (serverState.mode === 'human_vs_human') return true;
  // human_vs_ai：仅人类回合
  return serverState.controller === 'human';
}

function handleSquareClick(square) {
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
    setTimeout(() => alert('对局结束！\n' + (data.result || '')), 200);
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

  const e = data.evaluation;
  const a = data.analysis || {};
  const council = a.council;

  const wp = Math.round(e.after.win_prob_white * 100);
  const bp = Math.round(e.after.win_prob_black * 100);
  $('#eval-white').css('height', wp + '%');
  $('#eval-black').css('height', bp + '%');
  $('#white-prob').text(`白方 ${wp}%`);
  $('#black-prob').text(`黑方 ${bp}%`);

  const clsLabels = {
    brilliant: '✨ 妙手！', great: '👍 好棋', good: '✓ 正常',
    inaccuracy: '🤔 缓着', mistake: '⚠️ 漏着', blunder: '💀 大漏',
  };
  $('#move-class')
    .text(clsLabels[e.classification] || e.classification)
    .attr('class', 'move-class ' + e.classification);

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
  $('#game-status').text('AI 思考中…');
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
  }, STEP_DELAY_MS);
}

function startAuto() {
  if (serverState.mode !== 'ai_vs_ai' && serverState.mode !== 'human_vs_ai') {
    alert('请先选择「AI vs AI」或「人 vs AI」模式并开新对局');
    return;
  }
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

async function loadDemos() {
  try {
    const data = await fetch(`${API}/demos`).then(r => r.json());
    const box = $('#demo-buttons').empty();
    (data.demos || []).forEach(d => {
      const btn = $(`<button type="button" title="${escapeHtml(d.blurb)}">${escapeHtml(d.title)}</button>`);
      btn.click(async () => {
        if (busy) return;
        busy = true;
        stopAuto();
        $('#ai-meta').text(`加载 Demo：${d.title} …`);
        try {
          const r = await fetch(`${API}/demos/${encodeURIComponent(d.id)}/run`, { method: 'POST' });
          const payload = await r.json();
          if (!r.ok) {
            alert('Demo 失败：' + JSON.stringify(payload.detail || payload));
            return;
          }
          const state = payload.state || {};
          applyServerState(state);
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
            $('#ai-meta').text(`Demo「${d.title}」Council 完成`);
            if (payload.analysis.analysis?.council?.debate?.triggered) {
              $('.tab').removeClass('active');
              $('.tab-content').removeClass('active');
              $('.tab[data-tab="debate"]').addClass('active');
              $('#tab-debate').addClass('active');
            }
          }
        } finally {
          busy = false;
        }
      });
      box.append(btn);
    });
  } catch (e) {
    $('#demo-buttons').text('Demo 列表加载失败');
  }
}

$('#btn-analyze-pos').click(async () => {
  if (busy) return;
  busy = true;
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
    busy = false;
  }
});

$('#btn-vision').click(async () => {
  const file = $('#vision-file')[0].files[0];
  if (!file) {
    alert('请先选择棋盘截图');
    return;
  }
  if (busy) return;
  busy = true;
  $('#vision-status').text('识别中…');
  try {
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch(`${API}/vision/fen?apply=true`, { method: 'POST', body: fd });
    const data = await r.json();
    if (!r.ok) {
      $('#vision-status').text('失败');
      alert('识谱失败：' + JSON.stringify(data.detail || data));
      return;
    }
    const state = data.state || {};
    applyServerState(state);
    game.load(state.fen);
    board.position(state.fen, false);
    $('#vision-status').text(`FEN 已加载 · ${data.vision?.vision_model || ''}`);
    $('#ai-meta').text('截图局面已加载，可点「分析当前局面」');
    updateStatus();
  } catch (e) {
    $('#vision-status').text('请求失败');
  } finally {
    busy = false;
  }
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

$(document).ready(async () => {
  initBoard();
  $(window).on('resize', () => {
    if (lastMoveFrom && lastMoveTo) paintLastMoveMarkers();
  });
  await startNewGame();
  await loadDemos();
  try {
    const h = await fetch(`${API}/health`).then(r => r.json());
    $('#llm-status').text(
      `模型：${h.llm_model || '?'} · ${h.llm_enabled ? '已启用' : '未配置 Key'} · 引擎${h.stockfish ? '就绪' : '未连接'}`
    );
  } catch (_) {
    $('#llm-status').text('无法连接后端 /api/health');
  }
});
