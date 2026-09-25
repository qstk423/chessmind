"""Desktop launcher smoke test without opening a native window."""
import os
import subprocess
import sys
from pathlib import Path


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
