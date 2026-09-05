"""ChessCouncil 入口——启动 FastAPI 服务"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.online import router as rooms_router
from src.api.routes import orchestrator, router
from src.guardrails import check_rate_limit
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


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            check_rate_limit(request)
        except Exception as exc:
            from fastapi import HTTPException

            if isinstance(exc, HTTPException):
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
            raise
        return await call_next(request)


app.add_middleware(RateLimitMiddleware)

# 公开展示建议收紧；开发默认同源可用 *
_cors = os.getenv("CORS_ORIGINS", "*").strip()
_origins = ["*"] if _cors == "*" else [o.strip() for o in _cors.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    from fastapi import HTTPException

    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(
        status_code=500,
        content={"detail": f"服务器内部错误：{type(exc).__name__}"},
    )


app.include_router(router, prefix="/api")
app.include_router(rooms_router, prefix="/api")

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")


def main():
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("src.main:app", host=host, port=port)


if __name__ == "__main__":
    main()
