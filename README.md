# ChessCouncil

**多智能体辩论式棋类分析与对战系统 —— 国际象棋 + 中国象棋，同一产品壳。**

ChessCouncil 把「算得清楚」和「说得明白」拆开：服务端负责规则、引擎与理事会（Council），Web 客户端负责棋盘交互与结果呈现。国际象棋侧用 [Stockfish](https://stockfishchess.org/) + 三师 LLM Council；中国象棋侧用内建规则引擎 + 启发式 Council。顶栏一键切换棋种（对弈↔对弈、学习↔学习），记住上次选择——**不是**双卡片门户页。

| | |
|---|---|
| 仓库 | [github.com/qstk423/chessmind](https://github.com/qstk423/chessmind)（历史仓库名仍为 `chessmind`；**产品名以 ChessCouncil 为准**） |
| 象棋源码 | 原 [Xiangqi Council](https://github.com/qstk423/Xiang-qi-gaming) 已并入本仓 `src/xiangqi` · `frontend/xiangqi` |
| 大赛说明 | [docs/COMPETE.md](docs/COMPETE.md) |

---

## 概述

棋类「能算」不难，难的是 **算得清楚、说得明白、还能吵出分歧**。ChessCouncil 把系统拆成两层、两种棋：

| 层级 | 职责 | 当前实现 |
|------|------|----------|
| Brain（服务端） | 两套规则引擎、Stockfish（国际象棋）、Council、对局 / 房间 / 学习库 | Python · FastAPI **单进程** |
| Client（客户端） | `/chess/` · `/xiangqi/` 分壳；顶栏棋种切换；四页导航 | 手机优先 Web / PWA |

入口 `/` 按 `localStorage.cc_variant` 瞬时跳转到上次棋种（默认国际象棋）。

**它包含：**

- 双棋种对弈：人机 / 人人；（国际象棋）另有 AI vs AI
- Council 分析：国际象棋为战术 / 战略 / 风险并行 + 分歧辩论；中国象棋为同结构启发式 MVP
- 名局 / 残局 / 战术学习与残局闯关
- WebSocket 联机房间（同网演示级）
- 国际象棋：拍照识谱、对局历史、PGN、路演 Demo
- Docker、pytest 冒烟（chess + xiangqi）、基础限流护栏

**它目前不包含：**

- 完整的公开运营账号体系 / 多租户
- 统一的「一套棋盘抽象」——合并的是**产品壳与进程**，不是规则引擎
- 应用商店级原生客户端（安卓 / iOS 仅为路线图上的「换壳」选项）
- 把引擎或 LLM 打进浏览器端

原则是：先把 **API 契约与 Brain** 当作产品真相来源，客户端可替换。无 Key、无 Stockfish 时界面仍可打开；分析与选着会软降级。

---

## 设计原则

1. **API 优先** — 能力经 HTTP / WebSocket 暴露；网页只是第一个客户端。
2. **引擎与模型不进端** — Stockfish / LLM 留在服务端，换壳不必重做 Brain。
3. **手机优先、壳一致** — 两棋种共用：紧凑顶栏 + 底栏四页 + 棋盘区 / Council 下滑；配色可不同（国际象棋墨绿木色，中国象棋墨褐朱砂）。
4. **棋种可切换、状态可记忆** — 顶栏 `国际象棋 | 中国象棋`；同级页跳转；`cc_variant` 持久化。
5. **可降级** — 缺少 LLM Key 或 Stockfish 时，界面与基础对弈仍可用。
6. **许可证清晰** — 本仓库 MIT；第三方引擎 / 云 API 须遵守其自身条款。

国际象棋分析流水线：

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

中国象棋侧目前为同结构启发式 Council（评估条 · 三师推荐 · 标签页 · 争议辩论），规则引擎内建于 `src/xiangqi/rules.py`。

---

## 当前完成度（诚实口径）

| 模块 | 完成度 | 说明 |
|------|--------|------|
| 双棋种壳 | ~88% | 同进程双 API + 顶栏切换 + 排版对齐；规则引擎未统一 |
| 对弈 | ~90% | 新局、走子、悔棋、提示；`X-Session-Id` 隔离 |
| Council（国际象棋） | ~85% | 三师并行 + 辩论 / 仲裁；日志 ContextVar 防串局 |
| Council（中国象棋） | ~70% | 启发式分析 MVP |
| 学习 / 闯关 | ~78% | 名局 / 残局 / 战术 + 闯关；进度在本机 |
| 联机 | ~70% | WebSocket 房间；进程内状态，适合同网演示 |
| 工具 / 识谱 / 历史 | ~75% | 识谱与 SQLite 历史主要在国际象棋侧 |
| 测试 / 部署 | ~75% | pytest 双测、Docker、限流 |

**适合：** 大赛路演、同网邀请试用、产品形态验证。  
**不适合直接宣称：** 公网多租户运营、完整账号体系、原生商店上架。

---

## 功能说明

### 棋种切换

- 顶栏：`国际象棋 | 中国象棋`
- 同级页跳转（对弈 / 学习 / 联机 / 工具）
- `localStorage.cc_variant` 记忆上次选择
- `/` 瞬时入口，不展示选型落地页

### 对弈

- 人 vs AI / 人人 /（国际象棋）AI vs AI
- 快评 / 深评 Council；着法列表与回放；悔棋 / 提示
- 浏览器会话隔离：请求携带 `X-Session-Id`

### 学习

- 名局 / 残局 / 战术库（跟谱或自由推演）
- 残局闯关（本地通关解锁）

### 联机

- 房间码 / 分享链接，WebSocket 同步（同网演示级）
- 进对弈页前断开大厅 WS，避免误触发 peer-left

### 工具

- 国际象棋：拍照识谱 → FEN、对局历史、PGN、路演 Demo、调用日志（管理口令）
- 中国象棋：FEN 导入 / 导出

### 安全与护栏

- 历史读写按 `X-Owner-Id` 隔离；越权 404，无身份 401
- API 限流对 `/api`、`/api/chess`、`/api/xiangqi` 共用规则并分桶
- 基础安全响应头（`nosniff` / `SAMEORIGIN` / CSP）
- 可选 `OWNER_SECRET`：HMAC 签名访客令牌（`GET /api/visitor`）
- OpenAPI 快照：`python scripts/export_openapi.py` → [`docs/openapi.json`](docs/openapi.json)

---

## 快速开始

### 环境

- Python ≥ 3.10
- [Stockfish](https://stockfishchess.org/)（推荐 `brew install stockfish` / `apt install stockfish`；**仅国际象棋需要**）
- 可选：OpenAI 兼容 `LLM_API_KEY`（大赛可用 `glm-5.1`，日常可用千问等）

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

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000) → 自动进入上次棋种；也可直达：

| 棋种 | 地址 |
|------|------|
| 国际象棋 | [http://127.0.0.1:8000/chess/](http://127.0.0.1:8000/chess/) |
| 中国象棋 | [http://127.0.0.1:8000/xiangqi/](http://127.0.0.1:8000/xiangqi/) |

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
pytest -q tests/test_api_smoke.py tests/xiangqi/
./scripts/smoke.sh                 # 需服务已启动
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

`OWNER_SECRET` 可选：设置后历史读写要求 `/api/visitor` 签发的签名 `X-Owner-Id`。

---

## 仓库结构

```
src/
├── main.py                 # FastAPI 入口（双棋种挂载）
├── orchestrator.py         # 国际象棋对局 + Council 编排
├── sessions.py · rooms.py  # 会话池 / 联机房间（国际象棋）
├── guardrails.py           # 限流 / admin / owner（双前缀归一）
├── api/                    # 国际象棋 HTTP / WebSocket
├── board/ · agents/ · council/ · library/
└── xiangqi/                # 中国象棋规则 / AI / Council / 房间 / API
frontend/
├── index.html              # 瞬时跳转入口
├── shared/                 # 棋种切换脚本与样式
├── chess/                  # 国际象棋 UI + PWA
└── xiangqi/                # 中国象棋 UI（朱砂中国风配色）
tests/
├── test_api_smoke.py       # 国际象棋 + 双前缀冒烟
└── xiangqi/                # 规则 / 谜题 / 联机回归
scripts/                    # run_dev · smoke · export_openapi
docs/                       # COMPETE.md · openapi.json · pitch/
```

---

## 主要 API

客户端请求普通对弈接口时应带：

- `X-Session-Id`：盘面隔离
- `X-Owner-Id`：历史归属（国际象棋历史；≥8 字符的本机身份）

| 前缀 | 说明 |
|------|------|
| `/api/chess/*` | 国际象棋正式前缀 |
| `/api/*` | 兼容旧客户端（等同 chess） |
| `/api/xiangqi/*` | 中国象棋 |

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` · `/api/chess/health` | 健康检查（含 `variants: ["chess","xiangqi"]`） |
| `GET` | `/api/xiangqi/health` | 象棋健康检查 |
| `POST` | `/api/game/new` · `/api/xiangqi/game/new` | 新对局 |
| `POST` | `.../game/move` | 走子 |
| `POST` | `.../game/ai-step` | AI 一步 |
| `POST` | `/api/game/analyze-position` | 只分析不走子（国际象棋） |
| `POST` | `/api/xiangqi/...` 分析相关 | 象棋启发式分析 |
| `WS` | `.../rooms/{id}/ws?token=` | 实时同步 |

走子 / 分析响应中的 `analysis.council`（国际象棋）含 `agents`、`disagreement`、`debate`、`verdict`。

完整契约见 [`docs/openapi.json`](docs/openapi.json)。

---

## 已知边界

1. `X-Owner-Id` / `X-Session-Id` 是**浏览器本地身份**，不是登录账号；可被伪造，仅适合演示与小范围试用。
2. 会话与联机房间主要在**单进程内存**；多 worker / 重启会丢状态。
3. Stockfish 实例共享并串行加锁，高并发会排队。
4. 两套规则引擎与 UI **未统一**；合并的是产品壳与进程。
5. 限流目前仍可被伪造 `X-Session-Id` 绕过到一定程度；公网前应改为 IP 级硬限流。
6. 公网部署请设置 `ADMIN_TOKEN`、`PUBLIC_DEMO=1`，并收紧 `CORS_ORIGINS`。

---

## 路线图

**已完成**

- Council 流水线 + 手机优先 Web / PWA
- 学习 / 闯关 / 联机 / 识谱
- 会话隔离、历史归属、自动存档、日志 ContextVar
- **双棋种同进程：顶栏切换 + 排版对齐（方案 A）**

**下一步**

1. 公网 HTTPS、IP 级硬限流与更严 CSP  
2. 象棋侧更强引擎（如 [Pikafish](https://github.com/official-pikafish/Pikafish)）可选接入  
3. 真账号体系（在签名访客之上）  
4. 可选原生壳：换壳不换脑，仍走本仓库 API  

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
