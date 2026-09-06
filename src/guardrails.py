"""上线护栏：限流、管理口令、昂贵路径识别。"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request

from src.config import (
    ADMIN_TOKEN,
    PUBLIC_DEMO,
    RATE_LIMIT_BURST,
    RATE_LIMIT_WINDOW_SEC,
)
from src.visitor import verify_owner_id

_lock = Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)

# 真正昂贵的分析路径：严格限流（相对 /api 规范路径）。
_EXPENSIVE_PREFIXES = (
    "/api/game/analyze-position",
    "/api/game/post-review",
    "/api/demos/",
    "/api/vision/",
    "/api/analyze/pgn",
)

# 走棋 / 自动播放路径需要支持“极快”档；仍保留会话级上限。
_PLAYBACK_PATHS = {
    "/api/game/move",
    "/api/game/ai-step",
    "/api/library/step",
}


def _canonical_api_path(path: str) -> str:
    """把 /api/chess/*、/api/xiangqi/* 归一成 /api/*，便于共用限流规则。"""
    for prefix in ("/api/chess/", "/api/xiangqi/"):
        if path.startswith(prefix):
            return "/api/" + path[len(prefix) :]
    return path


def _bucket(path: str) -> str:
    """按真实功能分桶，避免所有 /api/game/* 互相挤占额度。"""
    canon = _canonical_api_path(path)
    if canon.startswith("/api/rooms/"):
        if canon.endswith("/move"):
            return "rooms:move"
        if canon.endswith("/reset"):
            return "rooms:reset"
        if canon.endswith("/join"):
            return "rooms:join"
        return "rooms:state"
    return canon


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def check_rate_limit(request: Request) -> None:
    """滑动窗口限流；超限抛 429。"""
    path = request.url.path
    if not path.startswith("/api/"):
        return
    canon = _canonical_api_path(path)
    if canon == "/api/health" and request.query_params.get("ping_llm") not in ("1", "true", "True"):
        return

    ip = client_ip(request)
    now = time.monotonic()
    window = max(1, RATE_LIMIT_WINDOW_SEC)
    base = max(1, RATE_LIMIT_BURST)
    if canon in _PLAYBACK_PATHS or (canon.startswith("/api/rooms/") and canon.endswith("/move")):
        limit = base * 4
    elif any(canon.startswith(p) for p in _EXPENSIVE_PREFIXES):
        limit = max(1, base // 3)
    else:
        limit = base
    if canon == "/api/health" and request.query_params.get("ping_llm") in ("1", "true", "True"):
        limit = max(1, base // 5)

    session = (request.headers.get("x-session-id") or "").strip()[:128] or "anonymous"
    # 棋种写入 key，避免 chess / xiangqi 共用同一桶。
    variant = "xq" if path.startswith("/api/xiangqi") else ("ch" if path.startswith("/api/chess") else "api")
    key = f"{ip}:{session}:{variant}:{_bucket(path)}"
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"请求过于频繁，请稍后再试（{window}s 内最多 {limit} 次）",
            )
        q.append(now)


def require_admin(request: Request) -> None:
    """
    敏感接口：日志 / ping 模型。
    - 未设置 ADMIN_TOKEN：开发期放行；PUBLIC_DEMO=1 时拒绝
    - 已设置：要求 Header X-Admin-Token 或 ?admin_token= 匹配
    """
    token = (ADMIN_TOKEN or "").strip()
    provided = (
        request.headers.get("x-admin-token")
        or request.query_params.get("admin_token")
        or ""
    ).strip()
    if not token:
        if PUBLIC_DEMO:
            raise HTTPException(
                status_code=403,
                detail="公开展示模式已开启，请配置 ADMIN_TOKEN 后再访问敏感接口",
            )
        return
    if provided != token:
        raise HTTPException(status_code=403, detail="需要有效的管理口令（X-Admin-Token）")


def is_admin(request: Request) -> bool:
    """已配置 ADMIN_TOKEN 且口令匹配时为 True；未配置则不算管理员。"""
    token = (ADMIN_TOKEN or "").strip()
    if not token:
        return False
    provided = (
        request.headers.get("x-admin-token")
        or request.query_params.get("admin_token")
        or ""
    ).strip()
    return provided == token


def require_owner_id(request: Request) -> str:
    """浏览器本地身份：历史读写必须带有效 X-Owner-Id。"""
    owner = (request.headers.get("x-owner-id") or "").strip()
    try:
        return verify_owner_id(owner)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
