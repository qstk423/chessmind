# ChessCouncil

**多智能体辩论式棋类分析与对战系统——国际象棋 + 中国象棋，同一产品壳。**

ChessCouncil 把「算得清楚」和「说得明白」拆开：国际象棋侧用 Stockfish + LLM Council；中国象棋侧用内建规则引擎 + 启发式 Council。顶栏一键切换棋种（对弈↔对弈、学习↔学习），记住上次选择；不是双卡片门户页。

| | |
|---|---|
| 仓库 | [github.com/qstk423/chessmind](https://github.com/qstk423/chessmind)（仓库名历史为 `chessmind`，**产品名以 ChessCouncil 为准**） |
| 象棋源码归档 | 原 [Xiangqi Council](https://github.com/qstk423/Xiang-qi-gaming) 已并入本仓 `src/xiangqi` + `frontend/xiangqi` |
| 大赛说明 | [docs/COMPETE.md](docs/COMPETE.md) |

---

## 一句话定位

这不是又一个「网页棋盘」，而是一套 **API 优先的 Brain + Client**：

| 层级 | 职责 | 当前实现 |
|------|------|----------|
| Brain | 两套规则引擎、Stockfish（国际象棋）、Council、房间、学习库 | Python · FastAPI 单进程 |
| Client | `/chess/` · `/xiangqi/` 分壳；顶栏棋种切换；四页导航 / PWA | 手机优先 Web |

入口 `/` 按 `localStorage.cc_variant` 瞬时跳转到上次棋种（默认国际象棋）。无 LLM Key、无 Stockfish 时界面仍可打开；分析与选着会软降级。

---

## 当前完成度（诚实口径）

| 模块 | 完成度 | 说明 |
|------|--------|------|
| 双棋种壳 | ~85% | 同进程双 API + 顶栏切换；规则引擎未统一 |
| 对弈（人人 / 人机 / AI） | ~90% | 新局、走子、悔棋、提示、复盘；按 `X-Session-Id` 隔离 |
| Council（国际象棋） | ~85% | 三师并行 + 辩论 / 仲裁；日志用 ContextVar 防串局 |
| Council（中国象棋） | ~70% | 启发式分析 MVP |
| 学习 / 闯关 | ~78% | 名局 / 残局 / 战术 + 闯关；进度在本机 localStorage |
| 联机 | ~70% | WebSocket 房间；进程内状态，适合同网演示 |
| 工具 / 识谱 / 历史 | ~75% | 国际象棋侧含识谱与 SQLite 历史 |
| 测试 / 部署 | ~75% | pytest 冒烟（chess + xiangqi）、Docker、限流 |

**适合：** 大赛路演、同网邀请试用、产品形态验证。  
**不适合直接宣称：** 公网多租户运营、完整账号体系、原生 App 商店上架。

---

## 功能概览

### 棋种切换（方案 A）

- 顶栏：`国际象棋 | 中国象棋`
- 同级页跳转（对弈 / 学习 / 联机 / 工具）
- `localStorage.cc_variant` 记忆上次选择

### 对弈

- 人 vs AI / 人人 /（国际象棋）AI vs AI
- 快评 / 深评 Council；着法列表与回放；悔棋 / 提示
- 浏览器会话隔离：请求携带 `X-Session-Id`

### 学习

- 名局 / 残局 / 战术库（跟谱或自由推演）
- 残局闯关（本地通关解锁）

### 联机

- 房间码 / 分享链接，WebSocket 同步（同网演示级）

### 工具

- 国际象棋：拍照识谱 → FEN、对局历史、PGN、Demo
- 中国象棋：FEN 导入 / 导出

### 安全与护栏

- 历史读写按 `X-Owner-Id` 隔离
- API 限流对 `/api`、`/api/chess`、`/api/xiangqi` 共用规则并分桶
- 基础安全响应头（`nosniff` / `SAMEORIGIN` / CSP）
- OpenAPI 快照：`python scripts/export_openapi.py` → `docs/openapi.json`

---

## 快速开始

### 环境

- Python ≥ 3.10
- [Stockfish](https://stockfishchess.org/)（推荐 `brew install stockfish` / `apt install stockfish`；仅国际象棋需要）
- 可选：OpenAI 兼容 `LLM_API_KEY`

### 本地运行

```bash
git clone https://github.com/qstk423/chessmind.git
cd chessmind
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
chmod +x scripts/run_dev.sh scripts/smoke.sh
./scripts/run_dev.sh
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000) → 自动进入上次棋种；也可直达：

- 国际象棋：[http://127.0.0.1:8000/chess/](http://127.0.0.1:8000/chess/)
- 中国象棋：[http://127.0.0.1:8000/xiangqi/](http://127.0.0.1:8000/xiangqi/)

手机同网：

```bash
HOST=0.0.0.0 ./scripts/run_dev.sh
```

### Docker

```bash
cp .env.example .env
docker compose up --build
```

### 测试与冒烟

```bash
pytest -q tests/test_api_smoke.py tests/xiangqi/
./scripts/smoke.sh
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
OWNER_SECRET=please-change-owner-secret
CORS_ORIGINS=https://your.domain
```

---

## 仓库结构

```
src/
├── main.py              # FastAPI 入口（双棋种挂载）
├── orchestrator.py      # 国际象棋对局 + Council
├── xiangqi/             # 中国象棋规则 / AI / 房间 / API
├── api/                 # 国际象棋 HTTP / WebSocket
frontend/
├── index.html           # 瞬时跳转入口
├── shared/              # 棋种切换
├── chess/               # 国际象棋 UI + PWA
└── xiangqi/             # 中国象棋 UI
tests/                   # API 冒烟 + xiangqi 规则/谜题
```

---

## 主要 API

| 前缀 | 说明 |
|------|------|
| `/api/chess/*` | 国际象棋正式前缀 |
| `/api/*` | 兼容旧客户端（同 chess） |
| `/api/xiangqi/*` | 中国象棋 |

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` · `/api/chess/health` | 健康检查（含 `variants`） |
| `GET` | `/api/xiangqi/health` | 象棋健康检查 |
| `POST` | `/api/game/new` · `/api/xiangqi/game/new` | 新对局 |
| `POST` | `.../game/move` | 走子 |
| `WS` | `.../rooms/{id}/ws?token=` | 实时同步 |

---

## 已知边界

1. `X-Owner-Id` / `X-Session-Id` 是浏览器本地身份，不是登录账号。
2. 会话与联机房间主要在单进程内存。
3. 两套规则引擎与 UI **未统一**；合并的是产品壳与进程。
4. 公网部署请设置 `ADMIN_TOKEN`、`PUBLIC_DEMO=1`，并收紧 `CORS_ORIGINS`。

---

## 路线图

**已完成**

- Council 流水线 + 手机优先 Web / PWA
- 学习 / 闯关 / 联机 / 识谱
- **双棋种同进程：顶栏切换（方案 A）**

**下一步**

1. 公网 HTTPS、IP 级硬限流与更严 CSP  
2. 象棋侧更强引擎（如 Pikafish）可选接入  
3. 真账号体系  
4. 可选原生壳  

---

## 相关项目

| 项目 | 关系 |
|------|------|
| [Xiangqi Council](https://github.com/qstk423/Xiang-qi-gaming) | 已并入本仓；原仓库可作归档对照 |
| [Stockfish](https://github.com/official-stockfish/Stockfish) | 国际象棋 UCI 引擎 |
| [Pikafish](https://github.com/official-pikafish/Pikafish) | 象棋侧目标引擎（可选后续接入） |

---

## 许可证

[MIT](LICENSE)。第三方引擎 / 云 API 仍受其自身条款约束。
