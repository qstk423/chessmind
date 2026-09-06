"""FastAPI 路由——对弈 / Council / Demo / 复盘 / 多模态识谱 / 历史"""
from io import StringIO
from typing import Literal

import chess.pgn
from fastapi import APIRouter, File, Header, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field, ValidationError

from src.board.fen_edit import board_grid, set_square_piece, set_turn
from src.board.game_state import GameState
from src.board.vision_fen import fen_from_image_bytes
from src.config import PGN_MAX_PLIES
from src.council.demos import list_demos
from src.guardrails import is_admin, require_admin, require_owner_id
from src.library.catalog import list_library
from src.llm_logger import recent_logs
from src.sessions import orchestrator, pool
from src.storage import adopt_orphan_games, delete_game, get_game, list_games

router = APIRouter()


class MoveRequest(BaseModel):
    uci: str
    with_analysis: bool | None = None
    analysis_mode: Literal["fast", "deep"] | None = None


class NewGameRequest(BaseModel):
    mode: Literal["human_vs_human", "human_vs_ai", "ai_vs_ai"] = "human_vs_human"
    human_color: Literal["white", "black"] = "white"
    white_ai: Literal["llm", "engine"] = "llm"
    engine_depth: int | None = Field(default=None, ge=1, le=25)
    with_analysis: bool = True
    analysis_mode: Literal["fast", "deep"] = "fast"
    coach_level: Literal["beginner", "intermediate", "advanced"] = "intermediate"


class PGNRequest(BaseModel):
    pgn: str


class AiStepRequest(BaseModel):
    with_analysis: bool | None = None


class FenRequest(BaseModel):
    fen: str


class AnalyzePositionRequest(BaseModel):
    with_analysis: bool = True


class FenSquareRequest(BaseModel):
    fen: str
    square: str
    piece: str | None = None


class FenTurnRequest(BaseModel):
    fen: str
    turn: Literal["w", "b", "white", "black"]


class SaveGameRequest(BaseModel):
    title: str | None = None
    with_review: bool = False


class LibraryLoadRequest(BaseModel):
    mode: Literal["human_vs_human", "human_vs_ai", "ai_vs_ai"] | None = None
    with_analysis: bool | None = None
    human_color: Literal["white", "black"] | None = None
    free_play: bool = False
    engine_depth: int | None = Field(default=None, ge=1, le=25)


class LibraryStepRequest(BaseModel):
    with_analysis: bool = False


def _orch(
    request: Request,
    response: Response,
    x_session_id: str | None,
):
    sid, orch = pool.resolve(x_session_id)
    response.headers["X-Session-Id"] = sid
    owner = (request.headers.get("x-owner-id") or "").strip()
    if len(owner) >= 8:
        orch.owner_id = owner
    return orch


def _assert_game_access(request: Request, row: dict) -> None:
    if is_admin(request):
        return
    owner = require_owner_id(request)
    if (row.get("owner_id") or "") != owner:
        raise HTTPException(status_code=404, detail="对局不存在")


# ── 对弈模式 ──

@router.post("/game/new")
async def new_game(
    request: Request,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    body = await request.body()
    try:
        req = NewGameRequest.model_validate_json(body) if body.strip() else NewGameRequest()
    except ValidationError as exc:
        # errors() 可能含 bytes，不能直接塞进 JSONResponse
        raise HTTPException(
            status_code=422,
            detail=[{"msg": e.get("msg"), "type": e.get("type"), "loc": list(e.get("loc") or ())} for e in exc.errors()],
        ) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"非法 JSON：{exc}") from exc
    orch = _orch(request, response, x_session_id)
    state = orch.new_game(
        mode=req.mode,
        human_color=req.human_color,
        white_ai=req.white_ai,
        engine_depth=req.engine_depth,
        with_analysis=req.with_analysis,
        coach_level=req.coach_level,
        analysis_mode=req.analysis_mode,
    )
    return {"status": "ok", **state}


@router.post("/game/move")
async def make_move(
    request: Request,
    req: MoveRequest,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    orch = _orch(request, response, x_session_id)
    if orch.mode != "human_vs_human":
        if orch.current_controller() != "human":
            raise HTTPException(status_code=400, detail="当前不是人类行棋回合")
    result = await orch.make_move(
        req.uci,
        with_analysis=req.with_analysis,
        analysis_mode=req.analysis_mode,
    )
    if result is None or "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/game/ai-step")
