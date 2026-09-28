"""ChessCouncil desktop entry point.

The existing FastAPI app runs on an ephemeral loopback port. A native webview
shows its UI, so users do not need to open a browser or know a URL.
"""
from __future__ import annotations

import logging
import os
import shutil
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.request import urlopen

from dotenv import load_dotenv


def bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        if sys.platform == "darwin" and executable_dir.name == "MacOS" and executable_dir.parent.name == "Contents":
            # Finder apps keep their executable inside ChessCouncil.app/Contents/MacOS.
            # A private config belongs beside the app, not inside the signed bundle.
            return executable_dir.parent.parent.parent
        return executable_dir
    return Path(__file__).resolve().parents[1]


def user_data_dir() -> Path:
    override = os.getenv("CHESSCOUNCIL_DATA_DIR")
    if override:
        return Path(override)
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if base:
            return Path(base) / "ChessCouncil"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ChessCouncil"
    return Path.home() / ".chesscouncil"


def prepare_environment() -> Path:
    data_dir = user_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    # Configuration lives outside the executable. Never bundle a real API key.
    for config_file in (
        application_dir() / "ChessCouncil.env",
        data_dir / "config.env",
    ):
        if config_file.is_file():
            load_dotenv(config_file, override=False)

    os.environ.setdefault("CHESSCOUNCIL_DATA_DIR", str(data_dir))
    log_path = Path(os.getenv("LLM_LOG_PATH") or "logs/llm_calls.jsonl").expanduser()
    if not log_path.is_absolute():
        log_path = data_dir / log_path
    os.environ["LLM_LOG_PATH"] = str(log_path)

    stockfish = bundle_root() / "bin" / (
        "stockfish.exe" if os.name == "nt" else "stockfish"
    )
    if stockfish.is_file():
        configured = os.getenv("STOCKFISH_PATH")
        if not configured or not (Path(configured).is_file() or shutil.which(configured)):
            os.environ["STOCKFISH_PATH"] = str(stockfish)

    pikafish = bundle_root() / "bin" / "pikafish"
    if pikafish.is_file() and (bundle_root() / "bin" / "pikafish.nnue").is_file():
        configured = os.getenv("PIKAFISH_PATH")
        if not configured or not (Path(configured).is_file() or shutil.which(configured)):
            os.environ["PIKAFISH_PATH"] = str(pikafish)

    logging.basicConfig(
        filename=str(data_dir / "desktop.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return data_dir


def start_local_server():
    import uvicorn

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"

    # Restrict browser access to this local window before src.main reads config.
    os.environ["CORS_ORIGINS"] = origin
    from src.main import app

    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=port, access_log=False, log_config=None
        )
    )
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [sock]},
        name="chesscouncil-server",
        daemon=True,
    )
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=3)
        sock.close()
        raise RuntimeError("本地服务启动失败，请查看 desktop.log")
    return origin, server, thread


def run_self_test(origin: str) -> None:
    for route in (
        "/chess/", "/xiangqi/", "/api/chess/health", "/api/xiangqi/health",
        "/api/xiangqi/game/review",
    ):
        with urlopen(origin + route, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError(f"{route}: HTTP {response.status}")
    if (bundle_root() / "bin" / "pikafish").is_file():
        from src.xiangqi.engine import best_move_pikafish
        from src.xiangqi.rules import START_FEN

        if not best_move_pikafish(START_FEN, depth=8, movetime_ms=250):
            raise RuntimeError("内置 Pikafish 自检失败")


def main() -> int:
    data_dir = prepare_environment()
    try:
        origin, server, thread = start_local_server()
        try:
            if "--self-test" in sys.argv:
                run_self_test(origin)
                return 0

            import webview

            webview.create_window(
                "ChessCouncil",
                origin + "/",
                width=1200,
                height=900,
                min_size=(900, 600),
                background_color="#17251d",
            )
            webview.start(debug=False)
            return 0
        finally:
            server.should_exit = True
            thread.join(timeout=5)
    except Exception:
        logging.exception("ChessCouncil desktop startup failed")
        if os.name == "nt" and "--self-test" not in sys.argv:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                f"ChessCouncil 启动失败。请查看：{data_dir / 'desktop.log'}",
                "ChessCouncil",
                0x10,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
