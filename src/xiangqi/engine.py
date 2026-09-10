"""可选 Pikafish UCI 引擎（中国象棋对标 Stockfish 的现成强力引擎）。

优先使用环境变量 PIKAFISH_PATH；否则自动探测仓库内
`engines/Pikafish/src/pikafish`。未安装时降级到内建搜索。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from src.config import PIKAFISH_PATH

_lock = threading.Lock()
_proc: subprocess.Popen[str] | None = None
_available: bool | None = None
_connect_error: str | None = None
_engine_dir: Path | None = None

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CANDIDATES = (
    _PROJECT_ROOT / "engines" / "Pikafish" / "src" / "pikafish",
    _PROJECT_ROOT / "engines" / "pikafish",
    _PROJECT_ROOT / "bin" / "pikafish",
    Path.home() / ".local" / "bin" / "pikafish",
)


def _resolve_path() -> str | None:
    raw = (PIKAFISH_PATH or "").strip()
    if raw and raw != "pikafish":
        p = Path(raw).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return str(p.resolve())
    found = shutil.which(raw or "pikafish")
    if found:
        return found
    for cand in _DEFAULT_CANDIDATES:
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand.resolve())
    return None


def pikafish_available() -> bool:
    global _available
    if _available is not None:
        return _available
    path = _resolve_path()
    _available = bool(path)
    return _available


def pikafish_status() -> dict:
    return {
        "available": pikafish_available(),
        "path": _resolve_path(),
        "error": _connect_error,
        "cwd": str(_engine_dir) if _engine_dir else None,
    }


def _read_until(proc: subprocess.Popen[str], token: str, timeout: float = 12.0) -> list[str]:
    assert proc.stdout is not None
    lines: list[str] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        line = line.rstrip("\r\n")
        if line:
            lines.append(line)
        if line == token or line.startswith(token + " "):
            break
    return lines


def _ensure_engine() -> subprocess.Popen[str]:
    global _proc, _available, _connect_error, _engine_dir
    if _proc and _proc.poll() is None:
        return _proc
    path = _resolve_path()
    if not path:
        _available = False
        raise RuntimeError("未找到 Pikafish 可执行文件")
    engine_path = Path(path)
    _engine_dir = engine_path.parent
    # stderr 必须丢掉，否则 PIPE 缓冲区满会卡死引擎进程
    _proc = subprocess.Popen(
        [str(engine_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        cwd=str(_engine_dir),
    )
    assert _proc.stdin and _proc.stdout
    _proc.stdin.write("uci\n")
    _proc.stdin.flush()
    _read_until(_proc, "uciok")
    # EvalFile 默认相对 cwd 的 pikafish.nnue，cwd 已指向引擎目录
    _proc.stdin.write("setoption name Threads value 2\n")
    _proc.stdin.write("setoption name Hash value 128\n")
    _proc.stdin.write("isready\n")
    _proc.stdin.flush()
    _read_until(_proc, "readyok")
    _available = True
    _connect_error = None
    return _proc


def best_move_pikafish(
    fen: str,
    *,
    depth: int = 18,
    movetime_ms: int | None = None,
) -> str | None:
    """同步问引擎最佳着法；失败返回 None。"""
    with _lock:
        try:
            proc = _ensure_engine()
            assert proc.stdin and proc.stdout
            fen_cmd = fen.strip()
            proc.stdin.write("ucinewgame\n")
            proc.stdin.write("isready\n")
            proc.stdin.flush()
            _read_until(proc, "readyok", timeout=8.0)
            proc.stdin.write(f"position fen {fen_cmd}\n")
            # 用 movetime 保证响应上限，避免深搜拖死 API
            if movetime_ms is None:
                movetime_ms = {
                    8: 200,
                    10: 350,
                    12: 400,
                    14: 600,
                    16: 700,
                    18: 900,
                    20: 1200,
                    22: 1600,
                }.get(int(depth), max(500, int(depth) * 50))
            proc.stdin.write(f"go movetime {int(movetime_ms)}\n")
            proc.stdin.flush()
            best: str | None = None
            deadline = time.monotonic() + max(3.0, movetime_ms / 1000.0 + 2.5)
            while time.monotonic() < deadline:
                line = proc.stdout.readline()
                if not line:
                    break
                line = line.rstrip("\r\n")
                if line.startswith("bestmove"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] not in ("(none)", "0000"):
                        best = parts[1]
                    break
            return best
        except Exception as exc:  # noqa: BLE001
            global _connect_error, _available, _proc
            _connect_error = f"{type(exc).__name__}: {exc}"
            _available = False
            if _proc:
                try:
                    _proc.kill()
                except Exception:
                    pass
            _proc = None
            return None


def close_pikafish() -> None:
    global _proc
    with _lock:
        if _proc:
            try:
                if _proc.stdin:
                    _proc.stdin.write("quit\n")
                    _proc.stdin.flush()
                _proc.wait(timeout=1.5)
            except Exception:
                try:
                    _proc.kill()
                except Exception:
                    pass
            _proc = None
