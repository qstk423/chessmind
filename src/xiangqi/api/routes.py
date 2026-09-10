"""对弈 / AI / 残局 / FEN API。"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, Field

from src.xiangqi.ai import choose_move_for_side, opponent_ai, resolve_ai_side
from src.xiangqi.council import analyze_position
from src.xiangqi.library import get_library_item, list_challenges, list_library
from src.xiangqi.puzzles import get_puzzle, list_puzzles, solution_lines_of
from src.xiangqi.rules import START_FEN, Move, legal_targets, parse_fen
from src.xiangqi.sessions import sessions

router = APIRouter()


class NewGameRequest(BaseModel):
    mode: str = "human_vs_human"
    human_color: str = "red"
    red_ai: str = "engine"
    fen: str | None = None


class MoveRequest(BaseModel):
    uci: str


class FenRequest(BaseModel):
    fen: str


class TargetsRequest(BaseModel):
    square: str = Field(description="如 e3")


class AnalyzeRequest(BaseModel):
    with_analysis: bool = True


class TimeoutRequest(BaseModel):
    color: str = Field(description="超时方 red/black")


class LibraryLoadRequest(BaseModel):
    free_play: bool = False


def _sid(x_session_id: str | None, response: Response) -> tuple[str, object]:
    sid, game = sessions.resolve(x_session_id)
    response.headers["X-Session-Id"] = sid
    return sid, game


def _normalize_red_ai(value: str | None) -> str:
    v = (value or "engine").strip().lower()
    if v not in ("engine", "llm", "qwen"):
        return "engine"
    return v


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
    settings = sessions.settings_of(sid)
    mode = settings.get("mode", "human_vs_human")
    human_color = settings.get("human_color", "red")
    red_ai = _normalize_red_ai(settings.get("red_ai"))
    controller = None
    if not game.result:
        side = resolve_ai_side(
            mode=mode,
            turn=game.turn,
            human_color=human_color,
            red_ai=red_ai,  # type: ignore[arg-type]
        )
        controller = "human" if side is None else side
    data["session_id"] = sid
    data["mode"] = mode
    data["human_color"] = human_color
    data["red_ai"] = red_ai
    data["black_ai"] = opponent_ai(red_ai) if mode == "ai_vs_ai" else None  # type: ignore[arg-type]
    data["controller"] = controller
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
    from src.config import LLM_ENABLED, LLM_MODEL, QWEN_ENABLED, QWEN_MODEL
    from src.xiangqi.rooms import room_manager

    engine_info = {"available": False}
    try:
        from src.xiangqi.engine import pikafish_status

        engine_info = pikafish_status()
    except Exception:
        pass

    return {
        "status": "ok",
        "product": "ChessCouncil",
        "variant": "xiangqi",
        "version": "0.3.4",
        "engine": "pikafish" if engine_info.get("available") else "builtin_minimax_v2",
        "pikafish": engine_info,
        "council": "heuristic_v2",
        "llm_enabled": LLM_ENABLED,
        "llm_model": LLM_MODEL,
        "qwen_enabled": QWEN_ENABLED,
        "qwen_model": QWEN_MODEL,
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
            "ai_vs_ai",
            "llm_move_pick",
            "undo",
            "legal_highlights",
            "check_detect",
            "puzzles",
            "library",
            "challenges",
            "fen_tools",
            "online_rooms",
            "council_analyze",
            "post_review",
            "session_isolation",
            "threefold_draw",
            "perpetual_check_loss",
        ],
        "planned": ["llm_debate", "accounts", "perpetual_chase"],
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
    mode = (req.mode or "human_vs_human").strip()
    if mode not in ("human_vs_human", "human_vs_ai", "ai_vs_ai"):
        mode = "human_vs_human"
    human_color = (req.human_color or "red").strip().lower()
    if human_color not in ("red", "black"):
        human_color = "red"
    red_ai = _normalize_red_ai(req.red_ai)
    try:
        parse_fen(fen)
        game.reset(fen)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    sessions.set_library(sid, {"id": None, "moves": [], "index": 0, "meta": None})
    sessions.set_settings(
        sid,
        {
            "mode": mode,
            "human_color": human_color,
            "red_ai": red_ai,
        },
    )
    return _state(game, sid)


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


@router.post("/game/timeout")
def game_timeout(
    req: TimeoutRequest,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """超时判负。"""
    sid, game = _sid(x_session_id, response)
    if game.result:
        return _state(game, sid, timed_out=True)
    color = (req.color or "").strip().lower()
    if color not in ("red", "black"):
        raise HTTPException(400, "颜色错误")
    try:
        game.end_by(color, "超时")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _state(game, sid, timed_out=True)


@router.post("/game/ai-step")
async def ai_step(
    response: Response,
    depth: int | None = None,
    strength: str = "normal",
    ai_side: str | None = None,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    sid, game = _sid(x_session_id, response)
    if game.result:
        raise HTTPException(400, "对局已结束")
    settings = sessions.settings_of(sid)
    mode = settings.get("mode", "human_vs_human")
    human_color = settings.get("human_color", "red")
    red_ai = _normalize_red_ai(settings.get("red_ai"))
    level = (strength or settings.get("strength") or "normal").strip().lower()
    if level not in ("easy", "normal", "hard"):
        level = "normal"
    sessions.set_settings(sid, {"strength": level})

    side = _normalize_red_ai(ai_side) if ai_side else None
    if not side:
        resolved = resolve_ai_side(
            mode=mode,
            turn=game.turn,
            human_color=human_color,
            red_ai=red_ai,  # type: ignore[arg-type]
        )
        if resolved is not None:
            side = resolved
        elif mode == "human_vs_ai":
            # 手动「AI 一步」允许在人类回合代走
            side = red_ai
        else:
            side = "engine"
    assert side is not None

    kwargs: dict = {"strength": level, "ai_side": side}
    if depth is not None:
        kwargs["depth"] = max(1, min(5, int(depth)))
    choice = await choose_move_for_side(game, **kwargs)
    uci = choice.get("uci")
    if not uci:
        raise HTTPException(400, "无合法着法")
    entry = game.play_uci(uci)
    state = _state(game, sid, last_move=entry, ai=True)
    try:
        from src.xiangqi.engine import pikafish_status

        state["ai_engine"] = pikafish_status()
    except Exception:
        state["ai_engine"] = {"available": False}
    state["ai_strength"] = level
    state["ai_meta"] = {
        "source": choice.get("source"),
        "reason": choice.get("reason"),
        "controller": choice.get("controller") or side,
    }
    return state


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


@router.get("/game/review")
def game_review(
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    from src.xiangqi.review import build_review

    sid, game = _sid(x_session_id, response)
    review = build_review(game)
    return {"session_id": sid, **review}


@router.post("/game/post-review")
def post_game_review(
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """终局结算后一键：局面分析 + 复盘报告。"""
    from src.xiangqi.review import build_review

    sid, game = _sid(x_session_id, response)
    council = None
    try:
        council = analyze_position(game)
    except Exception:  # noqa: BLE001
        council = None
    review = build_review(game)
    return {
        "session_id": sid,
        "state": _state(game, sid),
        "council": council,
        "analysis": {"council": council} if council else None,
        "review": review,
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
