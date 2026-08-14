# ChessMind ♟️

国际象棋多 Agent 实时分析系统——在自建棋盘上每走一步，
战术/战略/开局三个 Agent 并行分析后汇总，Stockfish 引擎交叉验证。

## 快速启动

```bash
cd chessmind
pip install -r requirements.txt
brew install stockfish
cp .env.example .env   # 编辑填入 LLM API Key
python -m src.main
```

打开 http://localhost:8000

## 项目结构

- `src/main.py` — FastAPI 入口
- `src/orchestrator.py` — 多 Agent 编排总控
- `src/board/game_state.py` — 走子、PGN、棋局记录
- `src/board/move_evaluator.py` — Stockfish 评分 + 走子分类
- `src/agents/tactical.py` — 战术 Agent
- `src/agents/strategic.py` — 战略 Agent
- `src/agents/pattern.py` — 开局模式 Agent
- `src/agents/summarizer.py` — 汇总 Agent
- `src/api/routes.py` — API 路由
- `frontend/` — 棋盘 UI + 分析面板
