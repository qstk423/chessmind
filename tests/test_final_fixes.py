"""决赛演示关键降级与回合边界回归测试。"""
from __future__ import annotations

import asyncio

import chess
from fastapi.testclient import TestClient

from src.agents.schema import AgentOpinion, fallback_opinion
from src.council.debate import consensus_verdict
from src.council.disagreement import compute_disagreement
from src.main import app
from src.orchestrator import ChessMindOrchestrator


def test_new_game_after_demo_starts_from_standard_opening() -> None:
    orch = ChessMindOrchestrator()
    try:
        orch.new_game(with_analysis=False)
        assert orch.load_demo("greek_gift")["fen"] != chess.STARTING_FEN
        state = orch.new_game(mode="ai_vs_ai", white_ai="engine", with_analysis=False)
        assert state["fen"] == chess.STARTING_FEN
        assert orch.game.initial.fen() == chess.STARTING_FEN
    finally:
        orch.close()


def test_unavailable_agents_are_not_consensus() -> None:
    opinions = {
        role: fallback_opinion(role, "llm_disabled")
        for role in ("tactical", "strategic", "risk")
    }
    disagreement = compute_disagreement(*opinions.values())
    verdict = consensus_verdict(opinions, {"pv": ["Nf3"], "score_cp": 20})
    assert disagreement["level"] == "unavailable"
    assert disagreement["consensus_score"] is None
    assert not disagreement["trigger_debate"]
    assert verdict.recommended_move == "Nf3"
    assert not verdict.parse_ok
    assert "未形成共识" in verdict.summary
    assert "None" not in " ".join(verdict.reasoning_points)


def test_partial_agent_failure_is_not_full_consensus() -> None:
    tactical = AgentOpinion(agent="tactical", recommended_move="Nf3")
    strategic = AgentOpinion(agent="strategic", recommended_move="Nf3")
    risk = fallback_opinion("risk", "timeout")
    disagreement = compute_disagreement(tactical, strategic, risk)
    assert disagreement["level"] == "partial"
    assert disagreement["disagreement_score"] is None
    assert not disagreement["trigger_debate"]


def test_xiangqi_rejects_human_move_during_ai_turn() -> None:
    client = TestClient(app)
    headers = {"X-Session-Id": "finals_xiangqi_turn_guard"}
    new = client.post(
        "/api/xiangqi/game/new",
        json={"mode": "human_vs_ai", "human_color": "red"},
        headers=headers,
    )
    assert new.status_code == 200
    first = client.post("/api/xiangqi/game/move", json={"uci": "b0c2"}, headers=headers)
    assert first.status_code == 200
    assert first.json()["controller"] == "engine"
    blocked = client.post("/api/xiangqi/game/move", json={"uci": "b9c7"}, headers=headers)
    assert blocked.status_code == 400
    assert client.get("/api/xiangqi/game/state", headers=headers).json()["turn"] == "black"


def test_changed_position_cannot_save_old_analysis() -> None:
    async def scenario() -> None:
        orch = ChessMindOrchestrator()
        orch.new_game(with_analysis=True)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def delayed_council(**_kwargs):
            entered.set()
            await release.wait()
            return {"council": {"disagreement": {"level": "consensus"}}}

        orch._run_council = delayed_council
        task = asyncio.create_task(orch.analyze_position())
        await entered.wait()
        assert orch.game.push_move("e2e4") is not None
        release.set()
        result = await task
        assert result["stale"] is True
        assert orch.last_position_analysis is None
        assert orch.move_analyses == []

    asyncio.run(scenario())
