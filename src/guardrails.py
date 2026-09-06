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


_lock = Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)

# 贵 / 写路径：更严格一点
_EXPENSIVE_PREFIXES = (
    "/api/game/move",
    "/api/game/ai-step",
    "/api/game/analyze-position",
    "/api/game/post-review",
    "/api/demos/",
    "/api/vision/",
    "/api/analyze/pgn",
    "/api/library/step",
)


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
    if path == "/api/health" and request.query_params.get("ping_llm") not in ("1", "true", "True"):
        return

    ip = client_ip(request)
    now = time.monotonic()
    window = max(1, RATE_LIMIT_WINDOW_SEC)
    base = max(1, RATE_LIMIT_BURST)
    limit = max(1, base // 3) if any(path.startswith(p) for p in _EXPENSIVE_PREFIXES) else base
    if path == "/api/health" and request.query_params.get("ping_llm") in ("1", "true", "True"):
        limit = max(1, base // 5)

    key = f"{ip}:{path.split('/')[2] if path.count('/') >= 2 else path}"
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
    """浏览器本地身份：历史读写必须带 X-Owner-Id。"""
    owner = (request.headers.get("x-owner-id") or "").strip()
    if len(owner) < 8 or len(owner) > 128:
        raise HTTPException(
            status_code=401,
            detail="需要有效的 X-Owner-Id（本机身份，至少 8 字符）",
        )
    return owner
