// ChessMind 前端逻辑
const API = '/api';
let board = null;
let game = new Chess();
let orientation = 'white';
let selectedSquare = null;
let legalSquares = [];

// ── 棋盘初始化 ──
function initBoard() {
  board = Chessboard('board', {
    position: 'start',
    orientation: orientation,
    draggable: false,
    pieceTheme: 'https://chessboardjs.com/img/chesspieces/wikipedia/{piece}.png',
  });

  // 点击走子：选中 → 落子
  $('#board').on('click', '.square-55d63', function () {
    const square = $(this).attr('data-square');
    handleSquareClick(square);
  });

  updateStatus();
}

// ── 点击处理 ──
function handleSquareClick(square) {
  // 第一步：选中棋子
  if (selectedSquare === null) {
    const piece = game.get(square);
    if (piece && piece.color === game.turn()) {
      selectPiece(square);
    }
    return;
  }

  // 点击同一格 → 取消选中
  if (square === selectedSquare) {
    deselectPiece();
    return;
  }

  // 点击己方另一颗棋子 → 切换选中
  const piece = game.get(square);
  if (piece && piece.color === game.turn()) {
    deselectPiece();
    selectPiece(square);
    return;
  }

  // 第二步：尝试走子
  const move = game.move({
    from: selectedSquare,
    to: square,
    promotion: 'q',
  });

  if (move === null) {
    // 非法走法 → 保持选中状态
    return;
  }

  // 走子成功
  deselectPiece();
  board.position(game.fen());

  // 发送到后端分析
  fetch(`${API}/game/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ uci: selectedSquare + square }),
  })
    .then(r => r.json())
    .then(updateAnalysis)
    .catch(err => console.error('分析请求失败:', err));

  selectedSquare = null;
  updateStatus();
}

function selectPiece(square) {
  selectedSquare = square;
  // 高亮选中格
  $('.square-55d63').removeClass('highlight-selected');
  $(`.square-55d63[data-square="${square}"]`).addClass('highlight-selected');
  // 高亮合法走法
  highlightLegalMoves(square);
}

function deselectPiece() {
  selectedSquare = null;
  clearHighlights();
}

function highlightLegalMoves(square) {
  clearHighlights();
  const moves = game.moves({ square: square, verbose: true });
  legalSquares = moves.map(m => m.to);
  legalSquares.forEach(to => {
    const $sq = $(`.square-55d63[data-square="${to}"]`);
    const piece = game.get(to);
    $sq.addClass(piece ? 'highlight-capture' : 'highlight-move');
  });
}

function clearHighlights() {
  $('.square-55d63').removeClass('highlight-selected highlight-move highlight-capture');
  legalSquares = [];
}

// ── 更新分析面板 ──
function updateAnalysis(data) {
  if (data.error) { console.error(data.error); return; }

  const e = data.evaluation;
  const a = data.analysis;

  // 胜率条
  const wp = Math.round(e.after.win_prob_white * 100);
  const bp = Math.round(e.after.win_prob_black * 100);
  $('#eval-white').css('height', wp + '%');
  $('#eval-black').css('height', bp + '%');
  $('#white-prob').text(`白方 ${wp}%`);
  $('#black-prob').text(`黑方 ${bp}%`);

  // 走子分类
  const clsLabels = {
    brilliant: '✨ 妙手！', great: '👍 好棋', good: '✓ 正常',
    inaccuracy: '🤔 缓着', mistake: '⚠️ 漏着', blunder: '💀 大漏',
  };
  $('#move-class')
    .text(clsLabels[e.classification] || e.classification)
    .attr('class', 'move-class ' + e.classification);

  // Agent 分析
  $('#tab-summary').html(formatText(a.summary));
  $('#tab-tactical').html(formatText(a.tactical));
  $('#tab-strategic').html(formatText(a.strategic));
  $('#tab-pattern').html(formatText(a.pattern));

  if (data.game_over) {
    $('#game-status').text('对局结束 — ' + (data.result || ''));
    setTimeout(() => alert('对局结束！\n' + (data.result || '')), 200);
  }
}

function formatText(text) {
  if (!text) return '<p class="placeholder">暂无分析</p>';
  return text.split('\n').map(l => `<p>${l}</p>`).join('');
}

function updateStatus() {
  const turn = game.turn() === 'w' ? '白方走棋' : '黑方走棋';
  $('#game-status').text(game.game_over() ? '对局结束' : turn);
}

// ── 新对局 ──
$('#btn-new-game').click(() => {
  fetch(`${API}/game/new`, { method: 'POST' })
    .then(() => {
      game = new Chess();
      board.position('start');
      orientation = 'white';
      board.orientation('white');
      selectedSquare = null;
      clearHighlights();
      $('#move-class').text('等待走棋…').attr('class', 'move-class');
      $('#eval-white, #eval-black').css('height', '50%');
      $('#white-prob').text('白方 50%');
      $('#black-prob').text('黑方 50%');
      $('.tab-content').html('<p class="placeholder">走一步棋来看看～</p>');
      updateStatus();
    });
});

// ── 翻转棋盘 ──
$('#btn-flip').click(() => {
  orientation = orientation === 'white' ? 'black' : 'white';
  board.orientation(orientation);
});

// ── Tab 切换 ──
$('.tab').click(function () {
  $('.tab').removeClass('active');
  $('.tab-content').removeClass('active');
  $(this).addClass('active');
  $('#tab-' + $(this).data('tab')).addClass('active');
});

// ── PGN 导入 ──
$('#btn-analyze-pgn').click(async () => {
  const pgn = $('#pgn-input').val().trim();
  if (!pgn) return;

  $('#btn-analyze-pgn').text('分析中…').prop('disabled', true);
  const res = await fetch(`${API}/analyze/pgn`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pgn }),
  });
  const data = await res.json();
  $('#btn-analyze-pgn').text('分析 PGN').prop('disabled', false);

  if (data.moves) {
    $('#pgn-result').html(
      `<p>共分析 <strong>${data.total_moves}</strong> 步</p>` +
      data.moves.slice(-10).map(m =>
        `<div style="margin-bottom:8px;padding:8px;background:#2a2a4a;border-radius:4px">
          <strong>第${m.move.number}步 ${m.move.san}</strong> [${m.evaluation.classification}]
          <p style="margin-top:4px;font-size:0.85rem;color:#ccc">${m.analysis.summary}</p>
        </div>`
      ).join('')
    );
  }
});

// ── 启动 ──
$(document).ready(() => {
  initBoard();
  fetch(`${API}/game/new`, { method: 'POST' });
});
