"""棋局状态管理——基于 python-chess 封装"""
from dataclasses import dataclass, field
from datetime import datetime

import chess
import chess.pgn

# 和棋原因的中文说明（不含将杀）
DRAW_REASONS = {
    chess.Termination.STALEMATE: "逼和",
    chess.Termination.INSUFFICIENT_MATERIAL: "子力不足",
    chess.Termination.SEVENTYFIVE_MOVES: "75回合规则",
    chess.Termination.FIVEFOLD_REPETITION: "五次重复局面",
}


@dataclass
class MoveRecord:
    """单步走子记录"""
    move_number: int           # 第几步（从 1 开始）
    san: str                   # 标准记谱，如 "Nf3"
    uci: str                   # UCI 坐标，如 "g1f3"
    fen_before: str            # 走之前的棋盘状态
    fen_after: str             # 走之后的棋盘状态
    eval_before: float | None  # 走之前 Stockfish 评分
    eval_after: float | None   # 走之后 Stockfish 评分
    eval_delta: float | None   # 评分变化（正=好棋，负=漏着）
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class GameState:
    """管理一盘棋的完整生命周期"""

    def __init__(self, board: chess.Board | None = None):
        # 支持自定义初始局面（PGN 复盘带 FEN 头时使用）
        self.initial = board.copy() if board is not None else chess.Board()
        self.board = self.initial.copy()
        self.move_history: list[MoveRecord] = []
        self.move_count = 0
        self.result: str | None = None        # 展示用中文结果
        self.result_pgn: str = "*"            # PGN 标准结果标记（1-0/0-1/1/2-1/2/*）

    @property
    def fen(self) -> str:
        """当前棋盘 FEN 字符串"""
        return self.board.fen()

    @property
    def is_game_over(self) -> bool:
        return self.board.is_game_over()

    def legal_moves(self) -> list[str]:
        """返回当前合法走法的 UCI 列表"""
        return [move.uci() for move in self.board.legal_moves]

    def push_move(self, uci: str) -> MoveRecord | None:
        """执行一步走子，返回记录；不合法则返回 None"""
        try:
            move = chess.Move.from_uci(uci)
            if move not in self.board.legal_moves:
                return None

            fen_before = self.board.fen()
            san = self.board.san(move)  # 必须在 push 之前生成 SAN
            self.board.push(move)
            fen_after = self.board.fen()
            self.move_count += 1

            record = MoveRecord(
                move_number=self.move_count,
                san=san,
                uci=uci,
                fen_before=fen_before,
                fen_after=fen_after,
                eval_before=None,
                eval_after=None,
                eval_delta=None,
            )
            self.move_history.append(record)
            self._check_game_over()
            return record
        except ValueError:
            return None

    def _check_game_over(self):
        """基于 board.outcome() 判定终局，覆盖将杀/逼和/子力不足/75回合/五次重复"""
        outcome = self.board.outcome()
        if outcome is None:
            return
        if outcome.termination == chess.Termination.CHECKMATE:
            winner = "白方" if outcome.winner == chess.WHITE else "黑方"
            self.result = f"{winner}将杀获胜"
        else:
            reason = DRAW_REASONS.get(outcome.termination, "和棋")
            self.result = f"和棋（{reason}）"
        self.result_pgn = outcome.result()

    def pop_move(self) -> MoveRecord | None:
        """悔棋：撤销最后一步，返回被撤销的记录。"""
        if not self.move_history:
            return None
        record = self.move_history.pop()
        self.board.pop()
        self.move_count = len(self.move_history)
        self.result = None
        self.result_pgn = "*"
        if self.board.is_game_over():
            self._check_game_over()
        return record

    def get_recent_moves(self, n: int = 10) -> list[str]:
        """获取最近 n 步的 SAN 记谱文本"""
        return [r.san for r in self.move_history[-n:]]

    def to_pgn(self) -> str:
        """导出整局 PGN 文本（Result 头使用 PGN 标准标记）"""
        game = chess.pgn.Game()
        if self.initial.fen() != chess.STARTING_FEN:
            game.setup(self.initial)
        node = game
        for record in self.move_history:
            node = node.add_variation(chess.Move.from_uci(record.uci))
        game.headers["Result"] = self.result_pgn
        game.headers["Date"] = datetime.now().strftime("%Y.%m.%d")
        return str(game)

    def reset(self):
        """重置棋局（回到初始局面）"""
        self.board = self.initial.copy()
        self.move_history = []
        self.move_count = 0
        self.result = None
        self.result_pgn = "*"

    def load_fen(self, fen: str) -> None:
        """从 FEN 加载为新的初始局面并重置历史。"""
        board = chess.Board(fen)
        self.initial = board.copy()
        self.reset()
