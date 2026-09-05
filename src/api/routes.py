"""FastAPI 路由——对弈 / Council / Demo / 复盘 / 多模态识谱 / 历史"""
from io import StringIO
from typing import Literal

import chess.pgn
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from src.board.fen_edit import board_grid, set_square_piece, set_turn
from src.board.game_state import GameState
from src.board.vision_fen import fen_from_image_bytes
from src.council.demos import list_demos
from src.library.catalog import list_library
from src.llm_logger import recent_logs
from src.orchestrator import ChessMindOrchestrator
from src.storage import delete_game, get_game, list_games

router = APIRouter()
orchestrator = ChessMindOrchestrator()


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


# ── 对弈模式 ──

@router.post("/game/new")
async def new_game(request: Request):
    body = await request.body()
    req = NewGameRequest.model_validate_json(body) if body.strip() else NewGameRequest()
    state = orchestrator.new_game(
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
async def make_move(req: MoveRequest):
    if orchestrator.mode != "human_vs_human":
        if orchestrator.current_controller() != "human":
            raise HTTPException(status_code=400, detail="当前不是人类行棋回合")
    result = await orchestrator.make_move(
        req.uci,
        with_analysis=req.with_analysis,
        analysis_mode=req.analysis_mode,
    )
    if result is None or "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/game/ai-step")
async def ai_step(req: AiStepRequest | None = None):
    with_analysis = None if req is None else req.with_analysis
    result = await orchestrator.ai_step(with_analysis=with_analysis)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/game/state")
def get_state():
    return orchestrator.get_state()


@router.post("/game/load-fen")
def load_fen(req: FenRequest):
    state = orchestrator.load_fen(req.fen)
    if "error" in state:
        raise HTTPException(status_code=400, detail=state)
    return {"status": "ok", **state}


@router.post("/game/analyze-position")
async def analyze_position(req: AnalyzePositionRequest | None = None):
    """分析当前局面（不走子），用于 Demo / 识谱后 Council。"""
    with_analysis = True if req is None else req.with_analysis
    return await orchestrator.analyze_position(with_analysis=with_analysis)


@router.post("/game/post-review")
async def post_game_review():
    """人人局等：终局后统一生成 Council 评价与复盘。"""
    result = await orchestrator.post_game_review()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/game/undo")
def undo_move():
    """悔棋（人 vs AI 尽量回到人类回合）。"""
    result = orchestrator.undo()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/game/hint")
async def hint_move():
    """Stockfish 提示着法（不触发 Council）。"""
    result = await orchestrator.hint()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/game/review")
def game_review():
    """赛后复盘报告（基于本局逐步 Council 缓存）。"""
    return orchestrator.get_review()


@router.post("/game/save")
def save_game(req: SaveGameRequest | None = None):
    title = None if req is None else req.title
    with_review = False if req is None else req.with_review
    saved = orchestrator.persist_game(title=title, with_review=with_review)
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


# ── 对局历史 ──

@router.get("/games")
def games_list(limit: int = Query(30, ge=1, le=100)):
    return {"games": list_games(limit)}


@router.get("/games/{game_id}")
def games_get(game_id: str):
    row = get_game(game_id)
    if not row:
        raise HTTPException(status_code=404, detail="对局不存在")
    return row


@router.delete("/games/{game_id}")
def games_delete(game_id: str):
    if not delete_game(game_id):
        raise HTTPException(status_code=404, detail="对局不存在")
    return {"status": "ok", "deleted": game_id}


@router.post("/games/{game_id}/restore")
def games_restore(game_id: str):
    """恢复历史局面到当前棋盘（不重放逐步分析）。"""
    row = get_game(game_id)
    if not row:
        raise HTTPException(status_code=404, detail="对局不存在")
    fen = row.get("fen_current") or row.get("fen_start")
    if not fen:
        raise HTTPException(status_code=400, detail="该记录无 FEN")
    state = orchestrator.load_fen(fen)
    if "error" in state:
        raise HTTPException(status_code=400, detail=state)
    return {"status": "ok", "restored_from": game_id, **state}


# ── Demo ──

@router.get("/demos")
def demos():
    return {"demos": list_demos()}


@router.post("/demos/{demo_id}/load")
def load_demo(demo_id: str):
    state = orchestrator.load_demo(demo_id)
    if "error" in state:
        raise HTTPException(status_code=404, detail=state)
    return {"status": "ok", **state}


@router.post("/demos/{demo_id}/run")
async def run_demo(demo_id: str):
    """加载高争议 Demo 并立刻跑 Council（路演一键）。"""
    state = orchestrator.load_demo(demo_id)
    if "error" in state:
        raise HTTPException(status_code=404, detail=state)
    analysis = await orchestrator.analyze_position(with_analysis=True)
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
def library_load(item_id: str, req: LibraryLoadRequest | None = None):
    mode = None if req is None else req.mode
    with_analysis = None if req is None else req.with_analysis
    human_color = None if req is None else req.human_color
    free_play = False if req is None else req.free_play
    engine_depth = None if req is None else req.engine_depth
    state = orchestrator.load_library(
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
async def library_step(req: LibraryStepRequest | None = None):
    with_analysis = False if req is None else req.with_analysis
    result = await orchestrator.library_step(with_analysis=with_analysis)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


# ── 多模态识谱 ──

@router.post("/vision/fen")
async def vision_fen(
    file: UploadFile = File(...),
    apply: bool = Query(True, description="识别后是否加载到当前棋局"),
    analyze: bool = Query(False, description="加载后是否立刻跑 Council 分析"),
    side_to_move: str | None = Query(None, description="强制行棋方 w/b/white/black"),
):
    """上传棋盘照片/截图 → FEN，并可直接映射到数字棋盘。"""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="空文件")
    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片过大（限制 12MB）")

    result = await fen_from_image_bytes(
        raw,
        filename=file.filename,
        client=orchestrator.llm_client,
        side_to_move=side_to_move,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)

    state = None
    analysis = None
    if apply:
        state = orchestrator.load_fen(result["fen"])
        if "error" in state:
            raise HTTPException(status_code=400, detail=state)
        if analyze:
            analysis = await orchestrator.analyze_position(with_analysis=True)

    return {"status": "ok", "vision": result, "state": state, "analysis": analysis}


@router.get("/health")
async def health(ping_llm: bool = Query(False, description="是否实际 ping 一次大模型")):
    if ping_llm:
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
    }


@router.get("/logs/recent")
def logs_recent(limit: int = Query(20, ge=1, le=200)):
    return {"count": limit, "logs": recent_logs(limit)}


@router.post("/analyze/pgn")
async def analyze_pgn(req: PGNRequest):
    game = chess.pgn.read_game(StringIO(req.pgn))
    if game is None or not list(game.mainline_moves()):
        raise HTTPException(status_code=400, detail="无法从 PGN 文本中解析出走法")

    replay = GameState(board=game.board())
    results = []
    for move in game.mainline_moves():
        analysis = await orchestrator.analyze_move(replay, move.uci())
        if not analysis or "error" in analysis:
            break
        results.append(analysis)

    return {"total_moves": len(results), "moves": results}
