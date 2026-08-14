"""ChessMind 入口——启动 FastAPI 服务"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from src.api.routes import router
import os

app = FastAPI(title="ChessMind", description="国际象棋多 Agent 分析系统")

# API 路由
app.include_router(router, prefix="/api")

# 前端静态文件
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")


def main():
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
