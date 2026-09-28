from src import storage
from src.xiangqi import engine as xq_engine
from src.xiangqi.council import evaluate_played_move
from src.xiangqi.rules import START_FEN, XiangqiGame


def test_mistake_book_persists_and_counts_repeats(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "mistakes.db")
    payload = {
        "variant": "chess",
        "classification": "mistake",
        "fen_before": "8/8/8/8/8/8/4K3/6k1 w - - 0 1",
        "fen_after": "8/8/8/8/8/8/8/4K1k1 b - - 1 1",
        "played_uci": "e2e1",
        "played_san": "Ke1",
        "recommended_uci": "e2f2",
        "recommended_san": "Kf2",
        "side": "white",
        "ply": 1,
    }

    first = storage.upsert_mistake(**payload)
    second = storage.upsert_mistake(**payload)
    items = storage.list_mistakes("chess")

    assert first["id"] == second["id"]
    assert len(items) == 1
    assert items[0]["repeat_count"] == 2
    assert items[0]["recommended_uci"] == "e2f2"


def test_xiangqi_engine_marks_opening_cannon_sacrifice(monkeypatch):
    calls = 0

    def fake_candidates(_fen, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return [("c3c4", 30), ("b2e2", 24)]
        return [("a9b9", 129)]

    monkeypatch.setattr(xq_engine, "candidate_moves_pikafish", fake_candidates)
    result = evaluate_played_move(XiangqiGame(START_FEN), "b2b9")

    assert result["classification"] == "mistake"
    assert result["recommended_uci"] == "c3c4"
    assert result["score_loss"] == 159
