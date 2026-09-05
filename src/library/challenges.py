"""残局闯关关卡——从学习库挑可实战通关的条目，按难度排序。"""
from __future__ import annotations

import chess

from src.library.catalog import get_library_item

# 由易到难；均有明确通关目标（将杀 / 升变）
CHALLENGE_IDS: list[str] = [
    "krk",
    "kqk",
    "ladder_mate",
    "arabian",
    "back_rank_drill",
    "corridor",
    "anastasia",
    "smothered_drill",
    "two_bishops",
    "queen_vs_pawn",
    "opposition",
    "lucena",
]


def _difficulty(level: int) -> int:
    if level <= 4:
        return 1
    if level <= 8:
        return 2
    return 3


def _human_color_from_fen(fen: str) -> str:
    board = chess.Board(fen)
    return "white" if board.turn == chess.WHITE else "black"


def list_challenges() -> list[dict]:
    levels: list[dict] = []
    for i, item_id in enumerate(CHALLENGE_IDS, start=1):
        item = get_library_item(item_id)
        if not item:
            continue
        fen = item["fen"]
        levels.append(
            {
                "level": i,
                "id": item_id,
                "title": item["title"],
                "blurb": item.get("blurb") or "",
                "goal": item.get("goal") or "完成目标",
                "difficulty": _difficulty(i),
                "fen": fen,
                "human_color": _human_color_from_fen(fen),
                "category": item.get("category"),
            }
        )
    return levels
