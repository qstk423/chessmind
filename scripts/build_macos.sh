#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This build script requires macOS." >&2
  exit 1
fi

python_bin="${PYTHON_BIN:-$project_root/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  echo "Python virtual environment is missing: $python_bin" >&2
  exit 1
fi

# PyInstaller's archive is read lazily. Replacing an open .app can corrupt
# imports in the still-running process (zlib.error during review/AI calls).
running_files="$(lsof -nP -c ChessCouncil 2>/dev/null || true)"
for running_app in \
  "$project_root/dist/ChessCouncil.app/Contents/MacOS/ChessCouncil" \
  "$project_root/dist/ChessCouncil-Mac/ChessCouncil.app/Contents/MacOS/ChessCouncil"; do
  if [[ "$running_files" == *"$running_app"* ]]; then
    echo "ChessCouncil is still running from $running_app. Quit it before rebuilding." >&2
    exit 1
  fi
done

if [[ "${1:-}" != "--skip-tests" ]]; then
  "$python_bin" -m pytest -q tests/test_api_smoke.py tests/xiangqi/ tests/test_final_fixes.py tests/test_desktop_launcher.py
fi

vendor_dir="$project_root/build/stockfish-macos"
archive="$vendor_dir/stockfish-19-upstream.tar.gz"
stockfish_url="https://github.com/official-stockfish/Stockfish/releases/download/sf_19/stockfish-macos-universal.tar.gz"
stockfish_sha256="a1f0e3bcc5a6927a11fe6fc8e54a779754645f3c2bae2cf13420fd1957adaa77"
mkdir -p "$vendor_dir"
if [[ ! -f "$archive" ]]; then
  curl -fL --retry 2 -o "$archive" "$stockfish_url"
fi
actual_sha256="$(shasum -a 256 "$archive" | awk '{print $1}')"
if [[ "$actual_sha256" != "$stockfish_sha256" ]]; then
  echo "Stockfish archive checksum mismatch." >&2
  exit 1
fi

tar -xzf "$archive" -C "$vendor_dir"
engine="$vendor_dir/stockfish/stockfish-macos-universal"
license="$vendor_dir/stockfish/Copying.txt"
if [[ ! -x "$engine" || ! -f "$license" ]]; then
  echo "Stockfish executable or license missing from archive." >&2
  exit 1
fi
mkdir -p "$vendor_dir/bin"
cp "$engine" "$vendor_dir/bin/stockfish"
pikafish_root="$project_root/engines/Pikafish"
pikafish="$pikafish_root/src/pikafish"
pikafish_nnue="$pikafish_root/src/pikafish.nnue"
pikafish_license="$pikafish_root/Copying.txt"
if [[ ! -x "$pikafish" || ! -f "$pikafish_nnue" || ! -f "$pikafish_license" ]]; then
  echo "Local Pikafish executable, NNUE or license is missing." >&2
  exit 1
fi
mkdir -p "$project_root/build/pikafish-macos"
pikafish_source="$project_root/build/pikafish-macos/pikafish-source.tar.gz"
tar -czf "$pikafish_source" -C "$pikafish_root" \
  --exclude='./.git' --exclude='./src/pikafish' .
sips -s format icns frontend/chess/icons/icon-512.png --out "$vendor_dir/ChessCouncil.icns" >/dev/null

"$python_bin" -m PyInstaller \
  --noconfirm --clean --onedir --windowed \
  --name ChessCouncil \
  --icon "$vendor_dir/ChessCouncil.icns" \
  --osx-bundle-identifier com.chessmind.chesscouncil \
  --collect-submodules uvicorn \
  --hidden-import webview.platforms.cocoa \
  --add-data "frontend:frontend" \
  --add-binary "$vendor_dir/bin/stockfish:bin" \
  --add-binary "$pikafish:bin" \
  --add-data "$pikafish_nnue:bin" \
  --add-data "$license:third_party/stockfish" \
  --add-data "$archive:third_party/stockfish" \
  --add-data "$pikafish_license:third_party/pikafish" \
  --add-data "$pikafish_source:third_party/pikafish" \
  desktop/launcher.py

app="$project_root/dist/ChessCouncil.app"
if [[ ! -d "$app" ]]; then
  echo "ChessCouncil.app was not generated." >&2
  exit 1
fi

test_data="$(mktemp -d)"
CHESSCOUNCIL_DATA_DIR="$test_data" "$app/Contents/MacOS/ChessCouncil" --self-test

package="$project_root/dist/ChessCouncil-Mac"
mkdir -p "$package"
if [[ -d "$package/ChessCouncil.app" ]]; then
  rm -rf "$package/ChessCouncil.app"
fi
ditto "$app" "$package/ChessCouncil.app"
codesign --verify --deep --strict -v "$package/ChessCouncil.app"
cp desktop/ChessCouncil.env.example "$package/ChessCouncil.env.example"
cp desktop/README-Mac.md "$package/使用说明.md"
ditto -c -k --sequesterRsrc --keepParent "$package" "$project_root/dist/ChessCouncil-Mac.zip"
echo "Built and verified: $project_root/dist/ChessCouncil-Mac.zip"
