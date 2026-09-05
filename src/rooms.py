"""联机房间：多人隔离对局（手机互下）。"""
from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import WebSocket

from src.board.game_state import GameState
from src.board.mate_patterns import detect_finale

Color = Literal["white", "black"]


def _code(n: int = 6) -> str:
    # 去掉易混字符
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(n))


@dataclass
class Seat:
    token: str
    color: Color
    name: str
    connected: bool = False
    ws: WebSocket | None = None


@dataclass
class Room:
    id: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    game: GameState = field(default_factory=GameState)
    white: Seat | None = None
    black: Seat | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def touch(self) -> None:
        self.updated_at = time.time()

    def seat_by_token(self, token: str) -> Seat | None:
        for seat in (self.white, self.black):
            if seat and seat.token == token:
                return seat
        return None

    def public_state(self) -> dict[str, Any]:
        g = self.game
        turn = "white" if g.board.turn else "black"
        return {
            "room_id": self.id,
            "fen": g.fen,
            "turn": turn,
            "move_count": g.move_count,
            "is_game_over": g.is_game_over,
            "result": g.result,
            "pgn": g.to_pgn(),
            "legal_moves": [] if g.is_game_over else g.legal_moves(),
            "seats": {
                "white": None
                if not self.white
                else {"name": self.white.name, "connected": self.white.connected},
                "black": None
                if not self.black
                else {"name": self.black.name, "connected": self.black.connected},
            },
            "both_ready": bool(self.white and self.black),
        }

    async def broadcast(self, payload: dict[str, Any], *, except_token: str | None = None) -> None:
        dead: list[Seat] = []
        for seat in (self.white, self.black):
            if not seat or not seat.ws:
                continue
            if except_token and seat.token == except_token:
                continue
            try:
                await seat.ws.send_json(payload)
            except Exception:
                dead.append(seat)
        for seat in dead:
            seat.ws = None
            seat.connected = False


class RoomManager:
    def __init__(self, *, max_rooms: int = 200, ttl_sec: int = 2 * 60 * 60):
        self.rooms: dict[str, Room] = {}
        self.max_rooms = max_rooms
        self.ttl_sec = ttl_sec
        self._lock = asyncio.Lock()

    def _purge_expired(self) -> None:
        now = time.time()
        dead = [rid for rid, r in self.rooms.items() if now - r.updated_at > self.ttl_sec]
        for rid in dead:
            self.rooms.pop(rid, None)

    async def create(self, *, host_name: str = "白方", host_color: Color = "white") -> dict[str, Any]:
        async with self._lock:
            self._purge_expired()
            if len(self.rooms) >= self.max_rooms:
                raise RuntimeError("房间已满，请稍后再试")
            for _ in range(20):
                rid = _code()
                if rid not in self.rooms:
                    break
            else:
                raise RuntimeError("无法分配房间号")
            room = Room(id=rid)
            token = secrets.token_urlsafe(16)
            seat = Seat(token=token, color=host_color, name=host_name or ("白方" if host_color == "white" else "黑方"))
            if host_color == "white":
                room.white = seat
            else:
                room.black = seat
            self.rooms[rid] = room
            return {
                "room_id": rid,
                "token": token,
                "color": host_color,
                "name": seat.name,
                "state": room.public_state(),
            }

    async def join(self, room_id: str, *, name: str = "黑方") -> dict[str, Any]:
        async with self._lock:
            self._purge_expired()
            room = self.rooms.get(room_id.upper())
            if not room:
                raise KeyError("房间不存在或已过期")
            room.touch()
            if room.white and room.black:
                raise RuntimeError("房间已满（两人）")
            color: Color = "black" if room.white and not room.black else "white"
            token = secrets.token_urlsafe(16)
            seat = Seat(token=token, color=color, name=name or ("黑方" if color == "black" else "白方"))
            if color == "white":
                room.white = seat
            else:
                room.black = seat
            return {
                "room_id": room.id,
                "token": token,
                "color": color,
                "name": seat.name,
                "state": room.public_state(),
            }

    def get(self, room_id: str) -> Room | None:
        return self.rooms.get(room_id.upper())

    async def play_move(self, room: Room, token: str, uci: str) -> dict[str, Any]:
        async with room.lock:
            seat = room.seat_by_token(token)
            if not seat:
                return {"error": "无效身份，请重新加入房间"}
            if room.game.is_game_over:
                return {"error": "对局已结束"}
            turn: Color = "white" if room.game.board.turn else "black"
            if seat.color != turn:
                return {"error": f"现在是{'白' if turn == 'white' else '黑'}方走棋"}
            record = room.game.push_move(uci)
            if record is None:
                return {"error": "非法着法"}
            room.touch()
            finale = detect_finale(room.game.board) if room.game.is_game_over else None
            return {
                "ok": True,
                "move": {"san": record.san, "uci": record.uci, "number": record.move_number},
                "finale": finale,
                "state": room.public_state(),
            }

    async def reset_game(self, room: Room, token: str) -> dict[str, Any]:
        async with room.lock:
            seat = room.seat_by_token(token)
            if not seat:
                return {"error": "无效身份"}
            room.game.reset()
            room.touch()
            return {"ok": True, "state": room.public_state()}


room_manager = RoomManager()
