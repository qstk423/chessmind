"""对弈 / AI / 残局 / FEN API。"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, Field

from src.xiangqi.ai import choose_move
from src.xiangqi.council import analyze_position
from src.xiangqi.library import get_library_item, list_challenges, list_library
from src.xiangqi.puzzles import get_puzzle, list_puzzles, solution_lines_of
from src.xiangqi.rules import START_FEN, Move, legal_targets, parse_fen
from src.xiangqi.sessions import sessions

router = APIRouter()


class NewGameRequest(BaseModel):
    mode: str = "human_vs_human"
    human_color: str = "red"
    fen: str | None = None


class MoveRequest(BaseModel):
    uci: str


class FenRequest(BaseModel):
    fen: str


class TargetsRequest(BaseModel):
    square: str = Field(description="如 e3")


class AnalyzeRequest(BaseModel):
    with_analysis: bool = True


class LibraryLoadRequest(BaseModel):
    free_play: bool = False


def _sid(x_session_id: str | None, response: Response) -> tuple[str, object]:
    sid, game = sessions.resolve(x_session_id)
    response.headers["X-Session-Id"] = sid
    return sid, game


def _state(game, sid: str, **extra):
    data = game.snapshot()
    lib = sessions.library_of(sid)
    if lib.get("id"):
        moves = lib.get("moves") or []
        idx = lib.get("index") or 0
        data["library"] = {
            "id": lib["id"],
            "title": (lib.get("meta") or {}).get("title"),
            "index": idx,
            "total": len(moves),
            "has_script": bool(moves),
            "done": bool(moves) and idx >= len(moves),
            "meta": lib.get("meta"),
        }
    data["session_id"] = sid
    data.update(extra)
    return data


def _parse_square(sq: str) -> tuple[int, int]:
    sq = (sq or "").strip().lower()
    if len(sq) < 2 or sq[0] not in "abcdefghi" or not sq[1:].isdigit():
        raise ValueError("格子编码错误")
    fc = ord(sq[0]) - 97
    rank = int(sq[1:])
    if rank < 0 or rank > 9:
        raise ValueError("格子越界")
    fr = 9 - rank
    if not (0 <= fr < 10 and 0 <= fc < 9):
        raise ValueError("格子越界")
    return fr, fc


@router.get("/health")
def health():
    from src.xiangqi.rooms import room_manager

    return {
        "status": "ok",
        "product": "ChessCouncil",
        "variant": "xiangqi",
        "version": "0.3.2",
        "engine": "builtin_minimax",
        "council": "heuristic_v1",
        "rules": "mvp_mate_stalemate_threefold_perpetual_check",
        "sessions": "header",
        "session_pool": sessions.stats(),
        "room_pool": room_manager.stats(),
    }


@router.get("/capabilities")
def capabilities():
    return {
        "ready": [
            "rules_engine",
            "local_play",
            "human_vs_ai",
            "undo",
            "legal_highlights",
            "check_detect",
            "puzzles",
            "library",
            "challenges",
            "fen_tools",
            "online_rooms",
            "council_analyze",
            "session_isolation",
            "threefold_draw",
            "perpetual_check_loss",
        ],
        "planned": ["pikafish", "llm_debate", "opening_book", "accounts", "perpetual_chase"],
    }


@router.post("/game/new")
def new_game(
    response: Response,
    req: NewGameRequest | None = None,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    req = req or NewGameRequest()
    sid, game = _sid(x_session_id, response)
    fen = req.fen or START_FEN
    try:
        parse_fen(fen)
        game.reset(fen)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    sessions.set_library(sid, {"id": None, "moves": [], "index": 0, "meta": None})
    return _state(game, sid, mode=req.mode, human_color=req.human_color)


@router.get("/game/state")
def game_state(
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    sid, game = _sid(x_session_id, response)
    return _state(game, sid)


@router.post("/game/move")
def make_move(
    req: MoveRequest,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    sid, game = _sid(x_session_id, response)
    try:
        entry = game.play_uci(req.uci)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _state(game, sid, last_move=entry)


@router.post("/game/undo")
def undo_move(
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    sid, game = _sid(x_session_id, response)
    last = game.undo()
    if not last:
        raise HTTPException(400, "没有可悔的棋")
    return _state(game, sid, undone=last)


@router.post("/game/ai-step")
def ai_step(
    response: Response,
    depth: int = 2,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    sid, game = _sid(x_session_id, response)
    if game.result:
        raise HTTPException(400, "对局已结束")
    depth = max(1, min(3, depth))
    uci = choose_move(game, depth=depth)
    if not uci:
        raise HTTPException(400, "无合法着法")
    entry = game.play_uci(uci)
    return _state(game, sid, last_move=entry, ai=True)


@router.post("/game/targets")
def targets(
    req: TargetsRequest,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    sid, game = _sid(x_session_id, response)
    try:
        fr, fc = _parse_square(req.square)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    pts = legal_targets(game.board, game.turn, fr, fc)
    return {
        "square": req.square.strip().lower(),
        "targets": [f"{chr(97 + c)}{9 - r}" for r, c in pts],
        "uci": [Move(fr, fc, r, c).uci for r, c in pts],
        "session_id": sid,
    }


@router.post("/game/load-fen")
def load_fen(
    req: FenRequest,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    sid, game = _sid(x_session_id, response)
    try:
        parse_fen(req.fen)
        game.reset(req.fen)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _state(game, sid)


@router.post("/game/analyze-position")
def analyze_pos(
    response: Response,
    req: AnalyzeRequest | None = None,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    req = req or AnalyzeRequest()
    sid, game = _sid(x_session_id, response)
    if not req.with_analysis:
        return {"status": "skipped", "state": _state(game, sid)}
    try:
        council = analyze_position(game)
    except Exception as exc:  # noqa: BLE001 — 非法局面降级为 400
        raise HTTPException(400, f"分析失败: {exc}") from exc
    return {
        "status": "ok",
        "state": _state(game, sid),
        "council": council,
        "analysis": {"council": council},
    }


@router.get("/puzzles")
def puzzles(category: str | None = None):
    return {"items": list_puzzles(category=category)}


@router.post("/puzzles/{puzzle_id}/load")
def load_puzzle(
    puzzle_id: str,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    puzzle = get_puzzle(puzzle_id)
    if not puzzle:
        raise HTTPException(404, "题目不存在")
    sid, game = _sid(x_session_id, response)
    game.reset(puzzle["fen"])
    sessions.set_library(
        sid,
        {
            "id": None,
            "moves": [],
            "index": 0,
            "meta": None,
            "puzzle_id": puzzle_id,
            "puzzle_path": [],
        },
    )
    return _state(game, sid, puzzle=puzzle)


@router.post("/puzzles/{puzzle_id}/check")
def check_puzzle(
    puzzle_id: str,
    req: MoveRequest,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """
    答案约定：
    - solution: 多个可选正确着（OR），走中任意一个即通关
    - solution_lines: 多步变例；匹配前缀后，若后续着法无分叉则自动替对手走出
    """
    puzzle = get_puzzle(puzzle_id)
    if not puzzle:
        raise HTTPException(404, "题目不存在")
    sid, game = _sid(x_session_id, response)
    lib = sessions.library_of(sid)
    if lib.get("puzzle_id") != puzzle_id:
        lib["puzzle_id"] = puzzle_id
        lib["puzzle_path"] = []

    lines = solution_lines_of(puzzle)
    if not lines:
        raise HTTPException(400, "题目缺少答案")

    uci = req.uci.strip().lower()
    path = list(lib.get("puzzle_path") or [])
    prefix = path + [uci]
    matched = [line for line in lines if len(line) >= len(prefix) and line[: len(prefix)] == prefix]
    if not matched:
        return {
            "correct": False,
            "solved": False,
            "progress": f"{len(path)}/{max(len(line) for line in lines)}",
            "hint": puzzle["hint"],
            "state": game.snapshot(),
            "goal": puzzle["goal"],
            "session_id": sid,
        }

    try:
        game.play_uci(uci)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    path = list(prefix)
    human_len = len(path)
    puzzle_side = (puzzle.get("side") or "red").lower()
    if puzzle_side not in {"red", "black"}:
        puzzle_side = "red"
    auto_moves: list[str] = []
    # 仅自动续走对手着；轮到解题方时停下来等人手再走
    while game.turn != puzzle_side:
        next_moves = {line[len(path)] for line in matched if len(line) > len(path)}
        if len(next_moves) != 1:
            break
        nxt = next_moves.pop()
        try:
            game.play_uci(nxt)
        except ValueError:
            break
        path.append(nxt)
        auto_moves.append(nxt)
        matched = [line for line in matched if len(line) >= len(path) and line[: len(path)] == path]

    lib["puzzle_path"] = path
    sessions.set_library(sid, lib)
    solved = any(len(line) == len(path) for line in matched)
    total = max(len(line) for line in lines)
    return {
        "correct": True,
        "solved": solved,
        "progress": f"{len(path)}/{total}",
        "hint": "通关！" if solved else "正确，请继续",
        "state": game.snapshot(),
        "goal": puzzle["goal"],
        "session_id": sid,
        "auto_moves": auto_moves,
        "human_plies": human_len,
    }


@router.get("/library")
def library_list(category: str | None = None):
    return {"items": list_library(category=category)}


@router.get("/challenges")
def challenges():
    return {"levels": list_challenges()}


@router.post("/library/{item_id}/load")
def library_load(
    item_id: str,
    response: Response,
    req: LibraryLoadRequest | None = None,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    req = req or LibraryLoadRequest()
    item = get_library_item(item_id)
    if not item:
        raise HTTPException(404, "条目不存在")
    sid, game = _sid(x_session_id, response)
    fen = item.get("fen") or START_FEN
    try:
        parse_fen(fen)
        game.reset(fen)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    moves = [] if req.free_play else list(item.get("moves") or [])
    sessions.set_library(
        sid,
        {
            "id": item["id"],
            "moves": moves,
            "index": 0,
            "meta": {
                "title": item.get("title"),
                "category": item.get("category"),
                "blurb": item.get("blurb") or item.get("goal"),
                "goal": item.get("goal"),
                "side": item.get("side"),
                "solution": item.get("solution"),
            },
        },
    )
    return _state(game, sid)


@router.post("/library/step")
def library_step(
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    sid, game = _sid(x_session_id, response)
    lib = sessions.library_of(sid)
    if not lib.get("id") or not lib.get("moves"):
        raise HTTPException(400, "当前没有可演示的棋谱")
    idx = lib["index"]
    moves = lib["moves"]
    if idx >= len(moves):
        raise HTTPException(400, "棋谱已演示完毕")
    uci = moves[idx]
    try:
        entry = game.play_uci(uci)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    lib["index"] = idx + 1
    sessions.set_library(sid, lib)
    return _state(game, sid, last_move=entry)


@router.post("/challenges/{item_id}/load")
def challenge_load(
    item_id: str,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    item = get_library_item(item_id)
    if not item or not item.get("fen"):
        raise HTTPException(404, "关卡不存在")
    sid, game = _sid(x_session_id, response)
    try:
        parse_fen(item["fen"])
        game.reset(item["fen"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    sessions.set_library(
        sid,
        {
            "id": None,
            "moves": [],
            "index": 0,
            "meta": None,
            "puzzle_id": item_id if item.get("solution") or item.get("solution_lines") else None,
            "puzzle_path": [],
        },
    )
    return _state(
        game,
        sid,
        challenge={
            "id": item_id,
            "title": item.get("title"),
            "goal": item.get("goal"),
            "human_color": item.get("side") or "red",
            "solution": item.get("solution") or [],
        },
        puzzle=item if item.get("solution") or item.get("solution_lines") else None,
    )
