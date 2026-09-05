#!/usr/bin/env python3
"""导出路演 / 提交用证据包：跑希腊赠礼 Demo → 复盘 → 日志摘录。"""
from __future__ import annotations

import asyncio
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "pitch" / "evidence"


async def main() -> None:
    import sys

    sys.path.insert(0, str(ROOT))
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=True)

    from src.llm_logger import recent_logs
    from src.orchestrator import ChessMindOrchestrator

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    meta = {"exported_at": stamp, "demo": "greek_gift"}

    o = ChessMindOrchestrator()
    await o.connect()
    try:
        o.new_game(mode="human_vs_human", with_analysis=True)
        print("running greek_gift council…")
        state = o.load_demo("greek_gift")
        if state.get("error"):
            raise SystemExit(state)
        result = await o.analyze_position(with_analysis=True)
        council = (result.get("analysis") or {}).get("council") or {}
        # analyze_position may nest differently
        if not council and isinstance(result.get("analysis"), dict):
            council = result["analysis"].get("council") or {}
        dg = council.get("disagreement") or {}
        debate = council.get("debate") or {}
        meta["disagreement_score"] = dg.get("disagreement_score")
        meta["debate_triggered"] = debate.get("triggered")
        meta["verdict_move"] = (council.get("verdict") or {}).get("recommended_move")
        meta["llm_model"] = o.get_state().get("llm_model")

        (OUT / "demo_result.json").write_text(
            json.dumps(
                {"state": state, "analysis": result},
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        review = o.get_review()
        (OUT / "review.json").write_text(
            json.dumps(review, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        logs = recent_logs(40)
        (OUT / "llm_calls_excerpt.jsonl").write_text(
            "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in logs),
            encoding="utf-8",
        )
        src_log = ROOT / "logs" / "llm_calls.jsonl"
        if src_log.exists():
            shutil.copy2(src_log, OUT / "llm_calls.full.jsonl")

        (OUT / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        storyboard = OUT / "STORYBOARD.md"
        storyboard.write_text(
            "\n".join(
                [
                    "# 路演证据包",
                    "",
                    f"- 导出时间（UTC）：`{stamp}`",
                    f"- 模型：`{meta.get('llm_model')}`",
                    f"- 争议度：`{meta.get('disagreement_score')}`",
                    f"- 辩论触发：`{meta.get('debate_triggered')}`",
                    f"- 仲裁着法：`{meta.get('verdict_move')}`",
                    "",
                    "正式提交请另用 QuickTime 按 `docs/COMPETE.md` 录屏，并将本目录与视频一并打包。",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        print(f"wrote {OUT}")
    finally:
        o.close()


if __name__ == "__main__":
    asyncio.run(main())
