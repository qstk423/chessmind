"""FastAPI 路由——对弈模式 + PGN 分析模式"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.orchestrator import ChessMindOrchestrator

router = APIRouter()
orchestrator = ChessMindOrchestrator()


class MoveRequest(BaseModel):
    uci: str


class PGNRequest(BaseModel):
    pgn: str


class GameResponse(BaseModel):
    fen: str
    move_count: int
    is_game_over: bool
    result: str | None
    legal_moves: list[str]
    pgn: str


@router.on_event("startup")
async def startup():
    await orchestrator.connect()


@router.on_event("shutdown")
def shutdown():
    orchestrator.close()


# ── 对弈模式 ──

@router.post("/game/new")
def new_game():
    """开始新对局"""
    orchestrator.new_game()
    return {"status": "ok", "fen": orchestrator.game.fen}


@router.post("/game/move")
async def make_move(req: MoveRequest):
    """走一步棋，返回完整分析"""
    result = await orchestrator.make_move(req.uci)
    if result is None or "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/game/state")
def get_state():
    """获取当前棋局状态"""
    return orchestrator.get_state()


# ── PGN 分析模式 ──

@router.post("/analyze/pgn")
async def analyze_pgn(req: PGNRequest):
    """
    导入 PGN 文本并逐步复盘分析。
    返回每一步的分析结果列表。
    """
    import chess.pgn
    from io import StringIO

    pgn_io = StringIO(req.pgn)
    game = chess.pgn.read_game(pgn_io)
    if game is None:
        raise HTTPException(status_code=400, detail="无法解析 PGN 文本")

    orchestrator.new_game()
    board = game.board()
    results = []

    for move in game.mainline_moves():
        uci = move.uci()
        analysis = await orchestrator.make_move(uci)
        if analysis:
            results.append(analysis)

    return {"total_moves": len(results), "moves": results}
