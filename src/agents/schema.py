"""ChessCouncil Agent 结构化意见：解析、校验、默认值兜底。"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

AGENT_IDS = ("tactical", "strategic", "risk", "coach", "arbiter")


@dataclass
class AgentOpinion:
    agent: str
    recommended_move: str | None = None
    alternative_moves: list[str] = field(default_factory=list)
    confidence: float = 0.5
    evaluation: float = 0.0  # 兵单位，正=白优（与引擎白方视角对齐）
    risk: float = 0.5
    summary: str = ""
    reasoning_points: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    # 元数据
    parse_ok: bool = True
    raw_text: str = ""
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def _clamp01(v: Any, default: float = 0.5) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, x))


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _as_str_list(v: Any, limit: int = 6) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        parts = [p.strip() for p in re.split(r"[,，;；\n]", v) if p.strip()]
        return parts[:limit]
    if isinstance(v, list):
        out = []
        for item in v:
            s = str(item).strip()
            if s:
                out.append(s)
            if len(out) >= limit:
                break
        return out
    return []


def extract_json_object(text: str) -> dict[str, Any] | None:
    """从模型回复中提取第一个 JSON 对象。"""
    if not text:
        return None
    text = text.strip()
    # 直接整段 JSON
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # ```json ... ```
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        try:
            obj = json.loads(fence.group(1))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    # 括号匹配找最大对象
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                chunk = text[start : i + 1]
                try:
                    obj = json.loads(chunk)
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    break
    return None


def normalize_move_token(move: str | None) -> str | None:
    if not move:
        return None
    s = str(move).strip()
    if not s or s.lower() in {"none", "null", "n/a", "-", "无", "暂无"}:
        return None
    # 去掉多余注释
    s = s.split()[0].strip(".,;:，。；：")
    return s or None


def validate_opinion(agent_id: str, data: dict[str, Any] | None, raw_text: str = "") -> AgentOpinion:
    """校验并补齐字段；永不抛异常。"""
    if not data:
        summary = (raw_text or "").strip()[:400] or "（未能解析结构化意见）"
        logger.warning("agent=%s JSON parse failed", agent_id)
        return AgentOpinion(
            agent=agent_id,
            summary=summary,
            parse_ok=False,
            raw_text=raw_text,
            fallback_reason="json_parse_failed",
            confidence=0.3,
            risk=0.5,
        )

    rec = normalize_move_token(data.get("recommended_move"))
    alts = [normalize_move_token(x) for x in _as_str_list(data.get("alternative_moves"))]
    alts = [a for a in alts if a and a != rec][:5]

    summary = str(data.get("summary") or "").strip()
    if not summary and raw_text:
        summary = raw_text.strip()[:400]

    opinion = AgentOpinion(
        agent=str(data.get("agent") or agent_id),
        recommended_move=rec,
        alternative_moves=alts,
        confidence=_clamp01(data.get("confidence"), 0.5),
        evaluation=_as_float(data.get("evaluation"), 0.0),
        risk=_clamp01(data.get("risk"), 0.5),
        summary=summary or "（无摘要）",
        reasoning_points=_as_str_list(data.get("reasoning_points"), limit=8),
        concerns=_as_str_list(data.get("concerns"), limit=6),
        parse_ok=True,
        raw_text=raw_text,
        fallback_reason=None,
    )
    # 强制 agent id 规范
    if opinion.agent not in AGENT_IDS:
        opinion.agent = agent_id
    return opinion


def opinion_from_raw(agent_id: str, raw_text: str) -> AgentOpinion:
    data = extract_json_object(raw_text)
    return validate_opinion(agent_id, data, raw_text=raw_text)


def fallback_opinion(agent_id: str, reason: str, summary: str = "") -> AgentOpinion:
    return AgentOpinion(
        agent=agent_id,
        summary=summary or f"（{agent_id} 不可用：{reason}）",
        parse_ok=False,
        fallback_reason=reason,
        confidence=0.2,
        risk=0.5,
    )


JSON_OUTPUT_RULES = """
你必须只输出一个 JSON 对象（不要 Markdown 代码块以外的说明文字），字段如下：
{
  "agent": "<角色id>",
  "recommended_move": "SAN着法或null",
  "alternative_moves": ["SAN1", "SAN2"],
  "confidence": 0.0到1.0,
  "evaluation": 以兵为单位的局面评估（正数偏白优，负数偏黑优，尽量贴近引擎）,
  "risk": 0.0到1.0（你推荐方案的风险）,
  "summary": "一两句中文摘要",
  "reasoning_points": ["要点1", "要点2"],
  "concerns": ["顾虑1"]
}
规则：
- recommended_move 尽量用标准 SAN；若无明显建议可为 null
- confidence / risk 必须是 0~1 数字
- 禁止编造棋盘上不存在的子力；必须以给定结构化事实与引擎信息为准
""".strip()
