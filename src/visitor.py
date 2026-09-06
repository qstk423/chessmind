"""访客身份：可选 HMAC 签名的 X-Owner-Id。"""
from __future__ import annotations

import hmac
import secrets
import time
from hashlib import sha256

from src.config import OWNER_SECRET

_SIG_LEN = 32
_MAX_AGE_SEC = 365 * 24 * 3600  # 令牌有效期一年；可重新签发


def owner_signing_enabled() -> bool:
    return bool(OWNER_SECRET)


def mint_owner_id() -> str:
    """签发本机访客身份。未配置 OWNER_SECRET 时仍返回可校验格式的令牌。"""
    raw = secrets.token_urlsafe(18)
    ts = int(time.time())
    payload = f"v1.{raw}.{ts}"
    if not OWNER_SECRET:
        return payload
    sig = hmac.new(OWNER_SECRET.encode("utf-8"), payload.encode("utf-8"), sha256).hexdigest()[:_SIG_LEN]
    return f"{payload}.{sig}"


def verify_owner_id(owner: str) -> str:
    """
    校验 X-Owner-Id。
    - 未配置 OWNER_SECRET：接受 8–128 字符任意本机 id（兼容旧客户端），也接受 v1. 格式
    - 已配置：必须为 v1.<id>.<ts>.<sig> 且签名匹配、未过期
    """
    owner = (owner or "").strip()
    if not owner or len(owner) < 8 or len(owner) > 200:
        raise ValueError("需要有效的 X-Owner-Id")

    if not OWNER_SECRET:
        return owner

    parts = owner.split(".")
    if len(parts) != 4 or parts[0] != "v1":
        raise ValueError("需要由 /api/visitor 签发的访客令牌")
    payload = ".".join(parts[:3])
    sig = parts[3]
    expect = hmac.new(OWNER_SECRET.encode("utf-8"), payload.encode("utf-8"), sha256).hexdigest()[:_SIG_LEN]
    if not hmac.compare_digest(sig, expect):
        raise ValueError("访客令牌签名无效")
    try:
        ts = int(parts[2])
    except ValueError as e:
        raise ValueError("访客令牌时间戳无效") from e
    if abs(time.time() - ts) > _MAX_AGE_SEC:
        raise ValueError("访客令牌已过期，请重新获取")
    return owner
