"""棋局状态管理——基于 python-chess 封装"""
import chess
import chess.pgn
from dataclasses import dataclass, field
from datetime import datetime


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

    def __init__(self):
        self.board = chess.Board()
        self.move_history: list[MoveRecord] = []
        self.move_count = 0
        self.result: str | None = None

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
            self.board.push(move)
            fen_after = self.board.fen()
            self.move_count += 1

            record = MoveRecord(
                move_number=self.move_count,
                san=self.board.san(move),
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
        if self.board.is_checkmate():
            winner = "黑方" if self.board.turn == chess.WHITE else "白方"
            self.result = f"{winner}将杀获胜"
        elif self.board.is_stalemate():
            self.result = "逼和"
        elif self.board.is_insufficient_material():
            self.result = "子力不足，和棋"

    def get_recent_moves(self, n: int = 10) -> list[str]:
        """获取最近 n 步的 SAN 记谱文本"""
        return [r.san for r in self.move_history[-n:]]

    def to_pgn(self) -> str:
        """导出整局 PGN 文本"""
        game = chess.pgn.Game()
        node = game
        board_copy = chess.Board()
        for record in self.move_history:
            move = chess.Move.from_uci(record.uci)
            node = node.add_variation(move)
            board_copy.push(move)
        game.headers["Result"] = self.result or "*"
        game.headers["Date"] = datetime.now().strftime("%Y.%m.%d")
        return str(game)

    def reset(self):
        """重置棋局"""
        self.board = chess.Board()
        self.move_history = []
        self.move_count = 0
        self.result = None
