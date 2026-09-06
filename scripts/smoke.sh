#!/usr/bin/env bash
# 无 LLM Key 也可跑的上线冒烟：健康检查 + 同会话新对局/走子 + 闯关列表
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BASE="${SMOKE_BASE:-http://127.0.0.1:8000}"
SID="${SMOKE_SESSION:-smoke_shell_$(date +%s)}"
OID="${SMOKE_OWNER:-owner_smoke_shell_01}"

hdr=(-H "Content-Type: application/json" -H "X-Session-Id: $SID" -H "X-Owner-Id: $OID")

echo "== health =="
curl -sf "$BASE/api/health" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert "llm_enabled" in d; print("ok", d.get("product"), "stockfish=", d.get("stockfish"))'

echo "== new game =="
FEN0=$(curl -sf -X POST "$BASE/api/game/new" "${hdr[@]}" \
  -d '{"mode":"human_vs_human","with_analysis":false}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d.get("fen"); print(d["fen"])')
echo "fen0 ok"

echo "== move (same session) =="
curl -sf -X POST "$BASE/api/game/move" "${hdr[@]}" \
  -d '{"uci":"e2e4","with_analysis":false}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); n=(d.get("move") or {}).get("number"); assert n==1 or d.get("move_count")==1; print("move ok", n or d.get("move_count"))'

echo "== state same session =="
curl -sf "$BASE/api/game/state" -H "X-Session-Id: $SID" -H "X-Owner-Id: $OID" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d.get("move_count")==1; print("state ok", d["move_count"])'

echo "== challenges =="
curl -sf "$BASE/api/challenges" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert len(d.get("levels") or [])>=1; print("levels", len(d["levels"]))'

echo "== library =="
curl -sf "$BASE/api/library" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d.get("items") or d.get("library") or isinstance(d,list); print("library ok")'

echo "SMOKE PASS (session=$SID)"
