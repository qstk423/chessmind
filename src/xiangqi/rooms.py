"""联机房间管理。"""
from __future__ import annotations

import secrets
import string
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from src.xiangqi.rules import XiangqiGame

_MAX_ROOMS = 200
_ROOM_TTL_SEC = 6 * 3600


def _room_id() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


@dataclass
class Seat:
    token: str
    color: str
    name: str
    ws: WebSocket | None = None
    connected: bool = False


@dataclass
class Room:
    room_id: str
    game: XiangqiGame = field(default_factory=XiangqiGame)
    seats: dict[str, Seat | None] = field(default_factory=lambda: {"red": None, "black": None})
    touched_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.touched_at = time.time()

    def public_state(self) -> dict[str, Any]:
        snap = self.game.snapshot()
        return {
            "room_id": self.room_id,
            "fen": snap["fen"],
            "turn": snap["turn"],
            "move_count": snap["move_count"],
            "is_game_over": snap["is_game_over"],
            "result": snap["result"],
            "in_check": snap["in_check"],
            "moves": snap["moves"],
            "legal_uci": snap["legal_uci"],
            "board": snap["board"],
            "seats": {
                color: (
                    {
                        "name": seat.name,
                        "connected": seat.connected,
                    }
                    if seat
                    else None
                )
                for color, seat in self.seats.items()
            },
            "both_ready": all(self.seats.values()),
        }

    def seat_by_token(self, token: str) -> Seat | None:
        for seat in self.seats.values():
            if seat and seat.token == token:
                return seat
        return None

    async def broadcast(self, payload: dict):
        for seat in self.seats.values():
            if seat and seat.ws and seat.connected:
                try:
                    await seat.ws.send_json(payload)
                except Exception:
                    seat.connected = False


class RoomManager:
    def __init__(self):
        self.rooms: dict[str, Room] = {}

    def _purge(self) -> None:
        now = time.time()
        dead = [rid for rid, room in self.rooms.items() if now - room.touched_at > _ROOM_TTL_SEC]
        for rid in dead:
            self.rooms.pop(rid, None)
        while len(self.rooms) > _MAX_ROOMS:
            oldest = min(self.rooms.values(), key=lambda r: r.touched_at)
            self.rooms.pop(oldest.room_id, None)

    def stats(self) -> dict[str, int]:
        self._purge()
        return {"active": len(self.rooms), "max": _MAX_ROOMS}

    def create(self, name: str = "玩家", color: str = "red") -> dict:
        self._purge()
        if len(self.rooms) >= _MAX_ROOMS:
            raise RuntimeError("房间过多，请稍后再试")
        color = "red" if color not in {"red", "black"} else color
        room_id = _room_id()
        while room_id in self.rooms:
            room_id = _room_id()
        room = Room(room_id=room_id)
        token = secrets.token_urlsafe(12)
        room.seats[color] = Seat(token=token, color=color, name=name or "玩家")
        room.touch()
        self.rooms[room_id] = room
        return {
            "room_id": room_id,
            "token": token,
            "color": color,
            "name": name or "玩家",
            "state": room.public_state(),
        }

    def join(self, room_id: str, name: str = "玩家") -> dict:
        self._purge()
        room = self.rooms.get(room_id.upper())
        if not room:
            raise KeyError("房间不存在")
        open_color = next((c for c, s in room.seats.items() if s is None), None)
        if not open_color:
            raise RuntimeError("房间已满")
        token = secrets.token_urlsafe(12)
        room.seats[open_color] = Seat(token=token, color=open_color, name=name or "玩家")
        room.touch()
        return {
            "room_id": room.room_id,
            "token": token,
            "color": open_color,
            "name": name or "玩家",
            "state": room.public_state(),
        }

    def get(self, room_id: str) -> Room | None:
        self._purge()
        room = self.rooms.get(room_id.upper())
        if room:
            room.touch()
        return room

    def play_move(self, room: Room, token: str, uci: str) -> dict:
        seat = room.seat_by_token(token)
        if not seat:
            return {"error": "无效身份"}
        if room.game.result:
            return {"error": "对局已结束"}
        if seat.color != room.game.turn:
            return {"error": f"现在是{'红' if room.game.turn == 'red' else '黑'}方走棋"}
        try:
            entry = room.game.play_uci(uci)
        except ValueError as exc:
            return {"error": str(exc)}
        room.touch()
        return {"ok": True, "move": entry, "state": room.public_state()}

    def reset(self, room: Room, token: str) -> dict:
        seat = room.seat_by_token(token)
        if not seat:
            return {"error": "无效身份"}
        room.game.reset()
        room.touch()
        return {"ok": True, "state": room.public_state()}


room_manager = RoomManager()
