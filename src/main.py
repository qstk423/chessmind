"""ChessCouncil 入口——启动 FastAPI 服务"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.online import router as rooms_router
from src.api.routes import orchestrator, router
from src.storage import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化 DB、连接 Stockfish，退出时关闭"""
    init_db()
    await orchestrator.connect()
    yield
    orchestrator.close()


app = FastAPI(
    title="ChessCouncil",
    description="多 Agent 协作辩论的实时国际象棋分析与对战系统",
    lifespan=lifespan,
)

# 联机部署：默认同源；若前后端分离可设 CORS_ORIGINS=* 或逗号列表
_cors = os.getenv("CORS_ORIGINS", "*").strip()
_origins = ["*"] if _cors == "*" else [o.strip() for o in _cors.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(rooms_router, prefix="/api")

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")


def main():
    import uvicorn

    # 联机默认监听全网卡；本机调试可 HOST=127.0.0.1
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("src.main:app", host=host, port=port)


if __name__ == "__main__":
    main()
