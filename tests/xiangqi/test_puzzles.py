"""谜题、会话、联机回归。"""
from __future__ import annotations

from fastapi import Request
from fastapi.testclient import TestClient

from src.guardrails import _hits, check_rate_limit
from src.main import app
from src.xiangqi.puzzles import PUZZLES, get_puzzle, solution_lines_of
from src.xiangqi.rules import XiangqiGame, legal_moves

client = TestClient(app)


def _rate_request(path: str, session: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "query_string": b"",
            "headers": [(b"x-session-id", session.encode())],
            "client": ("203.0.113.11", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


def test_solution_is_or_not_sequence():
    lines = solution_lines_of(get_puzzle("pawn_side_d8"))
    assert lines == [["e8d8"], ["e8f8"]]


def test_all_solution_first_moves_legal():
    for p in PUZZLES:
        game = XiangqiGame()
        game.reset(p["fen"])
        legal = {m.uci for m in legal_moves(game.board, game.turn)}
        for line in solution_lines_of(p):
            assert line[0] in legal, f"{p['id']} first move {line[0]} illegal"


def test_multi_answer_either_solves():
    h = {"X-Session-Id": "puzzle-or-1"}
    pid = "pawn_side_d8"
    assert client.post(f"/api/xiangqi/puzzles/{pid}/load", headers=h).status_code == 200
    r = client.post(f"/api/xiangqi/puzzles/{pid}/check", json={"uci": "e8f8"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["correct"] is True
    assert body["solved"] is True


def test_defend_block_legal_answers():
    p = get_puzzle("defend_block")
    assert set(p["solution"]) == {"d9e9", "e8d7"}


def test_solution_lines_auto_replies_and_continues():
    h = {"X-Session-Id": "puzzle-lines-1"}
    pid = "rook_chase_two"
    p = get_puzzle(pid)
    assert p and p.get("solution_lines")
    assert client.post(f"/api/xiangqi/puzzles/{pid}/load", headers=h).status_code == 200
    r1 = client.post(f"/api/xiangqi/puzzles/{pid}/check", json={"uci": "a0a9"}, headers=h)
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1["correct"] is True
    assert b1["solved"] is False
    assert "d9d8" in (b1.get("auto_moves") or [])
    # 黑方已被自动续走，轮到红方再走第二步正解
    r2 = client.post(f"/api/xiangqi/puzzles/{pid}/check", json={"uci": "a9a8"}, headers=h)
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["correct"] is True
    assert b2["solved"] is True


def test_wrong_move_does_not_solve_or_puzzle():
    h = {"X-Session-Id": "puzzle-wrong-1"}
    pid = "pawn_side_d8"
    assert client.post(f"/api/xiangqi/puzzles/{pid}/load", headers=h).status_code == 200
    r = client.post(f"/api/xiangqi/puzzles/{pid}/check", json={"uci": "e8e7"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["correct"] is False
    assert body["solved"] is False


def test_session_isolation():
    ha = {"X-Session-Id": "xq-sess-a"}
    hb = {"X-Session-Id": "xq-sess-b"}
    client.post("/api/xiangqi/game/new", json={}, headers=ha)
    client.post("/api/xiangqi/game/new", json={}, headers=hb)
    client.post("/api/xiangqi/game/move", json={"uci": "b0c2"}, headers=ha)
    sa = client.get("/api/xiangqi/game/state", headers=ha).json()
    sb = client.get("/api/xiangqi/game/state", headers=hb).json()
    assert sa["move_count"] == 1
    assert sb["move_count"] == 0
    assert sa["fen"] != sb["fen"]


def test_room_invite_join_and_full():
    create = client.post("/api/xiangqi/rooms", json={"name": "红方", "color": "red"})
    assert create.status_code == 200
    room = create.json()["room_id"]
    join = client.post(f"/api/xiangqi/rooms/{room}/join", json={"name": "黑方"})
    assert join.status_code == 200
    assert join.json()["color"] == "black"
    assert join.json().get("token")
    third = client.post(f"/api/xiangqi/rooms/{room}/join", json={"name": "旁观"})
    assert third.status_code == 409


def test_challenge_load_sets_puzzle_check_path():
    h = {"X-Session-Id": "xq-challenge-1"}
    pid = "mate_rook_a0d0"
    r = client.post(f"/api/xiangqi/challenges/{pid}/load", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body.get("challenge", {}).get("id") == pid
    # 非正解不应通关
    bad = client.post(f"/api/xiangqi/puzzles/{pid}/check", json={"uci": "a0a1"}, headers=h)
    assert bad.status_code == 200
    assert bad.json()["correct"] is False
    ok = client.post(f"/api/xiangqi/puzzles/{pid}/check", json={"uci": "a0d0"}, headers=h)
    assert ok.status_code == 200
    assert ok.json()["correct"] is True
    assert ok.json()["solved"] is True


def test_bad_uci_and_fen_are_400():
    h = {"X-Session-Id": "xq-bad-1"}
    assert client.post("/api/xiangqi/game/move", json={"uci": "z9z9"}, headers=h).status_code == 400
    assert client.post("/api/xiangqi/game/targets", json={"square": "oops"}, headers=h).status_code == 400
    bad_fen = "xnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
    assert client.post("/api/xiangqi/game/load-fen", json={"fen": bad_fen}, headers=h).status_code == 400


def test_health_headers_and_pools():
    h = {"X-Session-Id": "xq-health-pool"}
    assert client.post("/api/xiangqi/game/new", json={}, headers=h).status_code == 200
    r = client.get("/api/xiangqi/health")
    assert r.status_code == 200
    body = r.json()
    assert body["session_pool"]["active"] >= 1
    assert "active" in body["room_pool"]
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert "default-src" in (r.headers.get("Content-Security-Policy") or "")
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"


def test_ai_playback_has_separate_session_rate_bucket():
    _hits.clear()
    req = _rate_request("/api/xiangqi/game/ai-step", "xq-fast-playback")
    # 旧实现 40/min 会截断较快的自动对局。
    for _ in range(100):
        check_rate_limit(req)
