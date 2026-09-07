"""中国象棋赛后复盘：基于子力与将/杀结果的启发式报告。"""
from __future__ import annotations

from typing import Any

from src.xiangqi.council import _eval_probs
from src.xiangqi.rules import START_FEN, XiangqiGame, evaluate_material, parse_fen


def _thin_curve(points: list[dict[str, Any]], max_points: int = 8) -> list[dict[str, Any]]:
    if len(points) <= max_points:
        return points
    kept = [0]
    for i in range(1, len(points) - 1):
        last = points[kept[-1]]
        swing = abs(float(points[i]["advantage"]) - float(last["advantage"]))
        ply_gap = int(points[i].get("ply") or i) - int(last.get("ply") or 0)
        if ply_gap >= 2 and swing >= 6:
            kept.append(i)
    if kept[-1] != len(points) - 1:
        kept.append(len(points) - 1)
    if len(kept) > max_points:
        mid = kept[1:-1]
        scored = sorted(
            (
                abs(float(points[i]["advantage"]) - float(points[max(0, i - 1)]["advantage"])),
                i,
            )
            for i in mid
        )
        need = max_points - 2
        mid_keep = sorted(i for _, i in scored[-need:])
        kept = [0, *mid_keep, len(points) - 1]
    return [points[i] for i in kept]


def _classify_delta(delta_for_mover: float, captured: str | None, gave_check: bool) -> str:
    if captured and delta_for_mover >= 40:
        return "great"
    if captured and delta_for_mover >= 15:
        return "good"
    if gave_check and delta_for_mover >= 0:
        return "good"
    if delta_for_mover <= -80:
        return "blunder"
    if delta_for_mover <= -40:
        return "mistake"
    if delta_for_mover <= -15:
        return "inaccuracy"
    return "good"


def build_review(game: XiangqiGame) -> dict[str, Any]:
    """从本局着法生成复盘：叙事、关键着、红方优势曲线。"""
    start_fen = START_FEN
    if game.history:
        start_fen = game.history[0].get("fen_before") or START_FEN

    curve: list[dict[str, Any]] = [
        {
            "ply": 0,
            "san": "开局",
            "red_win": 50.0,
            "black_win": 50.0,
            "advantage": 0.0,
            "classification": None,
            "fen": start_fen,
        }
    ]
    highlights: list[dict[str, Any]] = []
    class_scores = {"red": [], "black": []}
    prev_mat = 0
    try:
        board, _, _, _ = parse_fen(start_fen)
        prev_mat = evaluate_material(board)
    except ValueError:
        prev_mat = 0

    for i, move in enumerate(game.history, start=1):
        fen_after = move.get("fen") or ""
        try:
            snap = XiangqiGame(fen_after)
            ev = _eval_probs(snap)
        except Exception:  # noqa: BLE001
            ev = {"red_pct": 50, "black_pct": 50, "material": prev_mat, "label": "均势"}
        mat = float(ev.get("material") or prev_mat)
        delta = mat - prev_mat
        color = move.get("color") or "red"
        # 红方物质增加为正；黑方走子时黑受益 = 红物质下降，故黑方 delta_for_mover = -delta
        delta_for_mover = delta if color == "red" else -delta
        cls = _classify_delta(delta_for_mover, move.get("captured"), bool(move.get("gave_check")))
        class_scores[color].append(cls)
        red_win = float(ev.get("red_pct") or 50)
        point = {
            "ply": i,
            "san": move.get("san") or move.get("uci") or "—",
            "red_win": red_win,
            "black_win": float(ev.get("black_pct") or (100 - red_win)),
            "advantage": round(red_win - 50.0, 1),
            "classification": cls,
            "fen": fen_after,
            "color": color,
        }
        curve.append(point)
        if cls in {"brilliant", "great", "mistake", "blunder"} or move.get("gave_check"):
            highlights.append(
                {
                    "number": i,
                    "san": point["san"],
                    "classification": cls,
                    "color": "红" if color == "red" else "黑",
                    "note": "将军" if move.get("gave_check") else "",
                    "disagreement_score": 0.35 if cls in {"mistake", "blunder"} else 0.15,
                }
            )
        prev_mat = mat

    def _side_accuracy(side: str) -> int | None:
        scores = class_scores[side]
        if not scores:
            return None
        mapping = {
            "brilliant": 100,
            "great": 95,
            "good": 85,
            "inaccuracy": 60,
            "mistake": 35,
            "blunder": 10,
        }
        vals = [mapping.get(c, 80) for c in scores]
        return int(round(sum(vals) / len(vals)))

    red_acc = _side_accuracy("red")
    black_acc = _side_accuracy("black")
    overall = None
    if red_acc is not None and black_acc is not None:
        overall = int(round((red_acc + black_acc) / 2))
    elif red_acc is not None:
        overall = red_acc
    elif black_acc is not None:
        overall = black_acc

    result = game.result or "对局进行中"
    narrative = [
        f"本局共 {len(game.history)} 着。",
        f"终局：{result}。",
    ]
    if "绝杀" in result:
        narrative.append("形成绝杀：对方无应将之路。")
    elif "困毙" in result:
        narrative.append("困毙判负：无子可动方负（非国际象棋式逼和）。")
    elif "长将" in result:
        narrative.append("长将判负：连续将军形成循环，长将方负。")
    elif "和棋" in result:
        narrative.append("重复局面和棋（MVP 规则）。")

    if highlights:
        narrative.append(f"标出 {len(highlights)} 处关键着（得子 / 失子 / 将军）。")

    title = "赛后复盘"
    if "红方胜" in result:
        title = "红方胜 · 复盘"
    elif "黑方胜" in result:
        title = "黑方胜 · 复盘"
    elif "和棋" in result:
        title = "和棋 · 复盘"

    return {
        "title": title,
        "result": result,
        "total_moves": len(game.history),
        "debate_count": 0,
        "avg_disagreement": 0.0,
        "narrative": narrative,
        "highlights": highlights[:12],
        "debates": [],
        "eval_curve": _thin_curve(curve),
        "accuracy": {
            "overall": overall,
            "red": red_acc,
            "black": black_acc,
            "white": red_acc,  # 兼容国际象棋复盘卡片字段
            "note": "启发式准确率（按子力波动粗分），非引擎深度评估。",
        },
        "pgn": " ".join(
            f"{i}.{m.get('san') or m.get('uci')}" for i, m in enumerate(game.history, start=1)
        ),
        "engine": "heuristic_v1",
    }
