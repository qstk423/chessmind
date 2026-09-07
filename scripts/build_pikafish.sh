#!/usr/bin/env bash
# 本机构建 Pikafish（中国象棋 NNUE 引擎，对标 Stockfish）。
# 用法：./scripts/build_pikafish.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/engines/Pikafish"

mkdir -p "$ROOT/engines"
if [[ ! -d "$DEST/.git" ]]; then
  git clone --depth 1 https://github.com/official-pikafish/Pikafish.git "$DEST"
fi

cd "$DEST/src"
# Apple Silicon / 一般 macOS：优先 apple-silicon，失败再试 build_profile=native
if [[ "$(uname -s)" == "Darwin" ]] && [[ "$(uname -m)" == "arm64" ]]; then
  make -j"$(sysctl -n hw.ncpu)" build ARCH=apple-silicon
else
  make -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)" build ARCH=native
fi

BIN="$DEST/src/pikafish"
NNUE="$DEST/src/pikafish.nnue"
if [[ ! -x "$BIN" ]]; then
  echo "构建失败：找不到 $BIN" >&2
  exit 1
fi
if [[ ! -f "$NNUE" ]]; then
  echo "警告：未找到 $NNUE，引擎启动可能失败。请按 Pikafish 文档下载官方 NNUE。" >&2
fi

echo "OK: $BIN"
echo "可在 .env 设置：PIKAFISH_PATH=$BIN"
echo "或什么都不设——服务会自动探测该路径。"
