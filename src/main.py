"""ChessCouncil 入口——国际象棋 + 中国象棋 同一进程。"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.online import router as chess_rooms_router
from src.api.routes import orchestrator, router as chess_router
from src.guardrails import check_rate_limit
from src.storage import init_db
from src.xiangqi.api.online import router as xiangqi_rooms_router
from src.xiangqi.api.routes import router as xiangqi_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化 DB、连接 Stockfish，退出时关闭"""
    init_db()
    await orchestrator.connect()
    yield
    orchestrator.close()


app = FastAPI(
    title="ChessCouncil",
    description="多智能体理事会：国际象棋 + 中国象棋",
    version=os.getenv("APP_VERSION", "0.5.0"),
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


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(self), microphone=(), geolocation=()",
        )
        if "Content-Security-Policy" not in response.headers:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "img-src 'self' data: blob: https:; "
                "media-src 'self' blob:; "
                "style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; "
                "connect-src 'self' ws: wss: http: https:; "
                "font-src 'self' data:; "
                "frame-ancestors 'self'"
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)

_cors = os.getenv("CORS_ORIGINS", "*").strip()
_origins = ["*"] if _cors == "*" else [o.strip() for o in _cors.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_origins != ["*"],
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


# 国际象棋：正式前缀 + 兼容旧 /api 别名
app.include_router(chess_router, prefix="/api/chess")
app.include_router(chess_rooms_router, prefix="/api/chess")
app.include_router(chess_router, prefix="/api")
app.include_router(chess_rooms_router, prefix="/api")

# 中国象棋
app.include_router(xiangqi_router, prefix="/api/xiangqi")
app.include_router(xiangqi_rooms_router, prefix="/api/xiangqi")

frontend_path = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/")
async def root_entry():
    """瞬时入口：按 localStorage 上次棋种跳转（见 frontend/index.html）。"""
    return FileResponse(frontend_path / "index.html")


if frontend_path.exists():
    app.mount("/chess", StaticFiles(directory=frontend_path / "chess", html=True), name="chess_ui")
    app.mount(
        "/xiangqi", StaticFiles(directory=frontend_path / "xiangqi", html=True), name="xiangqi_ui"
    )
    shared = frontend_path / "shared"
    if shared.exists():
        app.mount("/shared", StaticFiles(directory=shared), name="shared")


def main():
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("src.main:app", host=host, port=port)


if __name__ == "__main__":
    main()
