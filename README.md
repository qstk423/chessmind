# ChessCouncil

**多智能体辩论式国际象棋分析与对战系统。**

三个异质 Agent（战术 / 战略 / 风险）并行给意见；分歧够大时再辩论、质询、仲裁；Stockfish 提供客观计算；教练按水平把结论讲成人话。人机对弈、AI 互搏、名局学习、残局闯关、联机、识谱，共用同一套后端。

> 仓库名历史原因仍为 `chessmind`；产品名以 **ChessCouncil** 为准。

面向 [天津移动 Token 算力大赛 · 赛道二](docs/COMPETE.md) 时可切官方 `glm-5.1`；日常开发可用任意 OpenAI 兼容接口（如千问）。

---

## 为什么这样设计

国际象棋「能算」不难，难的是 **算得清楚、说得明白、还能吵出分歧**。ChessCouncil 把系统拆成两层：

| 层 | 职责 | 当前实现 |
|----|------|----------|
| **Brain（服务端）** | 规则、引擎、LLM Council、对局/房间/学习库、持久化 | Python · FastAPI |
| **Client（客户端）** | 棋盘交互、信息呈现、导航与触控体验 | 手机优先 Web / PWA |

原则：

1. **API 优先** — 所有能力经 HTTP/WebSocket 暴露；网页只是第一个客户端。
2. **引擎与模型不进端** — Stockfish / LLM 留在服务端，客户端保持可替换（Web → 原生 App）。
3. **手机优先** — 对弈 / 学习 / 联机 / 工具分页面 + 底栏；PC 宽屏布局后置。
4. **可降级** — 无 Key、无引擎时 UI 仍可打开，分析与选着软降级。

```
截图 / 数字棋盘 / 联机房间
            ↓
     FEN + python-chess
            ↓
     Stockfish 评估 / 分类
            ↓
   战术 · 战略 · 风险（并行 JSON）
            ↓
        分歧检测
       ↙        ↘
   共识裁决    辩论 → 仲裁
            ↓
          教练讲解
            ↓
     Web / 未来原生客户端
```

---

## 现在能做什么

**对弈**

- 人 vs AI / 人人 / AI vs AI（LLM 选着 ↔ 引擎，非法着法回退）
- 快评 / 深评 Council；着法列表、回放、速度控制；悔棋 / 提示
- 终局杀型结算动画；赛后复盘与准确度相关能力

**学习**

- 名局 / 残局 / 战术库（跟谱演示或 AI 代下）
- 残局闯关（通关解锁）

**联机**

- 房间码 / 分享链接，WebSocket 实时同步（适合同 Wi‑Fi 演示）

**工具**

- 拍照识谱 → FEN（可纠错再分析）
- 对局历史（SQLite）、PGN、路演 Demo、调用日志

**交付形态**

- 手机优先多页 UI + PWA（可「添加到主屏幕」）
- Docker 一键部署（镜像含 Stockfish）
- 冒烟测试与基础限流 / 超时护栏（邀请试用向）

---

## 快速开始

### 环境

- Python ≥ 3.10
- [Stockfish](https://stockfishchess.org/)（`brew install stockfish` / `apt install stockfish`）
- OpenAI 兼容的 `LLM_API_KEY`（可空，则纯引擎降级）

### 本地运行

```bash
git clone https://github.com/qstk423/chessmind.git
cd chessmind
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # 填写 LLM_* ；可选 STOCKFISH_PATH
chmod +x scripts/run_dev.sh
./scripts/run_dev.sh               # 或: python -m src.main
```

浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

**手机（推荐演示路径）**

```bash
HOST=0.0.0.0 ./scripts/run_dev.sh
```

手机与电脑同一局域网，浏览器打开 `http://<电脑局域网IP>:8000`，可「添加到主屏幕」。联机：一机创建房间 → 复制链接给另一台手机。

### Docker

```bash
cp .env.example .env   # 填 Key
docker compose up --build
```

默认 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

### 配置摘要

```ini
# 开发示例（阿里云百炼）
LLM_API_KEY=sk-xxxx
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
VISION_MODEL=qwen-vl-plus

# 大赛运行态
# LLM_MODEL=glm-5.1
# LLM_API_KEY / LLM_BASE_URL = 主办方下发

HOST=0.0.0.0
PORT=8000
```

公网小范围试用前建议：`PUBLIC_DEMO=1`、`ADMIN_TOKEN=...`、收紧 `CORS_ORIGINS`，并跑：

```bash
./scripts/smoke.sh
# 或: pytest -q tests/test_api_smoke.py
```

已知边界：默认进程内共享「单盘分析对局」；联机房间是独立状态。完整账号 / 多租户不在当前范围。

---

## 仓库结构

```
src/
├── main.py              # FastAPI 入口
├── orchestrator.py      # 对局 + Council 编排
├── api/                 # HTTP / WebSocket 路由
├── board/               # 棋局、引擎、识谱、杀型
├── agents/              # 战术 / 战略 / 风险 / 教练 / 选着
├── council/             # 分歧、辩论、复盘、Demo
├── library/             # 名局库与闯关
├── rooms.py / storage.py
frontend/                # 手机优先多页 + PWA
├── index.html           # 对弈
├── learn.html           # 学习
├── online.html          # 联机
├── tools.html           # 工具
docs/COMPETE.md          # 大赛路演与证据包
tests/                   # API 冒烟
```

---

## 主要 API（客户端契约）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/game/new` | 新对局 |
| `POST` | `/api/game/move` | 人类走子 |
| `POST` | `/api/game/ai-step` | AI 一步 |
| `POST` | `/api/game/analyze-position` | 只分析不走子 |
| `GET` | `/api/game/review` | 赛后复盘 |
| `GET` | `/api/library` | 学习库列表 |
| `POST` | `/api/library/{id}/load` | 加载条目 |
| `POST` | `/api/rooms` · `.../join` | 联机房间 |
| `WS` | `/api/rooms/{id}/ws?token=` | 实时同步 |
| `POST` | `/api/vision/fen` | 识谱 |
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/logs/recent` | LLM 调用日志（管理口令） |

走子 / 分析响应中的 `analysis.council` 含 `agents`、`disagreement`、`debate`、`verdict`。完整路演与提交清单见 [`docs/COMPETE.md`](docs/COMPETE.md)。

---

## 路线图（架构视角）

**已落地**

- Council 流水线 + 可演示的手机 Web 客户端
- 学习 / 闯关 / 联机 / 识谱 / PWA 壳
- Docker 与基础上线护栏

**合理下一步（不绑定本仓库是否已开工）**

1. **冻结 API 契约** — 把上表沉淀为稳定文档（或 OpenAPI），作为第二客户端的唯一对接面  
2. **公网部署** — 固定 HTTPS 域名后，手机才真正「装完就能玩」  
3. **安卓原生客户端（可选）** — Kotlin + Jetpack Compose；棋盘与导航原生，Brain 仍走本仓库 API  
4. **iOS** — 同一契约下的 SwiftUI 客户端  
5. **多租户 / 账号** — 仅在需要公开运营时再上

原生客户端是 **换壳，不换脑**：先把服务端当产品真相来源，再谈商店与安装包。

---

## License

[MIT](LICENSE)
