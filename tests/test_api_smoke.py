"""无外部 Key 的 API 冒烟（TestClient）。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from src.main import app


client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert "llm_enabled" in body
    assert "llm_model" in body


def test_new_game_and_move():
    r = client.post("/api/game/new", json={"mode": "human_vs_human", "with_analysis": False})
    assert r.status_code == 200
    fen = r.json().get("fen")
    assert fen
    r2 = client.post("/api/game/move", json={"uci": "e2e4", "with_analysis": False})
    assert r2.status_code == 200
    assert "fen" in r2.json() or "move" in r2.json()


def test_challenges_list():
    r = client.get("/api/challenges")
    assert r.status_code == 200
    levels = r.json().get("levels") or []
    assert len(levels) >= 1


def test_accuracy_helper():
    from src.council.review import compute_accuracy

    acc = compute_accuracy(
        [
            {
                "move": {"san": "e4", "number": 1},
                "fen_before": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                "evaluation": {"classification": "best"},
            }
        ]
    )
    assert acc["overall"] == 100.0


def test_pgn_cap():
    from src.config import PGN_MAX_PLIES
    import chess

    board = chess.Board()
    sans = []
    # 生成足够长的合法半步（开局重复推进，直到超限）
    while len(sans) <= PGN_MAX_PLIES + 2:
        legal = list(board.legal_moves)
        if not legal:
            break
        mv = legal[0]
        sans.append(board.san(mv))
        board.push(mv)
    # 拼成简易 PGN
    parts = []
    for i, san in enumerate(sans):
        if i % 2 == 0:
            parts.append(f"{i // 2 + 1}.")
        parts.append(san)
    pgn = " ".join(parts)
    r = client.post("/api/analyze/pgn", json={"pgn": pgn})
    assert r.status_code == 400
    assert "上限" in str(r.json().get("detail", ""))
