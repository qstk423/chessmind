"""无外部 Key 的 API 冒烟（TestClient）。"""
from __future__ import annotations

from contextvars import copy_context

import chess
from fastapi.testclient import TestClient

from src.config import PGN_MAX_PLIES
from src.council.review import compute_accuracy
from src.llm_logger import log_llm_call, set_context
from src.main import app
from src.storage import delete_game, upsert_game

client = TestClient(app)


def _headers(session: str, owner: str = "owner_smoke_test_01") -> dict[str, str]:
    return {
        "X-Session-Id": session,
        "X-Owner-Id": owner,
        "Content-Type": "application/json",
    }


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert "llm_enabled" in body
    assert "llm_model" in body


def test_new_game_and_move_same_session():
    h = _headers("smoke_sess_move")
    r = client.post(
        "/api/game/new",
        json={"mode": "human_vs_human", "with_analysis": False},
        headers=h,
    )
    assert r.status_code == 200
    fen0 = r.json().get("fen")
    assert fen0
    r2 = client.post(
        "/api/game/move",
        json={"uci": "e2e4", "with_analysis": False},
        headers=h,
    )
    assert r2.status_code == 200
    body = r2.json()
    assert (body.get("move") or {}).get("number") == 1 or body.get("move_count") == 1
    fen1 = body.get("fen") or (body.get("state") or {}).get("fen")
    assert fen1 and fen1 != fen0
    state = client.get("/api/game/state", headers=h).json()
    assert state.get("move_count") == 1
    assert "4P3" in state["fen"] or state["fen"].startswith("rnbqkbnr/pppppppp/8/8/4P3")


def test_session_isolation():
    ha = _headers("smoke_sess_a", "owner_smoke_a_______")
    hb = _headers("smoke_sess_b", "owner_smoke_b_______")
    client.post("/api/game/new", json={"mode": "human_vs_human", "with_analysis": False}, headers=ha)
    client.post("/api/game/new", json={"mode": "human_vs_human", "with_analysis": False}, headers=hb)
    client.post("/api/game/move", json={"uci": "e2e4", "with_analysis": False}, headers=ha)
    fa = client.get("/api/game/state", headers=ha).json()
    fb = client.get("/api/game/state", headers=hb).json()
    assert fa["move_count"] == 1
    assert fb["move_count"] == 0
    assert fa["fen"] != fb["fen"]


def test_history_owner_isolation_and_autosave():
    owner = "owner_hist_iso_aaaa"
    other = "owner_hist_iso_bbbb"
    h = _headers("smoke_hist_sess", owner)
    r = client.post(
        "/api/game/new",
        json={"mode": "human_vs_human", "with_analysis": False},
        headers=h,
    )
    assert r.status_code == 200
    r2 = client.post(
        "/api/game/move",
        json={"uci": "e2e4", "with_analysis": False},
        headers=h,
    )
    assert r2.status_code == 200
    saved = (r2.json().get("saved") or {}).get("id")
    assert saved
    mine = client.get("/api/games?limit=20", headers={"X-Owner-Id": owner})
    assert mine.status_code == 200
    assert any(g["id"] == saved for g in mine.json().get("games") or [])
    assert client.get("/api/games").status_code == 401
    assert client.get(f"/api/games/{saved}", headers={"X-Owner-Id": other}).status_code == 404
    assert client.delete(f"/api/games/{saved}", headers={"X-Owner-Id": other}).status_code == 404
    assert client.delete(f"/api/games/{saved}", headers={"X-Owner-Id": owner}).status_code == 200


def test_adopt_orphans_forbidden_for_normal_user():
    upsert_game(
        game_id="orphan_smoke_001",
        mode="human_vs_human",
        title="orphan",
        fen_current="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        owner_id=None,
    )
    owner = "owner_orphan_claim_x"
    r = client.get(
        "/api/games?limit=5&adopt_orphans=1",
        headers={"X-Owner-Id": owner},
    )
    assert r.status_code == 403
    delete_game("orphan_smoke_001")


def test_game_new_invalid_json_is_422():
    r = client.post(
        "/api/game/new",
        content=b"{not-json",
        headers={
            "Content-Type": "application/json",
            "X-Session-Id": "smoke_422",
            "X-Owner-Id": "owner_smoke_422____",
        },
    )
    assert r.status_code == 422


def test_llm_contextvars_isolation():
    results: list[tuple[str | None, int | None]] = []

    def work(gid: str, n: int) -> None:
        set_context(game_id=gid, move_number=n)
        rec = log_llm_call(agent="smoke", success=True, latency_ms=1.0)
        results.append((rec.get("game_id"), rec.get("move_number")))

    copy_context().run(work, "gameAAA", 1)
    copy_context().run(work, "gameBBB", 2)
    assert results == [("gameAAA", 1), ("gameBBB", 2)]


def test_challenges_list():
    r = client.get("/api/challenges")
    assert r.status_code == 200
    levels = r.json().get("levels") or []
    assert len(levels) >= 1


def test_accuracy_helper():
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
    board = chess.Board()
    sans = []
    while len(sans) <= PGN_MAX_PLIES + 2:
        legal = list(board.legal_moves)
        if not legal:
            break
        mv = legal[0]
        sans.append(board.san(mv))
        board.push(mv)
    parts = []
    for i, san in enumerate(sans):
        if i % 2 == 0:
            parts.append(f"{i // 2 + 1}.")
        parts.append(san)
    pgn = " ".join(parts)
    r = client.post(
        "/api/analyze/pgn",
        json={"pgn": pgn},
        headers=_headers("smoke_pgn"),
    )
    assert r.status_code == 400
    assert "上限" in str(r.json().get("detail", ""))
