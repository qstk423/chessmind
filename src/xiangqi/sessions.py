"""按浏览器会话隔离的对弈盘面（避免全局单例互踩）。"""
from __future__ import annotations

import secrets
import time
from threading import Lock

from src.xiangqi.rules import XiangqiGame

_MAX_SESSIONS = 500
_TTL_SEC = 6 * 3600


class GameSessions:
    def __init__(self) -> None:
        self._lock = Lock()
        self._games: dict[str, XiangqiGame] = {}
        self._touched: dict[str, float] = {}
        self._library: dict[str, dict] = {}
        self._settings: dict[str, dict] = {}

    def _purge(self) -> None:
        now = time.time()
        dead = [sid for sid, ts in self._touched.items() if now - ts > _TTL_SEC]
        for sid in dead:
            self._games.pop(sid, None)
            self._touched.pop(sid, None)
            self._library.pop(sid, None)
            self._settings.pop(sid, None)
        while len(self._games) > _MAX_SESSIONS:
            oldest = min(self._touched, key=self._touched.get)
            self._games.pop(oldest, None)
            self._touched.pop(oldest, None)
            self._library.pop(oldest, None)
            self._settings.pop(oldest, None)

    def stats(self) -> dict[str, int]:
        with self._lock:
            self._purge()
            return {"active": len(self._games), "max": _MAX_SESSIONS}

    def resolve(self, session_id: str | None) -> tuple[str, XiangqiGame]:
        with self._lock:
            self._purge()
            sid = (session_id or "").strip()
            if not sid:
                sid = secrets.token_urlsafe(16)
            if sid not in self._games:
                self._games[sid] = XiangqiGame()
            self._touched[sid] = time.time()
            return sid, self._games[sid]

    def library_of(self, session_id: str) -> dict:
        with self._lock:
            return self._library.setdefault(
                session_id, {"id": None, "moves": [], "index": 0, "meta": None}
            )

    def set_library(self, session_id: str, data: dict) -> None:
        with self._lock:
            self._library[session_id] = data
            self._touched[session_id] = time.time()

    def settings_of(self, session_id: str) -> dict:
        with self._lock:
            return dict(
                self._settings.setdefault(
                    session_id,
                    {
                        "mode": "human_vs_human",
                        "human_color": "red",
                        "red_ai": "engine",
                        "strength": "normal",
                    },
                )
            )

    def set_settings(self, session_id: str, data: dict) -> None:
        with self._lock:
            cur = self._settings.setdefault(session_id, {})
            cur.update(data)
            self._touched[session_id] = time.time()


sessions = GameSessions()
