#!/usr/bin/env bash
# 无 LLM Key 也可跑的上线冒烟：健康检查 + 新对局 + 走子 + 闯关列表
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BASE="${SMOKE_BASE:-http://127.0.0.1:8000}"

echo "== health =="
curl -sf "$BASE/api/health" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert "llm_enabled" in d; print("ok", d.get("product"), "stockfish=", d.get("stockfish"))'

echo "== new game =="
curl -sf -X POST "$BASE/api/game/new" \
  -H 'Content-Type: application/json' \
  -d '{"mode":"human_vs_human","with_analysis":false}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d.get("fen"); print("fen ok")'

echo "== move =="
curl -sf -X POST "$BASE/api/game/move" \
  -H 'Content-Type: application/json' \
  -d '{"uci":"e2e4","with_analysis":false}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); assert "fen" in d or d.get("move"); print("move ok")'

echo "== challenges =="
curl -sf "$BASE/api/challenges" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert len(d.get("levels") or [])>=1; print("levels", len(d["levels"]))'

echo "== library =="
curl -sf "$BASE/api/library" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d.get("items") or d.get("library") or isinstance(d,list); print("library ok")'

echo "SMOKE PASS"
