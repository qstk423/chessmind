"""Stockfish 引擎集成——评分与胜率转换"""
import asyncio
import chess
import chess.engine
from src.config import STOCKFISH_PATH


class MoveEvaluator:
    """封装 Stockfish 引擎的调用"""

    def __init__(self, depth: int = 15, time_limit: float = 0.5):
        self.depth = depth
        self.time_limit = time_limit
        self._engine: chess.engine.SimpleEngine | None = None
        # SimpleEngine 非线程安全，用锁把引擎访问串行化
        self._lock = asyncio.Lock()

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

    async def evaluate(self, fen: str) -> dict:
        """在线程池中执行同步引擎分析，避免阻塞事件循环"""
        async with self._lock:
            return await asyncio.to_thread(self._evaluate_sync, fen)

    def _evaluate_sync(self, fen: str) -> dict:
        """
        用 Stockfish 评估一个局面，返回：
        - score_cp: centipawn 评分（正=白优，负=黑优；将杀为接近 ±100000 的值）
        - win_prob_white / win_prob_black: 胜率 0.0~1.0
        - pv: 推荐走法序列（SAN，前 5 步）
        - mate_in: 距离将杀步数（None 表示暂无杀棋；0 表示已将杀）
        - is_mate: 是否为将杀分数
        """
        board = chess.Board(fen)

        # 终局已将杀的局面：直接给出确定性结论（引擎对 mate 0 的符号约定有歧义）
        if board.is_checkmate():
            white_mated = board.turn == chess.WHITE
            return {
                "score_cp": -100000 if white_mated else 100000,
                "win_prob_white": 0.0 if white_mated else 1.0,
                "win_prob_black": 1.0 if white_mated else 0.0,
                "pv": [],
                "mate_in": 0,
                "is_mate": True,
            }

        result = self.engine.analyse(board, chess.engine.Limit(depth=self.depth))
        pov = result["score"].white()  # 白方视角的 Cp 或 Mate 对象

        if pov.is_mate():
            mate_moves = pov.mate()  # 正=白方将杀黑方，负=白方被将杀
            mate_in, is_mate = abs(mate_moves), True
            # 注意：Mate.score() 返回 None，必须手工构造大数评分
            score_cp = (100000 - abs(mate_moves)) * (1 if mate_moves > 0 else -1)
            win_prob_white = 1.0 if mate_moves > 0 else 0.0
        else:
            mate_in, is_mate = None, False
            # 关键修复：pov 是 Cp 对象，不能直接做除法，必须先 .score() 转 int
            score_cp = pov.score()
            win_prob_white = self._cp_to_win_prob(score_cp)

        # PV 转 SAN 必须在推演中的棋盘上顺序生成（否则记谱错乱）
        pv = result.get("pv", [])
        pv_san = []
        replay = board.copy()
        for m in pv[:5]:
            try:
                pv_san.append(replay.san(m))
                replay.push(m)
            except Exception:
                break

        return {
            "score_cp": score_cp,  # int；将杀局面为 ±(100000-n) 的大数
            "win_prob_white": round(win_prob_white, 4),
            "win_prob_black": round(1.0 - win_prob_white, 4),
            "pv": pv_san,
            "mate_in": mate_in,
            "is_mate": is_mate,
        }

    @staticmethod
    def _cp_to_win_prob(cp: int) -> float:
        """将 centipawn 评分转为白方胜率（经验公式）"""
        return 1.0 / (1.0 + 10.0 ** (-cp / 400.0))

    def classify_move(self, eval_before: dict, eval_after: dict, mover_is_white: bool) -> str:
        """
        根据评分变化对一步棋分类。评分均为白方视角，需先换算到走子方视角，
        否则黑方的好棋会被判成漏着（原实现的 Bug）。

        - "brilliant"   妙手（将杀达成/不可阻挡，或大幅扭转）
        - "great"       好棋（评分显著提升）
        - "good"        正常（小提升或持平）
        - "inaccuracy"  缓着（轻微掉分）
        - "mistake"     漏着（明显掉分）
        - "blunder"     大漏（掉分严重）
        """
        def to_mover_pov(score_cp: int) -> int:
            return score_cp if mover_is_white else -score_cp

        before = to_mover_pov(eval_before["score_cp"])
        after = to_mover_pov(eval_after["score_cp"])
        delta = after - before

        # 走子后走子方已将杀或形成不可阻挡的将杀 → 妙手
        if eval_after["is_mate"] and after > 0:
            return "brilliant"

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
