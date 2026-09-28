"""Engine searches used during live play must have a wall-clock budget."""

from types import SimpleNamespace

import chess
import chess.engine

from src.board.move_evaluator import MoveEvaluator


def test_live_engine_calls_include_time_limit() -> None:
    calls = []

    class FakeEngine:
        def play(self, _board, limit):
            calls.append(("play", limit))
            return SimpleNamespace(move=chess.Move.from_uci("e2e4"))

        def analyse(self, _board, limit):
            calls.append(("analyse", limit))
            return {
                "score": chess.engine.PovScore(chess.engine.Cp(30), chess.WHITE),
                "pv": [],
            }

    evaluator = MoveEvaluator(depth=15, time_limit=0.4)
    evaluator._engine = FakeEngine()
    assert evaluator._best_move_sync(chess.STARTING_FEN) == "e2e4"
    assert evaluator._evaluate_sync(chess.STARTING_FEN)["score_cp"] == 30
    assert [(kind, limit.depth, limit.time) for kind, limit in calls] == [
        ("play", 15, 0.4),
        ("analyse", 15, 0.4),
    ]
