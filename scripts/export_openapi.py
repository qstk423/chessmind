#!/usr/bin/env python3
"""导出冻结的 OpenAPI 快照到 docs/openapi.json。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.main import app  # noqa: E402

OUT = ROOT / "docs" / "openapi.json"
CORE_PATHS = (
    "/api/health",
    "/api/visitor",
    "/api/game/new",
    "/api/game/move",
    "/api/game/state",
    "/api/games",
    "/api/challenges",
    "/api/rooms",
)


def main() -> None:
    spec = app.openapi()
    missing = [p for p in CORE_PATHS if p not in spec.get("paths", {})]
    if missing:
        raise SystemExit(f"OpenAPI 缺少核心路径: {missing}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(spec.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
