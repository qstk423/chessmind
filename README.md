# ChessCouncil

基于多智能体协作辩论的实时国际象棋分析与对战系统（由 ChessMind 增量升级）。

> 战术 / 战略 / 风险三类异质 Agent 并行分析；出现明显分歧时触发辩论与交叉质询；Stockfish 提供客观计算并参与仲裁；教练按用户水平生成可解释讲解。支持人机对弈与 AI vs AI 算法对抗。

面向 **天津移动 Token 算力大赛 · 赛道二** 时，运行态切换到官方 `glm-5.1` 即可；开发期可用阿里云千问等 OpenAI 兼容接口。

## 功能一览

- **完整对局循环**：人人分析 / 人 vs AI / AI vs AI
- **算法对抗**：LLM 合法着法选着 vs Stockfish；非法着法自动回退引擎
- **ChessCouncil 流水线**：结构化 JSON 意见 → 争议度 → 辩论（可选）→ 仲裁 → 教练讲解
- **走子轨迹**：半透明起点 + 虚线路径 + 终点高亮（JJ 风格）
- **路演 Demo**：希腊赠礼等高争议局面一键 Council
- **赛后复盘**：争议步、辩论次数、叙事与 PGN
- **多模态识谱**：棋盘截图 → FEN，支持格子纠错后再分析
- **对局历史**：SQLite 持久化，可恢复局面
- **路演快捷栏**：一键希腊赠礼 / 快速 AI 对战 / 调用证明
- **离线前端资源**：jQuery / chessboard / 棋子图本地 vendor，弱网可演示
- **调用日志**：`logs/llm_calls.jsonl`，便于大赛提交调用证明
- **无 Key / 无引擎降级**：仍可打开 UI；LLM 与 Stockfish 缺失时软降级
- **Docker**：`docker compose up` 一键部署（镜像内含 Stockfish）

## 工作原理

```
现实棋盘 / 截图 / 数字棋盘
        ↓
结构化局面（FEN + python-chess 接地事实）
        ↓
Stockfish 评估 / PV / 走子分类
        ↓
战术 · 战略 · 风险  Agent（并行，JSON）
        ↓
分歧检测（争议度 0~1）
   ↙            ↘
共识裁决      风险质询 → 答辩 → 仲裁官
        ↓
教练（beginner / intermediate / advanced）
        ↓
前端可视化 + 赛后复盘
```

## 环境要求

- Python ≥ 3.10
- Stockfish（`brew install stockfish` 或 `apt install stockfish`）
- LLM API Key（OpenAI 兼容）

## 快速启动

```bash
git clone https://github.com/qstk423/chessmind.git
cd chessmind
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # 填入 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
python -m src.main
```

打开 http://127.0.0.1:8000

### Docker 一键部署

```bash
cp .env.example .env   # 填入 Key
docker compose up --build
```

服务监听 `http://127.0.0.1:8000`；对局库与日志挂载到 named volume。

### `.env` 示例

**开发（阿里云百炼千问）：**

```ini
LLM_API_KEY=sk-xxxx
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
VISION_MODEL=qwen-vl-plus
STOCKFISH_PATH=stockfish
COACH_LEVEL=intermediate
DEBATE_THRESHOLD=0.5
```

**大赛运行态（Token 下发后）：**

```ini
LLM_API_KEY=<天津移动下发>
LLM_BASE_URL=<天津移动下发>
LLM_MODEL=glm-5.1
```

## 主要 API

| 端点 | 说明 |
|---|---|
| `POST /api/game/new` | 新对局（`mode` / `coach_level` / `with_analysis` …） |
| `POST /api/game/move` | 人类走子 |
| `POST /api/game/ai-step` | AI 走一步 |
| `POST /api/game/analyze-position` | 分析当前局面（不走子） |
| `GET /api/game/review` | 赛后复盘报告 |
| `GET /api/demos` | 路演 Demo 列表 |
| `POST /api/demos/{id}/run` | 加载 Demo 并跑 Council |
| `POST /api/vision/fen` | 上传截图识别 FEN |
| `POST /api/game/save` | 手动保存当前对局到 SQLite |
| `GET /api/games` | 对局历史列表 |
| `POST /api/games/{id}/restore` | 恢复历史局面 |
| `POST /api/fen/set-square` | FEN 纠错：改格子 |
| `GET /api/health?ping_llm=true` | 健康检查 |
| `GET /api/logs/recent` | 最近 LLM 调用日志 |

走子 / 局面分析响应中的 `analysis.council` 包含：`agents`、`disagreement`、`debate`、`verdict`。

## 项目结构

```
src/
├── main.py                 # FastAPI 入口
├── config.py
├── llm_logger.py           # JSONL 调用证明
├── orchestrator.py         # 对局 + Council 编排
├── api/routes.py
├── board/                  # 棋局、Stockfish、识谱
├── agents/                 # 战术/战略/风险/教练/选着 + schema
└── council/                # 分歧检测、辩论、复盘、Demo
frontend/                   # 棋室风格 UI
docs/COMPETE.md             # 大赛路演与提交清单
```

## 大赛提交

详见 [`docs/COMPETE.md`](docs/COMPETE.md)：5 分钟路演脚本、调用证明、Demo 操作顺序。

## License

MIT
