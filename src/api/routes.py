"""FastAPI 路由——对弈模式 + PGN 分析模式"""
from io import StringIO

import chess.pgn
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.board.game_state import GameState
from src.orchestrator import ChessMindOrchestrator

router = APIRouter()
orchestrator = ChessMindOrchestrator()

# 引擎的启动/关闭由 main.py 的 lifespan 管理


class MoveRequest(BaseModel):
    uci: str


class PGNRequest(BaseModel):
    pgn: str


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
    使用独立 GameState 重放，不覆盖当前对局。
    """
    game = chess.pgn.read_game(StringIO(req.pgn))
    if game is None or not list(game.mainline_moves()):
        raise HTTPException(status_code=400, detail="无法从 PGN 文本中解析出走法")

    # 独立棋局（含 FEN 头的自定义起始局面），不影响主对局
    replay = GameState(board=game.board())
    results = []
    for move in game.mainline_moves():
        analysis = await orchestrator.analyze_move(replay, move.uci())
        if not analysis or "error" in analysis:
            # PGN 与重放棋局不一致，后续走法已无意义
            break
        results.append(analysis)

    return {"total_moves": len(results), "moves": results}
