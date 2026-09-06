"""名局 / 残局片段学习库 + 闯关关卡。"""
from __future__ import annotations

from src.xiangqi.puzzles import PUZZLES, get_puzzle
from src.xiangqi.rules import START_FEN

# category: game | endgame | puzzle
# moves 为 UCI；空列表表示仅局面体验
LIBRARY: dict[str, dict] = {
    "opening_central_cannon": {
        "id": "opening_central_cannon",
        "category": "game",
        "title": "中炮对顺炮 · 开局示范",
        "blurb": "双方起手中炮，继而跳马出马，是最常见的开局骨架之一。",
        "players": "示范谱",
        "year": None,
        "fen": START_FEN,
        "moves": ["h2e2", "h7e7", "h0g2", "h9g7", "b0c2", "b9c7"],
        "tags": ["opening", "cannon"],
    },
    "opening_screen_horse": {
        "id": "opening_screen_horse",
        "category": "game",
        "title": "中炮对屏风马 · 开局示范",
        "blurb": "红方中炮，黑方屏风马挺7卒，典型对抗结构。",
        "players": "示范谱",
        "year": None,
        "fen": START_FEN,
        "moves": ["h2e2", "g6g5", "h0g2", "b9c7", "b0c2", "h9g7"],
        "tags": ["opening", "horse"],
    },
    "opening_edge_pawn": {
        "id": "opening_edge_pawn",
        "category": "game",
        "title": "仙人指路 · 开局示范",
        "blurb": "红方先挺中兵（仙人指路），黑方对挺，再转中炮。",
        "players": "示范谱",
        "year": None,
        "fen": START_FEN,
        "moves": ["e3e4", "e6e5", "h2e2", "h7e7", "h0g2", "h9g7"],
        "tags": ["opening", "pawn"],
    },
    "opening_cross_palace": {
        "id": "opening_cross_palace",
        "category": "game",
        "title": "飞相局雏形 · 开局示范",
        "blurb": "红方先飞相，再出横车，偏稳健路数。",
        "players": "示范谱",
        "year": None,
        "fen": START_FEN,
        "moves": ["c0a2", "c9a7", "a0a1", "a9a8", "h2e2", "h7e7"],
        "tags": ["opening", "elephant"],
    },
    "classic_rook_mate_motif": {
        "id": "classic_rook_mate_motif",
        "category": "game",
        "title": "名杀片段 · 单车锁宫",
        "blurb": "古典残局主题：底车平肋，将无逃路。可跟谱一步成杀。",
        "players": "残局主题",
        "year": None,
        "fen": "3k5/9/9/9/9/9/9/9/9/R3K4 w - - 0 1",
        "moves": ["a0d0"],
        "tags": ["mate", "classic"],
    },
    "classic_double_cannon": {
        "id": "classic_double_cannon",
        "category": "game",
        "title": "名杀片段 · 重炮沉底",
        "blurb": "前炮作架、后炮沉底，是教科书级杀法。",
        "players": "残局主题",
        "year": None,
        "fen": "4k4/9/4C4/9/9/9/9/9/4C4/4K4 w - - 0 1",
        "moves": ["e1e9"],
        "tags": ["mate", "cannon"],
    },
    "classic_king_assist": {
        "id": "classic_king_assist",
        "category": "game",
        "title": "名杀片段 · 帅助车杀",
        "blurb": "帅占中控制将门，底车成杀。",
        "players": "残局主题",
        "year": None,
        "fen": "3k5/9/9/9/9/9/9/9/9/3R1K3 w - - 0 1",
        "moves": ["f0e0"],
        "tags": ["mate", "king"],
    },
    "midgame_rook_check_line": {
        "id": "midgame_rook_check_line",
        "category": "game",
        "title": "攻杀片段 · 出车叫将",
        "blurb": "中残过渡：沉底或平中出车将军，培养进攻感觉。",
        "players": "教学谱",
        "year": None,
        "fen": "4k4/9/9/9/9/9/9/9/9/R4K3 w - - 0 1",
        "moves": ["a0a9"],
        "tags": ["attack", "rook"],
    },
}

# 由易到难的闯关（引用 puzzle id）
CHALLENGE_IDS: list[str] = [
    "mate_rook_a0d0",
    "mate_rook_e1d1",
    "mate_rook_h0f0",
    "pawn_side_d8",
    "capture_rook_a0a5",
    "capture_cannon_h0h7",
    "mate_rook_e4d4",
    "check_give_rook",
    "capture_horse_c5b7",
    "mate_cannon_e1e9",
    "mate_king_support",
    "defend_d9e9",
    "capture_cannon_e6c7",
    "mate_cannon_e2e9",
    "defend_f9e9",
    "iron_bolt_like",
    "defend_block",
]


def list_library(category: str | None = None) -> list[dict]:
    items = []
    for item in LIBRARY.values():
        if category and item.get("category") != category:
            continue
        items.append(
            {
                "id": item["id"],
                "category": item["category"],
                "title": item["title"],
                "blurb": item.get("blurb") or "",
                "players": item.get("players"),
                "year": item.get("year"),
                "tags": item.get("tags") or [],
                "has_script": bool(item.get("moves")),
                "move_count": len(item.get("moves") or []),
            }
        )
    # 残局题也并入学习库列表（便于筛选）
    if category in (None, "endgame", "puzzle"):
        for p in PUZZLES:
            cat = p.get("category") or "puzzle"
            if category and cat != category:
                continue
            items.append(
                {
                    "id": p["id"],
                    "category": cat,
                    "title": p["title"],
                    "blurb": p.get("goal") or "",
                    "players": None,
                    "year": None,
                    "tags": ["drill"],
                    "has_script": False,
                    "move_count": 0,
                    "difficulty": p.get("difficulty"),
                    "side": p.get("side"),
                }
            )
    return items


def get_library_item(item_id: str) -> dict | None:
    if item_id in LIBRARY:
        return LIBRARY[item_id]
    puzzle = get_puzzle(item_id)
    if puzzle:
        return {
            **puzzle,
            "blurb": puzzle.get("goal"),
            "moves": [],
            "players": None,
            "year": None,
            "tags": ["drill"],
        }
    return None


def _difficulty_band(level: int) -> int:
    if level <= 6:
        return 1
    if level <= 12:
        return 2
    return 3


def list_challenges() -> list[dict]:
    levels = []
    for i, pid in enumerate(CHALLENGE_IDS, start=1):
        p = get_puzzle(pid)
        if not p:
            continue
        levels.append(
            {
                "level": i,
                "id": pid,
                "title": p["title"],
                "blurb": p.get("hint") or "",
                "goal": p["goal"],
                "difficulty": _difficulty_band(i),
                "fen": p["fen"],
                "human_color": p["side"],
                "category": p.get("category"),
            }
        )
    return levels
