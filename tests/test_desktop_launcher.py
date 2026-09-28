"""Desktop launcher smoke test without opening a native window."""
import os
import subprocess
import sys
from pathlib import Path

from desktop import launcher


def test_macos_application_dir_points_beside_bundle(monkeypatch):
    executable = Path("/tmp/demo/ChessCouncil.app/Contents/MacOS/ChessCouncil")
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert launcher.application_dir() == Path("/tmp/demo").resolve()


def test_desktop_self_test(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["CHESSCOUNCIL_DATA_DIR"] = str(tmp_path)
    env["LLM_LOG_PATH"] = str(tmp_path / "logs" / "llm_calls.jsonl")
    result = subprocess.run(
        [sys.executable, "-m", "desktop.launcher", "--self-test"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "chesscouncil.db").is_file()


def test_relative_log_path_and_bundled_pikafish(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    bundle = tmp_path / "bundle"
    engine = bundle / "bin" / "pikafish"
    engine.parent.mkdir(parents=True)
    engine.write_text("test executable", encoding="utf-8")
    engine.chmod(0o755)
    (engine.parent / "pikafish.nnue").write_bytes(b"test net")
    monkeypatch.setattr(launcher, "bundle_root", lambda: bundle)
    monkeypatch.setenv("CHESSCOUNCIL_DATA_DIR", str(data_dir))
    monkeypatch.setenv("LLM_LOG_PATH", "logs/llm_calls.jsonl")
    monkeypatch.setenv("PIKAFISH_PATH", "missing-pikafish")

    launcher.prepare_environment()

    assert os.environ["LLM_LOG_PATH"] == str(data_dir / "logs" / "llm_calls.jsonl")
    assert os.environ["PIKAFISH_PATH"] == str(engine)
