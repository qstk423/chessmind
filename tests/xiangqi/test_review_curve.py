"""赛后胜率曲线必须保留 0% 和 100% 终局值。"""

from unittest.mock import patch

from src.xiangqi.review import build_review
from src.xiangqi.rules import START_FEN, XiangqiGame


def test_review_curve_keeps_zero_percent_for_losing_side():
    game = XiangqiGame()
    game.history = [
        {
            "fen_before": START_FEN,
            "fen": START_FEN,
            "color": "black",
            "san": "测试终局",
            "captured": None,
            "gave_check": False,
        }
    ]
    with patch(
        "src.xiangqi.review._eval_probs",
        return_value={"red_pct": 0, "black_pct": 100, "material": 0, "label": "黑胜定局"},
    ):
        curve = build_review(game)["eval_curve"]

    assert curve[-1]["red_win"] == 0
    assert curve[-1]["black_win"] == 100
    assert curve[-1]["advantage"] == -50
