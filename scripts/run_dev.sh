#!/usr/bin/env bash
# 本机开发：只保留一个端口，避免旧 uvicorn 僵尸导致 404 / 旧代码。
set -euo pipefail
cd "$(dirname "$0")/.."

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-1}"

if [[ ! -x .venv/bin/python ]]; then
  echo "缺少 .venv，请先: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

pids="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [[ -n "$pids" ]]; then
  echo "停止旧进程 $PORT: $pids"
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null || true
  sleep 1
  leftovers="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$leftovers" ]]; then
    # shellcheck disable=SC2086
    kill -9 $leftovers 2>/dev/null || true
    sleep 0.5
  fi
fi

echo "启动 ChessCouncil → http://${HOST}:${PORT}/ （RELOAD=${RELOAD}）"
extra=()
if [[ "$RELOAD" == "1" || "$RELOAD" == "true" ]]; then
  extra+=(--reload)
fi
exec .venv/bin/python -m uvicorn src.main:app --host "$HOST" --port "$PORT" "${extra[@]}"
