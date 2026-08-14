"""多 Agent 编排器：并行调用三个 Agent，汇总输出"""
import asyncio
from openai import AsyncOpenAI
from src.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from src.board.game_state import GameState
from src.board.move_evaluator import MoveEvaluator
from src.agents.tactical import TacticalAgent
from src.agents.strategic import StrategicAgent
from src.agents.pattern import PatternAgent
from src.agents.summarizer import SummarizerAgent


class ChessMindOrchestrator:
    """项目总控：管理棋局、引擎、Agent 的协作"""

    def __init__(self):
        self.game = GameState()
        self.evaluator = MoveEvaluator()
        self._connected = False

        # 初始化 LLM 客户端
        self.llm_client = AsyncOpenAI(
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
        )

        # 初始化 Agent
        self.tactical = TacticalAgent(self.llm_client, LLM_MODEL)
        self.strategic = StrategicAgent(self.llm_client, LLM_MODEL)
        self.pattern = PatternAgent(self.llm_client, LLM_MODEL)
        self.summarizer = SummarizerAgent(self.llm_client, LLM_MODEL)

    async def connect(self):
        """启动引擎"""
        if not self._connected:
            await self.evaluator.connect()
            self._connected = True

    def close(self):
        """关闭引擎"""
        self.evaluator.close()
        self._connected = False

    def new_game(self):
        """重置棋局"""
        self.game.reset()

    async def make_move(self, uci: str) -> dict | None:
        """
        执行一步走子，返回完整的分析结果。

        流程：
        1. 走子前 Stockfish 评估
        2. 执行走子
        3. 走子后 Stockfish 评估
        4. 走子分类
        5. 三个 Agent 并行分析
        6. 汇总输出
        """
        legal = self.game.legal_moves()
        if uci not in legal:
            return {"error": "非法走法", "legal_moves": legal}

        # 走前评估
        eval_before = self.evaluator.evaluate(self.game.fen)

        # 执行走子
        record = self.game.push_move(uci)
        if record is None:
            return {"error": "走子执行失败"}

        # 走后评估
        eval_after = self.evaluator.evaluate(self.game.fen)
        move_class = self.evaluator.classify_move(eval_before, eval_after)

        # 更新记录
        record.eval_before = eval_before["score_cp"]
        record.eval_after = eval_after["score_cp"]
        record.eval_delta = eval_after["score_cp"] - eval_before["score_cp"]

        # 并行调用三个 Agent
        history = self.game.get_recent_moves(10)
        tac, strat, pat = await asyncio.gather(
            self.tactical.analyze(self.game.fen, history),
            self.strategic.analyze(self.game.fen, history),
            self.pattern.analyze(self.game.fen, history),
        )

        # 汇总
        summary = await self.summarizer.summarize(
            tactical=tac,
            strategic=strat,
            pattern=pat,
            stockfish_info=eval_after,
            move_class=move_class,
            fen=self.game.fen,
        )

        return {
            "move": {
                "san": record.san,
                "uci": record.uci,
                "number": record.move_number,
            },
            "evaluation": {
                "before": eval_before,
                "after": eval_after,
                "delta": record.eval_delta,
                "classification": move_class,
            },
            "analysis": {
                "tactical": tac,
                "strategic": strat,
                "pattern": pat,
                "summary": summary,
            },
            "game_over": self.game.is_game_over,
            "result": self.game.result,
            "fen": self.game.fen,
            "legal_moves": self.game.legal_moves(),
        }

    def get_state(self) -> dict:
        """获取当前棋局状态（不含 Agent 分析）"""
        return {
            "fen": self.game.fen,
            "move_count": self.game.move_count,
            "is_game_over": self.game.is_game_over,
            "result": self.game.result,
            "legal_moves": self.game.legal_moves(),
            "pgn": self.game.to_pgn(),
        }
