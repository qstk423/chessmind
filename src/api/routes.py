"""FastAPI 路由——对弈 / Council / Demo / 复盘 / 多模态识谱"""
from io import StringIO
from typing import Literal

import chess.pgn
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from src.board.game_state import GameState
from src.board.vision_fen import fen_from_image_bytes
from src.council.demos import list_demos
from src.llm_logger import recent_logs
from src.orchestrator import ChessMindOrchestrator

router = APIRouter()
orchestrator = ChessMindOrchestrator()


class MoveRequest(BaseModel):
    uci: str
    with_analysis: bool | None = None


class NewGameRequest(BaseModel):
    mode: Literal["human_vs_human", "human_vs_ai", "ai_vs_ai"] = "human_vs_human"
    human_color: Literal["white", "black"] = "white"
    white_ai: Literal["llm", "engine"] = "llm"
    engine_depth: int | None = Field(default=None, ge=1, le=25)
    with_analysis: bool = True
    coach_level: Literal["beginner", "intermediate", "advanced"] = "intermediate"


class PGNRequest(BaseModel):
    pgn: str


class AiStepRequest(BaseModel):
    with_analysis: bool | None = None


class FenRequest(BaseModel):
    fen: str


class AnalyzePositionRequest(BaseModel):
    with_analysis: bool = True


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
    )
    return {"status": "ok", **state}


@router.post("/game/move")
async def make_move(req: MoveRequest):
    if orchestrator.mode != "human_vs_human":
        if orchestrator.current_controller() != "human":
            raise HTTPException(status_code=400, detail="当前不是人类行棋回合")
    result = await orchestrator.make_move(req.uci, with_analysis=req.with_analysis)
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


@router.get("/game/review")
def game_review():
    """赛后复盘报告（基于本局逐步 Council 缓存）。"""
    return orchestrator.get_review()


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


# ── 多模态识谱 ──

@router.post("/vision/fen")
async def vision_fen(file: UploadFile = File(...), apply: bool = Query(True)):
    """上传棋盘截图识别 FEN；apply=true 时加载到当前棋局。"""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="空文件")
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片过大（限制 8MB）")

    result = await fen_from_image_bytes(raw, filename=file.filename, client=orchestrator.llm_client)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)

    state = None
    if apply:
        state = orchestrator.load_fen(result["fen"])
        if "error" in state:
            raise HTTPException(status_code=400, detail=state)

    return {"status": "ok", "vision": result, "state": state}


@router.get("/health")
async def health(ping_llm: bool = Query(False, description="是否实际 ping 一次大模型")):
    if ping_llm:
        return await orchestrator.health()
    state = orchestrator.get_state()
    return {
        "stockfish": orchestrator._connected,
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
