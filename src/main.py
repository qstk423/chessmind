"""ChessMind 入口——启动 FastAPI 服务"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.api.routes import orchestrator, router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时连接 Stockfish 引擎，退出时关闭"""
    await orchestrator.connect()
    yield
    orchestrator.close()


app = FastAPI(
    title="ChessCouncil",
    description="多 Agent 协作辩论的实时国际象棋分析与对战系统",
    lifespan=lifespan,
)

# API 路由
app.include_router(router, prefix="/api")

# 前端静态文件
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")


def main():
    import uvicorn
    # 只监听本机；需要局域网访问时自行改为 0.0.0.0 并注意无鉴权风险
    uvicorn.run("src.main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
