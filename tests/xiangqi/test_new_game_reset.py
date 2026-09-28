"""新对局必须能抢在旧 AI 应着前完成，且旧结果不能落到新棋盘。"""
from __future__ import annotations

import asyncio
import time

import httpx

from src.main import app
from src.xiangqi.ai import choose_move_builtin
from src.xiangqi.rules import XiangqiGame, legal_moves


def test_builtin_hard_search_is_bounded():
    game = XiangqiGame()
    game.play_uci("h2d2")
    started = time.perf_counter()
    uci = choose_move_builtin(game, strength="hard")
    assert uci in {move.uci for move in legal_moves(game.board, game.turn)}
    assert time.perf_counter() - started < 4.0


def test_new_game_discards_inflight_ai_result(monkeypatch):
    async def scenario():
        started = asyncio.Event()
        finish = asyncio.Event()

        async def delayed_choice(game, **_kwargs):
            started.set()
            await finish.wait()
            return {"uci": legal_moves(game.board, game.turn)[0].uci, "source": "engine"}

        monkeypatch.setattr("src.xiangqi.api.routes.choose_move_for_side", delayed_choice)
        headers = {"X-Session-Id": "xq_reset_during_ai_test"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post(
                "/api/xiangqi/game/new",
                json={"mode": "human_vs_ai", "human_color": "red"},
                headers=headers,
            )
            assert created.status_code == 200
            moved = await client.post("/api/xiangqi/game/move", json={"uci": "h2d2"}, headers=headers)
            assert moved.status_code == 200

            ai_task = asyncio.create_task(client.post("/api/xiangqi/game/ai-step", headers=headers))
            await asyncio.wait_for(started.wait(), timeout=2)
            reset = await asyncio.wait_for(
                client.post("/api/xiangqi/game/new", json={"mode": "human_vs_ai"}, headers=headers),
                timeout=2,
            )
            assert reset.status_code == 200
            assert reset.json()["moves"] == []
            finish.set()
            stale = await asyncio.wait_for(ai_task, timeout=2)
            assert stale.status_code == 409
            current = await client.get("/api/xiangqi/game/state", headers=headers)
            assert current.json()["moves"] == []
            assert current.json()["fen"] == XiangqiGame().fen()

    asyncio.run(scenario())
