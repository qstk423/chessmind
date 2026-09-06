"""LLM 调用日志——写入 JSONL，供大赛「模型调用证明」使用。"""
from __future__ import annotations

import json
import threading
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import LLM_LOG_PATH, LLM_MODEL

_lock = threading.Lock()
_game_id: ContextVar[str | None] = ContextVar("llm_game_id", default=None)
_move_number: ContextVar[int | None] = ContextVar("llm_move_number", default=None)


def set_context(*, game_id: str | None = None, move_number: int | None = None) -> None:
    """绑定当前对局上下文（按异步/任务隔离，避免多用户串局）。"""
    if game_id is not None:
        _game_id.set(game_id)
    if move_number is not None:
        _move_number.set(move_number)


def new_game_id() -> str:
    gid = uuid.uuid4().hex[:12]
    set_context(game_id=gid, move_number=0)
    return gid


def log_llm_call(
    *,
    agent: str,
    model: str | None = None,
    success: bool,
    latency_ms: float,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """追加一条调用记录到 JSONL 文件。"""
    usage = {}
    if prompt_tokens is not None:
        usage["prompt_tokens"] = prompt_tokens
    if completion_tokens is not None:
        usage["completion_tokens"] = completion_tokens
    if total_tokens is not None:
        usage["total_tokens"] = total_tokens

    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "game_id": _game_id.get(),
        "move_number": _move_number.get(),
        "agent": agent,
        "model": model or LLM_MODEL,
        "success": success,
        "latency_ms": round(latency_ms, 1),
        "usage": usage or None,
        "error": error,
    }
    if extra:
        record["extra"] = extra

    path = Path(LLM_LOG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    return record


def recent_logs(limit: int = 20) -> list[dict[str, Any]]:
    """读取最近 N 条日志（文件不存在则返回空列表）。"""
    path = Path(LLM_LOG_PATH)
    if not path.exists():
        return []
    with _lock:
        lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
