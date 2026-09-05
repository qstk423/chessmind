"""ChessCouncil 编排器：对局模式 + 多 Agent 结构化分析 / 辩论 / 教练"""
from __future__ import annotations

import asyncio
from typing import Literal

import chess
from openai import AsyncOpenAI

from src.agents.coach import CoachAgent, CoachLevel
from src.agents.move_picker import MovePickerAgent
from src.agents.risk import RiskAgent
from src.agents.strategic import StrategicAgent
from src.agents.tactical import TacticalAgent
from src.board.game_state import GameState
from src.board.move_evaluator import MoveEvaluator
from src.board.position_features import describe_position
from src.config import (
    AI_ENGINE_DEPTH,
    COACH_LEVEL,
    DEBATE_THRESHOLD,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_ENABLED,
    LLM_MODEL,
)
from src.council.debate import ArbiterAgent, consensus_verdict, run_debate
from src.council.demos import get_demo, list_demos
from src.council.disagreement import compute_disagreement
from src.council.review import build_review
from src.storage import upsert_game
from src.llm_logger import new_game_id, set_context

GameMode = Literal["human_vs_human", "human_vs_ai", "ai_vs_ai"]


class ChessMindOrchestrator:
    """项目总控：管理棋局、引擎、Council Agent 协作"""

    def __init__(self):
        self.game = GameState()
        self.evaluator = MoveEvaluator()
        self._connected = False

        self.mode: GameMode = "human_vs_human"
        self.human_color: Literal["white", "black"] = "white"
        self.white_ai: Literal["llm", "engine"] = "llm"
        self.engine_depth: int = AI_ENGINE_DEPTH
        self.game_id: str | None = None
        self.with_analysis: bool = True
        self.coach_level: CoachLevel = (
            COACH_LEVEL if COACH_LEVEL in ("beginner", "intermediate", "advanced") else "intermediate"
        )
        # 本局逐步分析缓存（用于赛后复盘）
        self.move_analyses: list[dict] = []
        self.last_position_analysis: dict | None = None
        self._demo_diverge = False
        self.fen_start: str = self.game.fen

        self.llm_client = (
            AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
            if LLM_ENABLED
            else None
        )

        self.tactical = TacticalAgent(self.llm_client, LLM_MODEL)
        self.strategic = StrategicAgent(self.llm_client, LLM_MODEL)
        self.risk = RiskAgent(self.llm_client, LLM_MODEL)
        self.coach = CoachAgent(self.llm_client, LLM_MODEL)
        self.arbiter = ArbiterAgent(self.llm_client, LLM_MODEL)
        self.move_picker = MovePickerAgent(self.llm_client, LLM_MODEL)

    async def connect(self):
        if not self._connected:
            await self.evaluator.connect()
            self._connected = True

    def close(self):
        self.evaluator.close()
        self._connected = False

    def new_game(
        self,
        mode: GameMode = "human_vs_human",
        human_color: Literal["white", "black"] = "white",
        white_ai: Literal["llm", "engine"] = "llm",
        engine_depth: int | None = None,
        with_analysis: bool = True,
        coach_level: CoachLevel | None = None,
    ) -> dict:
        self.game.reset()
        self.mode = mode
        self.human_color = human_color
        self.white_ai = white_ai
        self.engine_depth = engine_depth if engine_depth is not None else AI_ENGINE_DEPTH
        self.with_analysis = with_analysis
        if coach_level in ("beginner", "intermediate", "advanced"):
            self.coach_level = coach_level
        self.game_id = new_game_id()
        self.move_analyses = []
        self.last_position_analysis = None
        self._demo_diverge = False
        self.fen_start = self.game.fen
        return self.get_state()

    def load_fen(self, fen: str) -> dict:
        """加载自定义局面（保留当前模式设置）。"""
        try:
            self.game.load_fen(fen)
        except ValueError as e:
            return {"error": f"非法 FEN：{e}"}
        self.game_id = new_game_id()
        self.move_analyses = []
        self.last_position_analysis = None
        self._demo_diverge = False
        self.fen_start = self.game.fen
        return self.get_state()

    def persist_game(self, *, title: str | None = None, with_review: bool = False) -> dict:
        """写入 SQLite；终局或显式保存时调用。"""
        if not self.game_id:
            return {"error": "无当前对局"}
        review = None
        if with_review or self.game.is_game_over:
            review = self.get_review()
        return upsert_game(
            game_id=self.game_id,
            mode=self.mode,
            title=title,
            result=self.game.result,
            fen_start=self.fen_start,
            fen_current=self.game.fen,
            pgn=self.game.to_pgn(),
            move_count=self.game.move_count,
            review=review,
            meta={
                "human_color": self.human_color,
                "white_ai": self.white_ai,
                "coach_level": self.coach_level,
            },
        )

    def load_demo(self, demo_id: str) -> dict:
        demo = get_demo(demo_id)
        if not demo:
            return {"error": f"未知 Demo：{demo_id}", "available": [d["id"] for d in list_demos()]}
        state = self.load_fen(demo["fen"])
        if "error" in state:
            return state
        self._demo_diverge = bool(demo.get("diverge"))
        state["demo"] = {
            "id": demo["id"],
            "title": demo["title"],
            "blurb": demo["blurb"],
            "tags": demo["tags"],
        }
        return state

    async def analyze_position(self, *, with_analysis: bool = True) -> dict:
        """分析当前局面（不走子）——路演 Demo / 识谱后一键 Council。"""
        game = self.game
        set_context(game_id=self.game_id, move_number=game.move_count)
        eval_after = await self.evaluator.evaluate(game.fen)
        grounding = describe_position(game.board, eval_after)
        history = game.get_recent_moves(10)

        if with_analysis:
            analysis = await self._run_council(
                fen=game.fen,
                history=history,
                grounding=grounding,
                eval_after=eval_after,
                move_class="position",
                diverge_roles=self._demo_diverge,
            )
        else:
            analysis = {
                "tactical": "（跳过）",
                "strategic": "（跳过）",
                "pattern": "（跳过）",
                "summary": "（跳过）",
                "council": None,
            }

        result = {
            "position_only": True,
            "move": None,
            "evaluation": {"after": eval_after, "classification": "position"},
            "analysis": analysis,
            "game_over": game.is_game_over,
            "result": game.result,
            "fen": game.fen,
            "legal_moves": game.legal_moves(),
            "mode": self.mode,
            "next_controller": (
                None if game.is_game_over else self.current_controller()
            ),
        }
        self.last_position_analysis = result
        return result

    def get_review(self) -> dict:
        return build_review(
            self.move_analyses,
            game_result=self.game.result,
            pgn=self.game.to_pgn(),
        )

    def _side_controller(self, color: chess.Color) -> Literal["human", "llm", "engine"]:
        if self.mode == "human_vs_human":
            return "human"
        if self.mode == "human_vs_ai":
            human_is_white = self.human_color == "white"
            if color == chess.WHITE:
                return "human" if human_is_white else "llm"
            return "human" if not human_is_white else "llm"
        if color == chess.WHITE:
            return self.white_ai
        return "engine" if self.white_ai == "llm" else "llm"

    def current_controller(self) -> Literal["human", "llm", "engine"]:
        return self._side_controller(self.game.board.turn)

    async def make_move(self, uci: str, *, with_analysis: bool | None = None) -> dict | None:
        analyze = self.with_analysis if with_analysis is None else with_analysis
        return await self.analyze_move(self.game, uci, with_analysis=analyze)

    async def _run_council(
        self,
        *,
        fen: str,
        history: list[str],
        grounding: str,
        eval_after: dict,
        move_class: str,
        diverge_roles: bool = False,
    ) -> dict:
        ctx = grounding
        if diverge_roles:
            from src.council.demos import DIVERGE_HINT

            ctx = grounding + "\n\n" + DIVERGE_HINT

        tac_o, strat_o, risk_o = await asyncio.gather(
            self.tactical.analyze_structured(fen, history, ctx),
            self.strategic.analyze_structured(fen, history, ctx),
            self.risk.analyze_structured(fen, history, ctx),
        )
        opinions = {"tactical": tac_o, "strategic": strat_o, "risk": risk_o}
        disagreement = compute_disagreement(tac_o, strat_o, risk_o)
        # 阈值可配置
        disagreement["trigger_debate"] = disagreement["disagreement_score"] >= DEBATE_THRESHOLD
        # 路演 Demo：只要三方推荐不完全一致，就强制进入辩论（保证可演示）
        if diverge_roles:
            mv = {
                tac_o.recommended_move,
                strat_o.recommended_move,
                risk_o.recommended_move,
            }
            mv.discard(None)
            if len(mv) >= 2:
                disagreement["trigger_debate"] = True
                disagreement["demo_forced"] = True
                if disagreement["disagreement_score"] < 0.5:
                    disagreement["badge"] = "🔥 路演争议"
                    disagreement["label"] = "Demo 强制辩论（角色推荐不一致）"
                    disagreement["level"] = "clear"

        debate_payload = None
        if disagreement["trigger_debate"] and LLM_ENABLED:
            debate_payload = await run_debate(
                tactical_agent=self.tactical,
                strategic_agent=self.strategic,
                risk_agent=self.risk,
                arbiter=self.arbiter,
                fen=fen,
                history=history,
                grounding=grounding,
                stockfish_info=eval_after,
                opinions=opinions,
            )
            from src.agents.schema import AgentOpinion

            vdict = debate_payload.get("verdict") or {}
            verdict = AgentOpinion(
                agent="arbiter",
                recommended_move=vdict.get("recommended_move"),
                alternative_moves=list(vdict.get("alternative_moves") or []),
                confidence=float(vdict.get("confidence") or 0.5),
                evaluation=float(vdict.get("evaluation") or 0.0),
                risk=float(vdict.get("risk") or 0.5),
                summary=str(vdict.get("summary") or ""),
                reasoning_points=list(vdict.get("reasoning_points") or []),
                concerns=list(vdict.get("concerns") or []),
                parse_ok=bool(vdict.get("parse_ok", True)),
                raw_text=str(vdict.get("raw_text") or ""),
                fallback_reason=vdict.get("fallback_reason"),
            )
        else:
            verdict = consensus_verdict(opinions, eval_after)
            debate_payload = {"triggered": False, "rounds": [], "verdict": verdict.to_dict()}

        snapshot = (
            f"分歧：{disagreement}\n"
            f"战术：{tac_o.to_dict()}\n战略：{strat_o.to_dict()}\n风险：{risk_o.to_dict()}\n"
            f"裁决：{verdict.to_dict()}\n辩论触发：{debate_payload.get('triggered')}"
        )
        coach_o = await self.coach.explain(
            fen=fen,
            move_history=history,
            grounding=grounding,
            stockfish_info=eval_after,
            move_class=move_class,
            level=self.coach_level,
            council_snapshot=snapshot,
            final_move=verdict.recommended_move,
        )

        # 兼容旧前端字段：pattern -> 风险摘要；summary -> 教练讲解
        analysis = {
            "tactical": tac_o.summary,
            "strategic": strat_o.summary,
            "pattern": risk_o.summary,  # 兼容旧 tab「开局」位：现展示风险审查
            "summary": coach_o.summary,
            "council": {
                "agents": {
                    "tactical": tac_o.to_dict(),
                    "strategic": strat_o.to_dict(),
                    "risk": risk_o.to_dict(),
                    "coach": coach_o.to_dict(),
                },
                "disagreement": disagreement,
                "debate": debate_payload,
                "verdict": verdict.to_dict(),
                "coach_level": self.coach_level,
            },
        }
        return analysis

    async def analyze_move(
        self,
        game: GameState,
        uci: str,
        *,
        with_analysis: bool = True,
        ai_meta: dict | None = None,
    ) -> dict | None:
        legal = game.legal_moves()
        if uci not in legal:
            return {"error": "非法走法", "legal_moves": legal}

        mover_is_white = game.board.turn == chess.WHITE
        set_context(game_id=self.game_id, move_number=game.move_count + 1)

        eval_before = await self.evaluator.evaluate(game.fen)

        record = game.push_move(uci)
        if record is None:
            return {"error": "走子执行失败"}

        eval_after = await self.evaluator.evaluate(game.fen)
        move_class = self.evaluator.classify_move(eval_before, eval_after, mover_is_white)

        record.eval_before = eval_before["score_cp"]
        record.eval_after = eval_after["score_cp"]
        record.eval_delta = eval_after["score_cp"] - eval_before["score_cp"]

        grounding = describe_position(game.board, eval_after)
        history = game.get_recent_moves(10)

        if with_analysis:
            analysis = await self._run_council(
                fen=game.fen,
                history=history,
                grounding=grounding,
                eval_after=eval_after,
                move_class=move_class,
            )
        else:
            analysis = {
                "tactical": "（本步跳过 Council 分析）",
                "strategic": "（本步跳过 Council 分析）",
                "pattern": "（本步跳过 Council 分析）",
                "summary": "（本步跳过 Council 分析）",
                "council": None,
            }

        result = {
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
            "analysis": analysis,
            "game_over": game.is_game_over,
            "result": game.result,
            "fen": game.fen,
            "legal_moves": game.legal_moves(),
            "mode": self.mode,
            "next_controller": (
                None if game.is_game_over else self._side_controller(game.board.turn)
            ),
        }
        if ai_meta:
            result["ai"] = ai_meta
        # 仅主对局缓存复盘材料
        if game is self.game and with_analysis:
            self.move_analyses.append(
                {
                    "move": result["move"],
                    "evaluation": result["evaluation"],
                    "analysis": {
                        "summary": analysis.get("summary"),
                        "council": analysis.get("council"),
                    },
                    "fen": result["fen"],
                }
            )
        if game is self.game:
            try:
                saved = self.persist_game(with_review=bool(game.is_game_over))
                result["saved"] = {"id": saved.get("id"), "updated_at": saved.get("updated_at")}
            except Exception as e:
                result["saved"] = {"error": f"{type(e).__name__}: {e}"}
        return result

    async def choose_ai_uci(self) -> dict:
        if self.game.is_game_over:
            return {"error": "对局已结束"}

        controller = self.current_controller()
        if controller == "human":
            return {"error": "当前应由人类走子", "controller": controller}

        legal = self.game.legal_moves()
        if not legal:
            return {"error": "无合法着法"}

        set_context(game_id=self.game_id, move_number=self.game.move_count + 1)
        depth = self.engine_depth

        if controller == "engine":
            uci = await self.evaluator.best_move(self.game.fen, depth=depth)
            if uci is None or uci not in legal:
                uci = legal[0]
            return {
                "uci": uci,
                "source": "engine",
                "reason": f"Stockfish depth={depth}",
                "controller": controller,
            }

        eval_now = await self.evaluator.evaluate(self.game.fen, depth=min(depth, 10))
        grounding = describe_position(self.game.board, eval_now)
        engine_hint = await self.evaluator.best_move(self.game.fen, depth=min(depth, 10))

        pick = await self.move_picker.pick_move(
            fen=self.game.fen,
            legal_moves=legal,
            move_history=self.game.get_recent_moves(16),
            grounding=grounding,
            engine_hint=engine_hint,
        )
        uci = pick.get("uci")
        source = pick.get("source", "llm")
        reason = pick.get("reason", "")

        if uci not in legal:
            fallback = await self.evaluator.best_move(self.game.fen, depth=depth)
            if fallback is None or fallback not in legal:
                fallback = legal[0]
            return {
                "uci": fallback,
                "source": "engine_fallback",
                "reason": f"LLM 无效({reason})，回退 Stockfish",
                "controller": controller,
                "llm_attempt": pick,
            }

        return {
            "uci": uci,
            "source": source,
            "reason": reason,
            "controller": controller,
        }

    async def ai_step(self, *, with_analysis: bool | None = None) -> dict:
        choice = await self.choose_ai_uci()
        if "error" in choice:
            return choice

        analyze = self.with_analysis if with_analysis is None else with_analysis
        return await self.analyze_move(
            self.game,
            choice["uci"],
            with_analysis=analyze,
            ai_meta={
                "source": choice.get("source"),
                "reason": choice.get("reason"),
                "controller": choice.get("controller"),
            },
        )

    async def health(self) -> dict:
        import time

        from src.llm_logger import log_llm_call

        info = {
            "stockfish": self._connected,
            "llm_enabled": LLM_ENABLED,
            "llm_model": LLM_MODEL,
            "llm_base_url": LLM_BASE_URL,
            "mode": self.mode,
            "game_id": self.game_id,
            "product": "ChessCouncil",
        }
        if not LLM_ENABLED or self.llm_client is None:
            info["llm_ping"] = "skipped"
            return info

        try:
            t0 = time.perf_counter()
            resp = await self.llm_client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": "回复OK即可"}],
                max_tokens=5,
                temperature=0,
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            usage = getattr(resp, "usage", None)
            log_llm_call(
                agent="health_ping",
                model=LLM_MODEL,
                success=True,
                latency_ms=latency_ms,
                prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
                completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
                total_tokens=getattr(usage, "total_tokens", None) if usage else None,
            )
            info["llm_ping"] = "ok"
            info["llm_latency_ms"] = round(latency_ms, 1)
        except Exception as e:
            log_llm_call(
                agent="health_ping",
                model=LLM_MODEL,
                success=False,
                latency_ms=0,
                error=f"{type(e).__name__}: {e}",
            )
            info["llm_ping"] = "fail"
            info["llm_error"] = f"{type(e).__name__}: {e}"
        return info

    def get_state(self) -> dict:
        return {
            "fen": self.game.fen,
            "move_count": self.game.move_count,
            "is_game_over": self.game.is_game_over,
            "result": self.game.result,
            "legal_moves": self.game.legal_moves(),
            "pgn": self.game.to_pgn(),
            "mode": self.mode,
            "human_color": self.human_color,
            "white_ai": self.white_ai,
            "engine_depth": self.engine_depth,
            "with_analysis": self.with_analysis,
            "coach_level": self.coach_level,
            "game_id": self.game_id,
            "turn": "white" if self.game.board.turn == chess.WHITE else "black",
            "controller": (
                None if self.game.is_game_over else self.current_controller()
            ),
            "llm_enabled": LLM_ENABLED,
            "llm_model": LLM_MODEL,
            "product": "ChessCouncil",
        }
