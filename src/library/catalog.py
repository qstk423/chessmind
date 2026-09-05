"""名局 / 残局 / 经典战术库——供学习体验与 AI 演示。"""
from __future__ import annotations

from typing import Any

# moves 为 UCI；空列表表示仅局面体验（残局自己下 / AI 代下）
LIBRARY: dict[str, dict[str, Any]] = {
    # ── 名局 ──
    "opera": {
        "id": "opera",
        "category": "game",
        "title": "歌剧院对局 · Morphy",
        "blurb": "莫菲经典弃子攻王：开局到闷杀一气呵成，适合跟谱学习。",
        "players": "Morphy vs Duke Karl / Count Isouard",
        "year": 1858,
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "moves": [
            "e2e4", "e7e5", "g1f3", "d7d6", "d2d4", "c8g4", "d4e5", "g4f3",
            "d1f3", "d6e5", "f1c4", "g8f6", "f3b3", "d8e7", "b1c3", "c7c6",
            "c1g5", "b7b5", "c3b5", "c6b5", "c4b5", "b8d7", "e1c1", "a8d8",
            "d1d7", "d8d7", "h1d1", "e7e6", "b5d7", "f6d7", "b3b8", "d7b8",
            "d1d8",
        ],
        "tags": ["classic", "attack", "morphy"],
    },
    "immortal": {
        "id": "immortal",
        "category": "game",
        "title": "不朽对局 · Anderssen",
        "blurb": "安德森不朽局：连续弃后弃车的浪漫主义攻杀。",
        "players": "Anderssen vs Kieseritzky",
        "year": 1851,
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "moves": [
            "e2e4", "e7e5", "f2f4", "e5f4", "f1c4", "d8h4", "e1f1", "b7b5",
            "c4b5", "g8f6", "g1f3", "h4h6", "d2d3", "f6h5", "f3h4", "h6g5",
            "h4f5", "c7c6", "g2g4", "h5f6", "h1g1", "c6b5", "h2h4", "g5g6",
            "h4h5", "g6g5", "d1f3", "f6g8", "c1f4", "g5f6", "b1c3", "f8c5",
            "c3d5", "f6b2", "f4d6", "c5g1", "e4e5", "b2a1", "f1e2", "b8a6",
            "f5g7", "e8d8", "f3f6", "g8f6", "d6e7",
        ],
        "tags": ["classic", "sacrifice", "romantic"],
    },
    "evergreen": {
        "id": "evergreen",
        "category": "game",
        "title": "常青对局 · Anderssen",
        "blurb": "常青局：中心打开后的华丽弃后杀王。",
        "players": "Anderssen vs Dufresne",
        "year": 1852,
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "moves": [
            "e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5", "b2b4", "c5b4",
            "c2c3", "b4a5", "d2d4", "e5d4", "e1g1", "d4d3", "d1b3", "d8f6",
            "e4e5", "f6g6", "f1e1", "g8e7", "c1a3", "b7b5", "b3b5", "a8b8",
            "b5a4", "a5b6", "b1d2", "c8b7", "d2e4", "g6f5", "c4d3", "f5h5",
            "e4f6", "g7f6", "e5f6", "h8g8", "a1d1", "h5f3", "e1e7", "c6e7",
            "a4d7", "e8d7", "d3f5", "d7e8", "f5d7", "e8f8", "a3e7",
        ],
        "tags": ["classic", "attack"],
    },
    "game_of_century": {
        "id": "game_of_century",
        "category": "game",
        "title": "世纪之局 · Fischer",
        "blurb": "菲舍尔 13 岁成名作：弃后换攻，终局闪杀。",
        "players": "Byrne vs Fischer",
        "year": 1956,
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "moves": [
            "g1f3", "g8f6", "c2c4", "g7g6", "b1c3", "f8g7", "d2d4", "e8g8",
            "c1f4", "d7d5", "d1b3", "d5c4", "b3c4", "c7c6", "e2e4", "b8d7",
            "a1d1", "d7b6", "c4c5", "c8g4", "f4g5", "b6a4", "c5a3", "a4c3",
            "b2c3", "f6e4", "g5e7", "d8b6", "f1c4", "e4c3", "e7c5", "f8e8",
            "e1f1", "g4e6", "c5b6", "e6c4", "f1g1", "c3e2", "g1f1", "e2d4",
            "f1g1", "d4e2", "g1f1", "e2c3", "f1g1", "a7b6", "a3b4", "a8a4",
            "b4b6", "c3d1", "h2h3", "a4a2", "g1h2", "d1f2", "h1e1", "e8e1",
            "b6d8", "g7f8", "f3e1", "c4d5", "e1f3", "f2e4", "d8b8", "b7b5",
            "h3h4", "h7h5", "f3e5", "g8g7", "h2g1", "f8c5", "g1f1", "e4g3",
            "f1e1", "c5b4", "e1d1", "d5b3", "d1c1", "g3e2", "c1b1", "e2c3",
            "b1c1", "a2c2",
        ],
        "tags": ["classic", "fischer", "queen_sac"],
    },
    "scholar": {
        "id": "scholar",
        "category": "game",
        "title": "学者将死 · Scholar's Mate",
        "blurb": "最快入门杀法之一：瞄准 f7，四步示范（含黑方常见失误）。",
        "players": "教学示例",
        "year": None,
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "moves": [
            "e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6", "h5f7",
        ],
        "tags": ["beginner", "mate"],
    },
    "fools_mate": {
        "id": "fools_mate",
        "category": "game",
        "title": "愚人将死 · Fool's Mate",
        "blurb": "棋史上最短将杀：白方乱推王翼兵，黑后两步绝杀。",
        "players": "教学示例",
        "year": None,
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "moves": ["f2f3", "e7e5", "g2g4", "d8h4"],
        "tags": ["beginner", "mate"],
    },
    "legal_trap": {
        "id": "legal_trap",
        "category": "game",
        "title": "莱加尔陷阱 · Legal's Mate",
        "blurb": "弃后诱捉钉死马象：经典开局陷阱，终局双马杀。",
        "players": "de Kermur / Legal",
        "year": 1750,
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "moves": [
            "e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "d7d6", "b1c3", "c8g4",
            "f3e5", "g4d1", "c4f7", "e8e7", "c3d5",
        ],
        "tags": ["trap", "mate", "classic"],
    },
    "fried_liver": {
        "id": "fried_liver",
        "category": "game",
        "title": "意大利局 · 炸肝攻击",
        "blurb": "两马开局炸肝：弃马打 f7，进入激烈攻杀结构（演示到关键弃子）。",
        "players": "教学示例",
        "year": None,
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "moves": [
            "e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6", "f3g5", "d7d5",
            "e4d5", "f6d5", "g5f7",
        ],
        "tags": ["attack", "opening", "italian"],
    },

    # ── 残局 ──
    "lucena": {
        "id": "lucena",
        "category": "endgame",
        "title": "卢塞纳局面 · 车兵残局",
        "blurb": "经典车兵胜法：造桥掩护，推进兵升变。",
        "fen": "1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1",
        "moves": [
            "c1d1", "d8e7", "d1d4", "a2c2", "b8a7", "c2a2", "a7b6", "a2g2",
            "d4d5", "g2g6", "b6c7", "g6g1", "d5b5", "g1g8", "b7b8q",
        ],
        "tags": ["endgame", "rook", "technique"],
        "goal": "白方造桥升变",
    },
    "philidor": {
        "id": "philidor",
        "category": "endgame",
        "title": "菲利多尔局面 · 守和",
        "blurb": "车兵残局防守典范：三线防守；兵冲七线后背后将军兑兵。",
        "fen": "3k4/8/3P4/3K4/8/8/8/2r5 b - - 0 1",
        "moves": [
            "c1c6", "d5e5", "c6a6", "e5d5", "a6c6", "d5e6", "c6c1", "d6d7",
            "c1e1", "e6d6", "e1d1", "d6e6", "d1d7",
        ],
        "tags": ["endgame", "rook", "draw"],
        "goal": "黑方演示守和思路（兑掉通路兵）",
    },
    "opposition": {
        "id": "opposition",
        "category": "endgame",
        "title": "对王 · 兵残局入门",
        "blurb": "谁掌握对王谁主导：白方抢对王后护送兵升变（注意避开逼和）。",
        "fen": "8/8/8/4k3/8/4K3/4P3/8 w - - 0 1",
        "moves": [
            "e3d3", "e5d5", "e2e4", "d5e5", "d3e3", "e5d6", "e3d4", "d6e6",
            "e4e5", "e6d7", "d4d5", "d7e7", "e5e6", "e7e8", "d5d6", "e8d8",
            "e6e7", "d8e8", "d6c7", "e8f7", "e7e8q",
        ],
        "tags": ["endgame", "king_pawn"],
        "goal": "白方升变",
    },
    "two_bishops": {
        "id": "two_bishops",
        "category": "endgame",
        "title": "双象杀王",
        "blurb": "基础将杀技术：把王逼到角上用双象绝杀。",
        "fen": "8/8/8/8/8/8/2B2K2/k1B5 w - - 0 1",
        "moves": [
            "f2e3", "a1a2", "c2d1", "a2a1", "e3d2", "a1a2", "d2c2", "a2a1",
            "d1f3", "a1a2", "f3d5", "a2a1", "c1b2",
        ],
        "tags": ["endgame", "mate_technique"],
        "goal": "白方将杀",
    },
    "queen_vs_pawn": {
        "id": "queen_vs_pawn",
        "category": "endgame",
        "title": "后对兵 · 第七横线",
        "blurb": "后对通路兵：先检查逼王，再靠近王配合绝杀。",
        "fen": "8/kp6/8/3K4/8/8/8/2Q5 w - - 0 1",
        "moves": [
            "c1c8", "a7b6", "c8b8", "b6a5", "b8b7", "a5a4", "d5c4", "a4a3",
            "b7b3",
        ],
        "tags": ["endgame", "queen"],
        "goal": "白方将杀",
    },

    # ── 战术 / 残局名局片段 ──
    "arabian": {
        "id": "arabian",
        "category": "puzzle",
        "title": "阿拉伯闷杀型",
        "blurb": "车马配合的经典杀型：Ra8# 一步绝杀。",
        "fen": "6k1/6p1/5nNp/8/8/8/8/R5K1 w - - 0 1",
        "moves": ["a1a8"],
        "tags": ["mate", "pattern"],
        "goal": "白方一步杀",
    },
    "back_rank_drill": {
        "id": "back_rank_drill",
        "category": "puzzle",
        "title": "底线杀练习",
        "blurb": "经典底线弱点：白走一步杀。",
        "fen": "6k1/5ppp/8/8/8/8/8/1R2K3 w - - 0 1",
        "moves": ["b1b8"],
        "tags": ["mate", "back_rank"],
        "goal": "白方一步杀",
    },
    "smothered_drill": {
        "id": "smothered_drill",
        "category": "puzzle",
        "title": "闷杀练习",
        "blurb": "著名闷杀结构：马跃 f7 完成绝杀。",
        "fen": "5r1k/6pp/7N/8/8/8/8/4K3 w - - 0 1",
        "moves": ["h6f7"],
        "tags": ["mate", "smothered"],
        "goal": "白方一步闷杀",
    },
    "greek_gift_lib": {
        "id": "greek_gift_lib",
        "category": "puzzle",
        "title": "希腊赠礼结构",
        "blurb": "与路演 Demo 同源：Bxh7+ 攻王主线演示到将杀，也可开 Council。",
        "fen": "rnbq1rk1/ppp2ppp/3b1n2/3pp3/3P4/2PB1N2/PP3PPP/RNBQK2R w KQ - 0 8",
        "moves": [
            "d3h7", "g8h7", "f3g5", "h7g8", "d1h5", "f8e8", "h5f7", "g8h8",
            "f7h5", "h8g8", "h5h7", "g8f8", "h7h8", "f8e7", "h8g7",
        ],
        "tags": ["sacrifice", "debate"],
        "goal": "白方演示弃象攻王主线",
        "diverge": True,
    },
}

CATEGORY_LABELS = {
    "game": "名局",
    "endgame": "残局",
    "puzzle": "战术/杀型",
}


def list_library(*, category: str | None = None) -> list[dict[str, Any]]:
    items = []
    for entry in LIBRARY.values():
        if category and entry["category"] != category:
            continue
        items.append(_public(entry))
    # 稳定排序：名局 → 残局 → 战术
    order = {"game": 0, "endgame": 1, "puzzle": 2}
    items.sort(key=lambda x: (order.get(x["category"], 9), x["title"]))
    return items


def get_library_item(item_id: str) -> dict[str, Any] | None:
    return LIBRARY.get(item_id)


def _public(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry["id"],
        "category": entry["category"],
        "category_label": CATEGORY_LABELS.get(entry["category"], entry["category"]),
        "title": entry["title"],
        "blurb": entry["blurb"],
        "players": entry.get("players"),
        "year": entry.get("year"),
        "tags": entry.get("tags") or [],
        "goal": entry.get("goal"),
        "move_count": len(entry.get("moves") or []),
        "has_script": bool(entry.get("moves")),
        "fen": entry["fen"],
    }
