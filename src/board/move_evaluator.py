"""Stockfish 引擎集成——评分与胜率转换"""
import asyncio
import chess.engine
from src.config import STOCKFISH_PATH


class MoveEvaluator:
    """封装 Stockfish 引擎的调用"""

    def __init__(self, depth: int = 15, time_limit: float = 0.5):
        self.depth = depth
        self.time_limit = time_limit
        self._engine: chess.engine.SimpleEngine | None = None

    @property
    def engine(self):
        if self._engine is None:
            raise RuntimeError("引擎未启动，请先调用 connect() 或使用异步上下文")
        return self._engine

    async def connect(self):
        """异步启动引擎"""
        self._engine = await asyncio.to_thread(
            chess.engine.SimpleEngine.popen_uci, STOCKFISH_PATH
        )

    def close(self):
        """关闭引擎"""
        if self._engine:
            self._engine.quit()
            self._engine = None

    def evaluate(self, fen: str) -> dict:
        """
        用 Stockfish 评估一个局面，返回：
        - score_cp: centipawn 评分（正=白优，负=黑优）
        - win_prob_white: 白方胜率 0.0~1.0
        - win_prob_black: 黑方胜率 0.0~1.0
        - pv: 推荐走法序列
        - mate_in: 距离将杀步数（None 表示暂无杀棋）
        - is_mate: 是否即将将杀
        """
        board = chess.Board(fen)
        limit = chess.engine.Limit(depth=self.depth)
        result = self.engine.analyse(board, limit)

        score = result["score"]
        cp = score.white()

        mate_in, is_mate = None, False
        if cp is not None:
            win_prob_white = self._cp_to_win_prob(cp)
            win_prob_black = 1.0 - win_prob_white
        else:
            mate_score = score.white()
            if hasattr(score, 'mate') and score.mate() is not None:
                mate_in = abs(score.mate())
                is_mate = True
                win_prob_white = 1.0 if score.mate() > 0 else 0.0
                win_prob_black = 1.0 - win_prob_white
            else:
                win_prob_white = 0.5
                win_prob_black = 0.5

        pv = result.get("pv", [])
        pv_san = [board.san(m) for m in pv[:5]]

        return {
            "score_cp": cp if cp is not None else 0,
            "win_prob_white": round(win_prob_white, 4),
            "win_prob_black": round(win_prob_black, 4),
            "pv": pv_san,
            "mate_in": mate_in,
            "is_mate": is_mate,
        }

    @staticmethod
    def _cp_to_win_prob(cp: float) -> float:
        """将 centipawn 评分转为白方胜率（经验公式）"""
        return 1.0 / (1.0 + 10.0 ** (-cp / 400.0))

    def classify_move(self, eval_before: dict, eval_after: dict) -> str:
        """
        根据评分变化对一步棋分类：
        - "brilliant"   妙手（大幅扭转或超越预期的好棋）
        - "great"       好棋（评分显著提升）
        - "good"        正常（小提升或持平）
        - "inaccuracy"  缓着（轻微掉分）
        - "mistake"     漏着（明显掉分）
        - "blunder"     大漏（掉分严重）
        """
        delta = eval_after["score_cp"] - eval_before["score_cp"]

        if delta >= 200:
            return "brilliant"
        elif delta >= 80:
            return "great"
        elif delta >= -30:
            return "good"
        elif delta >= -100:
            return "inaccuracy"
        elif delta >= -250:
            return "mistake"
        else:
            return "blunder"

    def cp_to_win_prob(self, cp: float) -> float:
        return self._cp_to_win_prob(cp)
