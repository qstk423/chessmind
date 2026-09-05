"""路演 / 高争议 Demo 预设局面。"""
from __future__ import annotations

# 均为白方行棋。优先选择「攻王弃子 vs 稳健」张力大的局面。
DEMO_PRESETS: dict[str, dict] = {
    "greek_gift": {
        "id": "greek_gift",
        "title": "希腊赠礼（攻王弃象）",
        "blurb": "经典 Bxh7+ 攻王抉择：战术想弃象破门，风险倾向稳健。路演首选。",
        # 白方象在 d3、马在 f3，黑王已易位 —— 典型希腊赠礼结构
        "fen": "rnbq1rk1/ppp2ppp/3b1n2/3pp3/3P4/2PB1N2/PP3PPP/RNBQK2R w KQ - 0 8",
        "side_to_move": "white",
        "tags": ["sacrifice", "king_attack", "debate"],
        "diverge": True,
    },
    "exchange_sac": {
        "id": "exchange_sac",
        "title": "中局强攻 vs 巩固",
        "blurb": "开放线与王翼压力并存，是否立即打将/弃子常引发分歧。",
        "fen": "r2q1rk1/1pp2ppp/p1npbn2/4p3/B3P3/2PP1N2/PP3PPP/R1BQ1RK1 w - - 0 11",
        "side_to_move": "white",
        "tags": ["middlegame", "tension"],
        "diverge": True,
    },
    "poisoned": {
        "id": "poisoned",
        "title": "毒兵诱惑",
        "blurb": "是否吃侧翼兵：贪子战术 vs 风险审查的「别上当」。",
        "fen": "rnbqkb1r/1p3ppp/p2p1n2/4p3/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 0 7",
        "side_to_move": "white",
        "tags": ["poisoned_pawn", "risk"],
        "diverge": True,
    },
}

DIVERGE_HINT = """
【路演强化 · 角色必须分化】
- 战术分析师：优先寻找弃子、打将、强制战术续着；即使风险高也要给进攻性 recommended_move。
- 战略分析师：优先改善结构/发展/中心，推荐可不同于战术的稳健战略着法。
- 风险审查员：主动反对弃子与冒进，recommended_move 必须给更稳妥的防守/巩固着法，并在 concerns 指出对手杀着或反将。
三方推荐着法应尽量不同，以便系统演示分歧与辩论。
""".strip()


def list_demos() -> list[dict]:
    return [
        {
            "id": d["id"],
            "title": d["title"],
            "blurb": d["blurb"],
            "fen": d["fen"],
            "tags": d["tags"],
        }
        for d in DEMO_PRESETS.values()
    ]


def get_demo(demo_id: str) -> dict | None:
    return DEMO_PRESETS.get(demo_id)
