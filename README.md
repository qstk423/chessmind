# ChessCouncil

**多智能体辩论式国际象棋分析与对战系统。**

ChessCouncil 把「算得清楚」和「说得明白」拆开：服务端用 Stockfish 做客观计算，再用战术 / 战略 / 风险三个 Agent 并行给意见；分歧够大时进入辩论与仲裁；教练按水平把结论讲成人话。Web 客户端负责棋盘、学习和联机演示。

| | |
|---|---|
| 仓库 | [github.com/qstk423/chessmind](https://github.com/qstk423/chessmind)（仓库名历史为 `chessmind`，**产品名以 ChessCouncil 为准**） |
| 姐妹项目 | [Xiangqi Council](https://github.com/qstk423/Xiang-qi-gaming)（中国象棋侧，信息架构对齐） |
| 大赛说明 | [docs/COMPETE.md](docs/COMPETE.md) |

---

## 一句话定位

这不是又一个「网页棋盘」，而是一套 **API 优先的 Brain + Client**：

| 层级 | 职责 | 当前实现 |
|------|------|----------|
| Brain | 规则、Stockfish、LLM Council、房间、学习库、历史 | Python · FastAPI |
| Client | 棋盘交互、分析呈现、四页导航 / PWA | 手机优先 Web |

无 LLM Key、无 Stockfish 时界面仍可打开；分析与选着会软降级。

---

## 当前完成度（诚实口径）

| 模块 | 完成度 | 说明 |
|------|--------|------|
| 对弈（人人 / 人机 / AI） | ~90% | 新局、走子、悔棋、提示、复盘；按 `X-Session-Id` 隔离 |
| Council | ~85% | 三师并行 + 辩论 / 仲裁；日志用 ContextVar 防串局 |
| 学习 / 闯关 | ~78% | 名局 / 残局 / 战术 + 闯关；进度在本机 localStorage |
| 联机 | ~70% | WebSocket 房间；进程内状态，适合同网演示 |
| 工具 / 识谱 / 历史 | ~75% | FEN、PGN、识谱、SQLite 历史；按 `X-Owner-Id` 隔离 |
| 测试 / 部署 | ~70% | pytest 冒烟、Docker、限流；非完整生产运维 |

**适合：** 大赛路演、同网邀请试用、产品形态验证。  
**不适合直接宣称：** 公网多租户运营、完整账号体系、原生 App 商店上架。

---

## 功能概览

### 对弈

- 人 vs AI / 人人 / AI vs AI
- 快评 / 深评 Council；着法列表与回放；悔棋 / 提示
- 终局结算与赛后复盘、准确度相关能力
- 浏览器会话隔离：请求携带 `X-Session-Id`（前端写入 `sessionStorage`）

### 学习

- 名局 / 残局 / 战术库（跟谱或自由推演）
- 残局闯关（本地通关解锁）

### 联机

- 房间码 / 分享链接，WebSocket 同步（同网演示级）

### 工具

- 拍照识谱 → FEN（可纠错再分析）
- 对局历史（SQLite）、PGN、路演 Demo
- LLM 调用日志（需 `X-Admin-Token`）

### 安全与护栏（本轮加固）

- 历史读写按 `X-Owner-Id` 隔离；越权返回 404，无身份返回 401
- 自动存档与手动保存共用同一 `owner_id`
- 无归属历史 **仅管理员** 可 `adopt_orphans=1` 认领；普通用户默认关闭
- 历史标题等用户文本走安全 DOM / 转义，降低存储型 XSS
- API 限流、`PUBLIC_DEMO` + `ADMIN_TOKEN` 敏感口令

---

## 快速开始

### 环境

- Python ≥ 3.10
- [Stockfish](https://stockfishchess.org/)（推荐 `brew install stockfish` / `apt install stockfish`）
- 可选：OpenAI 兼容 `LLM_API_KEY`

### 本地运行

```bash
git clone https://github.com/qstk423/chessmind.git
cd chessmind
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # 填写 LLM_* ；可选 STOCKFISH_PATH
chmod +x scripts/run_dev.sh scripts/smoke.sh
./scripts/run_dev.sh               # 或: python -m src.main
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)

手机同网演示：

```bash
HOST=0.0.0.0 ./scripts/run_dev.sh
# 手机访问 http://<电脑局域网IP>:8000
```

### Docker

```bash
cp .env.example .env
docker compose up --build
```

### 测试与冒烟

```bash
pytest -q tests/test_api_smoke.py
./scripts/smoke.sh                 # 需服务已启动；固定 Session/Owner 头
```

### 关键配置

```ini
LLM_API_KEY=sk-xxxx
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
VISION_MODEL=qwen-vl-plus
STOCKFISH_PATH=stockfish
HOST=0.0.0.0
PORT=8000
PUBLIC_DEMO=1
ADMIN_TOKEN=please-change-me
CORS_ORIGINS=https://your.domain
```

---

## 仓库结构

```
src/
├── main.py              # FastAPI 入口
├── orchestrator.py      # 对局 + Council 编排
├── sessions.py          # 浏览器会话池（共享引擎，隔离盘面）
├── storage.py           # SQLite 历史
├── guardrails.py        # 限流 / admin / owner
├── llm_logger.py        # ContextVar 隔离的调用日志
├── api/                 # HTTP / WebSocket
├── board/               # 棋局、引擎、识谱
├── agents/              # 战术 / 战略 / 风险 / 教练 / 选着
├── council/             # 分歧、辩论、复盘、Demo
├── library/             # 名局与闯关
frontend/                # index / learn / online / tools + PWA
tests/                   # API 冒烟与安全回归
scripts/                 # run_dev / smoke
docs/COMPETE.md          # 大赛路演说明
```

---

## 主要 API

客户端请求普通对弈接口时应带：

- `X-Session-Id`：盘面隔离
- `X-Owner-Id`：历史归属（≥8 字符的本机身份）

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/game/new` | 新对局 |
| `POST` | `/api/game/move` | 走子（可触发自动存档） |
| `POST` | `/api/game/ai-step` | AI 一步 |
| `POST` | `/api/game/analyze-position` | 只分析不走子 |
| `GET` | `/api/game/review` | 赛后复盘 |
| `GET` | `/api/games` | 历史列表（按 owner） |
| `GET` | `/api/library` | 学习库 |
| `POST` | `/api/rooms` · `.../join` | 联机 |
| `WS` | `/api/rooms/{id}/ws?token=` | 实时同步 |
| `POST` | `/api/vision/fen` | 识谱 |
| `GET` | `/api/logs/recent` | LLM 日志（admin） |

走子 / 分析响应中的 `analysis.council` 含 `agents`、`disagreement`、`debate`、`verdict`。

---

## 已知边界

1. `X-Owner-Id` / `X-Session-Id` 是**浏览器本地身份**，不是登录账号；可被伪造，仅适合演示与小范围试用。
2. 会话与联机房间主要在**单进程内存**；多 worker / 重启会丢状态。
3. Stockfish 实例共享并串行加锁，高并发会排队。
4. 公网部署请设置 `ADMIN_TOKEN`、`PUBLIC_DEMO=1`，并收紧 `CORS_ORIGINS`。
5. 完整多租户、大厅观战、原生客户端不在当前范围。

---

## 路线图

**已完成**

- Council 流水线 + 手机优先 Web / PWA
- 学习 / 闯关 / 联机 / 识谱
- 会话隔离、历史归属、自动存档、日志 ContextVar
- Docker、限流、冒烟回归

**下一步**

1. 冻结 OpenAPI 契约  
2. 公网 HTTPS 与更严安全头 / CSP  
3. 与 Xiangqi Council 合并：`game_type=chess|xiangqi`  
4. 真账号或多端签名令牌（替代可伪造 owner）  
5. 可选原生壳：换壳不换脑，仍走本仓库 API  

---

## 相关项目

| 项目 | 关系 |
|------|------|
| [Xiangqi Council](https://github.com/qstk423/Xiang-qi-gaming) | 中国象棋姐妹项目，目标统一产品壳 |
| [Stockfish](https://github.com/official-stockfish/Stockfish) | 国际象棋 UCI 引擎 |
| [Pikafish](https://github.com/official-pikafish/Pikafish) | 象棋侧目标引擎（由姐妹项目接入） |

---

## 许可证

[MIT](LICENSE)。第三方引擎 / 云 API 仍受其自身条款约束。