async def ai_step(
    request: Request,
    response: Response,
    req: AiStepRequest | None = None,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    orch = _orch(request, response, x_session_id)
    with_analysis = None if req is None else req.with_analysis
    result = await orch.ai_step(with_analysis=with_analysis)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/game/state")
def get_state(
    request: Request,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    return _orch(request, response, x_session_id).get_state()


@router.post("/game/load-fen")
def load_fen(
    request: Request,
    req: FenRequest,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    state = _orch(request, response, x_session_id).load_fen(req.fen)
    if "error" in state:
        raise HTTPException(status_code=400, detail=state)
    return {"status": "ok", **state}


@router.post("/game/analyze-position")
async def analyze_position(
    request: Request,
    response: Response,
    req: AnalyzePositionRequest | None = None,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """分析当前局面（不走子），用于 Demo / 识谱后 Council。"""
    orch = _orch(request, response, x_session_id)
    with_analysis = True if req is None else req.with_analysis
    return await orch.analyze_position(with_analysis=with_analysis)


@router.post("/game/post-review")
async def post_game_review(
    request: Request,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """人人局等：终局后统一生成 Council 评价与复盘。"""
    result = await _orch(request, response, x_session_id).post_game_review()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/game/undo")
def undo_move(
    request: Request,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """悔棋（人 vs AI 尽量回到人类回合）。"""
    result = _orch(request, response, x_session_id).undo()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/game/hint")
async def hint_move(
    request: Request,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """Stockfish 提示着法（不触发 Council）。"""
    result = await _orch(request, response, x_session_id).hint()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/game/review")
def game_review(
    request: Request,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """赛后复盘报告（基于本局逐步 Council 缓存）。"""
    return _orch(request, response, x_session_id).get_review()


@router.post("/game/save")
def save_game(
    request: Request,
    response: Response,
    req: SaveGameRequest | None = None,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    owner = require_owner_id(request)
    title = None if req is None else req.title
    with_review = False if req is None else req.with_review
    saved = _orch(request, response, x_session_id).persist_game(
        title=title, with_review=with_review, owner_id=owner
    )
    if "error" in saved:
        raise HTTPException(status_code=400, detail=saved)
    return {"status": "ok", "game": saved}


# ── FEN 纠错 ──

@router.get("/fen/grid")
def fen_grid(fen: str = Query(...)):
    try:
        return board_grid(fen)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)}) from e


@router.post("/fen/set-square")
def fen_set_square(req: FenSquareRequest):
    result = set_square_piece(req.fen, req.square, req.piece)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/fen/set-turn")
def fen_set_turn(req: FenTurnRequest):
    result = set_turn(req.fen, req.turn)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


# ── 对局历史（按 owner 隔离；管理员可看全部）──

@router.get("/games")
def games_list(
    request: Request,
    limit: int = Query(30, ge=1, le=100),
    adopt_orphans: bool = Query(
        False,
        description="仅管理员可用：将无归属历史归属到当前 X-Owner-Id",
    ),
):
    if is_admin(request):
        adopted = 0
        if adopt_orphans:
            owner = (request.headers.get("x-owner-id") or "").strip()
            if len(owner) >= 8:
                adopted = adopt_orphan_games(owner)
        return {"games": list_games(limit), "adopted_orphans": adopted}
    owner = require_owner_id(request)
    # 普通用户禁止认领孤儿，避免多用户环境下误占全部无归属记录
    if adopt_orphans:
        raise HTTPException(
            status_code=403,
            detail="认领无归属历史仅管理员可用（需要 X-Admin-Token）",
        )
    return {"games": list_games(limit, owner_id=owner), "adopted_orphans": 0}


@router.get("/games/{game_id}")
def games_get(game_id: str, request: Request):
    row = get_game(game_id)
    if not row:
        raise HTTPException(status_code=404, detail="对局不存在")
    _assert_game_access(request, row)
    return row


@router.delete("/games/{game_id}")
def games_delete(game_id: str, request: Request):
    row = get_game(game_id)
    if not row:
        raise HTTPException(status_code=404, detail="对局不存在")
    _assert_game_access(request, row)
    if not delete_game(game_id):
        raise HTTPException(status_code=404, detail="对局不存在")
    return {"status": "ok", "deleted": game_id}


@router.post("/games/{game_id}/restore")
def games_restore(
    game_id: str,
    request: Request,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """恢复历史局面到当前棋盘（不重放逐步分析）。"""
    row = get_game(game_id)
    if not row:
        raise HTTPException(status_code=404, detail="对局不存在")
    _assert_game_access(request, row)
    fen = row.get("fen_current") or row.get("fen_start")
    if not fen:
        raise HTTPException(status_code=400, detail="该记录无 FEN")
    state = _orch(request, response, x_session_id).load_fen(fen)
    if "error" in state:
        raise HTTPException(status_code=400, detail=state)
    return {"status": "ok", "restored_from": game_id, **state}


# ── Demo ──

@router.get("/demos")
def demos():
    return {"demos": list_demos()}


@router.post("/demos/{demo_id}/load")
def load_demo(
    demo_id: str,
    request: Request,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    state = _orch(request, response, x_session_id).load_demo(demo_id)
    if "error" in state:
        raise HTTPException(status_code=404, detail=state)
    return {"status": "ok", **state}


@router.post("/demos/{demo_id}/run")
async def run_demo(
    demo_id: str,
    request: Request,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """加载高争议 Demo 并立刻跑 Council（路演一键）。"""
    orch = _orch(request, response, x_session_id)
    state = orch.load_demo(demo_id)
    if "error" in state:
        raise HTTPException(status_code=404, detail=state)
    analysis = await orch.analyze_position(with_analysis=True)
    return {"status": "ok", "demo": state.get("demo"), "state": state, "analysis": analysis}


# ── 名局 / 残局库 ──

@router.get("/library")
def library_list(category: str | None = Query(None, description="game|endgame|puzzle")):
    return {"items": list_library(category=category)}


@router.get("/challenges")
def challenges_list():
    """残局闯关关卡列表。"""
    from src.library.challenges import list_challenges

    return {"levels": list_challenges()}


@router.post("/library/{item_id}/load")
def library_load(
    item_id: str,
    request: Request,
    response: Response,
    req: LibraryLoadRequest | None = None,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    orch = _orch(request, response, x_session_id)
    mode = None if req is None else req.mode
    with_analysis = None if req is None else req.with_analysis
    human_color = None if req is None else req.human_color
    free_play = False if req is None else req.free_play
    engine_depth = None if req is None else req.engine_depth
    state = orch.load_library(
        item_id,
        mode=mode,
        with_analysis=with_analysis,
        human_color=human_color,
        free_play=free_play,
        engine_depth=engine_depth,
    )
    if "error" in state:
        raise HTTPException(status_code=404, detail=state)
    return {"status": "ok", **state}


@router.post("/library/step")
async def library_step(
    request: Request,
    response: Response,
    req: LibraryStepRequest | None = None,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    with_analysis = False if req is None else req.with_analysis
    result = await _orch(request, response, x_session_id).library_step(with_analysis=with_analysis)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


# ── 多模态识谱 ──

@router.post("/vision/fen")
async def vision_fen(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    apply: bool = Query(True, description="识别后是否加载到当前棋局"),
    analyze: bool = Query(False, description="加载后是否立刻跑 Council 分析"),
    side_to_move: str | None = Query(None, description="强制行棋方 w/b/white/black"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    """上传棋盘照片/截图 → FEN，并可直接映射到数字棋盘。"""
    orch = _orch(request, response, x_session_id)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="空文件")
    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片过大（限制 12MB）")

    result = await fen_from_image_bytes(
        raw,
        filename=file.filename,
        client=orch.llm_client,
        side_to_move=side_to_move,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)

    state = None
    analysis = None
    if apply:
        state = orch.load_fen(result["fen"])
        if "error" in state:
            raise HTTPException(status_code=400, detail=state)
        if analyze:
            analysis = await orch.analyze_position(with_analysis=True)

    return {"status": "ok", "vision": result, "state": state, "analysis": analysis}


@router.get("/health")
async def health(
    request: Request,
    ping_llm: bool = Query(False, description="是否实际 ping 一次大模型"),
):
    if ping_llm:
        require_admin(request)
        return await orchestrator.health()
    state = orchestrator.get_state()
    return {
        "stockfish": orchestrator._connected,
        "stockfish_error": getattr(orchestrator.evaluator, "_connect_error", None),
        "llm_enabled": state["llm_enabled"],
        "llm_model": state["llm_model"],
        "mode": state["mode"],
        "game_id": state["game_id"],
        "product": state.get("product", "ChessCouncil"),
        "llm_ping": "not_requested",
        "public_ready": True,
        "sessions": "header",
    }


@router.get("/logs/recent")
def logs_recent(request: Request, limit: int = Query(20, ge=1, le=200)):
    require_admin(request)
    return {"count": limit, "logs": recent_logs(limit)}


@router.post("/analyze/pgn")
async def analyze_pgn(
    request: Request,
    req: PGNRequest,
    response: Response,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    orch = _orch(request, response, x_session_id)
    game = chess.pgn.read_game(StringIO(req.pgn))
    moves = list(game.mainline_moves()) if game is not None else []
    if game is None or not moves:
        raise HTTPException(status_code=400, detail="无法从 PGN 文本中解析出走法")
    if len(moves) > PGN_MAX_PLIES:
        raise HTTPException(
            status_code=400,
            detail=f"PGN 过长（{len(moves)} 半步），上限 {PGN_MAX_PLIES}；请截取关键片段",
        )

    replay = GameState(board=game.board())
    results = []
    for move in moves:
        analysis = await orch.analyze_move(replay, move.uci())
        if not analysis or "error" in analysis:
            break
        results.append(analysis)

    return {"total_moves": len(results), "moves": results, "capped_at": PGN_MAX_PLIES}
