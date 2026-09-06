"""按浏览器会话隔离的对弈编排器（共享 Stockfish / LLM Agent）。"""
from __future__ import annotations

import secrets
import time
from threading import Lock

from src.orchestrator import ChessMindOrchestrator

_MAX_SESSIONS = 200
_TTL_SEC = 6 * 3600


class OrchestratorPool:
    def __init__(self) -> None:
        self.primary = ChessMindOrchestrator()
        self._lock = Lock()
        self._map: dict[str, ChessMindOrchestrator] = {}
        self._touched: dict[str, float] = {}

    def _purge(self) -> None:
        now = time.time()
        dead = [sid for sid, ts in self._touched.items() if now - ts > _TTL_SEC]
        for sid in dead:
            self._map.pop(sid, None)
            self._touched.pop(sid, None)
        while len(self._map) > _MAX_SESSIONS:
            oldest = min(self._touched, key=self._touched.get)
            self._map.pop(oldest, None)
            self._touched.pop(oldest, None)

    def resolve(self, session_id: str | None) -> tuple[str, ChessMindOrchestrator]:
        with self._lock:
            self._purge()
            sid = (session_id or "").strip()
            if not sid:
                sid = secrets.token_urlsafe(16)
            if sid not in self._map:
                orch = ChessMindOrchestrator(share=self.primary)
                orch.session_id = sid
                orch._connected = self.primary._connected
                self._map[sid] = orch
            self._touched[sid] = time.time()
            orch = self._map[sid]
            orch.session_id = sid
            orch._connected = self.primary._connected
            return sid, orch


pool = OrchestratorPool()
# 兼容旧引用：health / lifespan 仍用 primary
orchestrator = pool.primary
