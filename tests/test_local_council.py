import asyncio

import chess

from src.council.local_analysis import build_local_council
from src.orchestrator import ChessMindOrchestrator


ENGINE_EVAL = {
    "score_cp": 28,
    "win_prob_white": 0.54,
    "win_prob_black": 0.46,
    "pv": ["Nf3", "Nf6", "g3"],
    "mate_in": None,
    "is_mate": False,
}


def test_local_council_has_all_roles_and_legal_recommendations():
    result = build_local_council(
        fen=chess.STARTING_FEN,
        engine_eval=ENGINE_EVAL,
        move_class="good",
        coach_level="intermediate",
    )

    council = result["council"]
    assert council["analysis_source"] == "local_heuristic"
    assert council["analysis_mode"] == "fast"
    assert council["debate"]["triggered"] is False
    assert set(council["agents"]) == {"tactical", "strategic", "risk", "coach"}

    board = chess.Board()
    for role in ("tactical", "strategic", "risk", "coach"):
        opinion = council["agents"][role]
        assert opinion["parse_ok"] is True
        assert opinion["summary"]
        if opinion["recommended_move"]:
            assert board.parse_san(opinion["recommended_move"]) in board.legal_moves


def test_fast_council_never_calls_remote_agents():
    orchestrator = ChessMindOrchestrator()

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("fast mode must not call a remote agent")

    orchestrator.tactical.analyze_structured = forbidden
    orchestrator.strategic.analyze_structured = forbidden
    orchestrator.risk.analyze_structured = forbidden

    try:
        result = asyncio.run(
            orchestrator._run_council(
                fen=chess.STARTING_FEN,
                history=[],
                grounding="starting position",
                eval_after=ENGINE_EVAL,
                move_class="good",
                analysis_mode="fast",
            )
        )
    finally:
        orchestrator.close()

    assert result["council"]["analysis_source"] == "local_heuristic"
