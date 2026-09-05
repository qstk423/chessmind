# ChessCouncil

**多智能体辩论式国际象棋分析与对战系统。**

ChessCouncil 提供国际象棋对局、局面分析与联机演示能力：服务端负责规则、引擎、LLM 理事会（Council）与学习库，Web 客户端负责棋盘交互与结果呈现。三个异质 Agent（战术 / 战略 / 风险）并行给意见；分歧够大时再辩论、质询、仲裁；[Stockfish](https://stockfishchess.org/) 提供客观计算；教练按水平把结论讲成人话。

- 仓库：[github.com/qstk423/chessmind](https://github.com/qstk423/chessmind)（历史仓库名仍为 `chessmind`；**产品名以 ChessCouncil 为准**）
- 姐妹项目：[Xiangqi Council](https://github.com/qstk423/Xiang-qi-gaming)（中国象棋侧，信息架构对齐，可合并为双棋种）
- 大赛说明：[docs/COMPETE.md](docs/COMPETE.md)（天津移动 Token 算力大赛 · 赛道二等场景）

---

## 概述

国际象棋「能算」不难，难的是 **算得清楚、说得明白、还能吵出分歧**。ChessCouncil 把系统拆成两层：

| 层级 | 职责 | 当前实现 |
|------|------|----------|
| Brain（服务端） | 规则、Stockfish、LLM Council、对局 / 房间 / 学习库、持久化 | Python · FastAPI |
| Client（客户端） | 棋盘、分析呈现、导航与触控 | 手机优先 Web / PWA |

**它包含：**

- 人机 / 人人 / AI 互搏对弈，以及可演示的 Council 分析流水线
- 名局 / 残局 / 战术学习与残局闯关
- WebSocket 联机房间、拍照识谱、对局历史与赛后复盘相关能力
- Docker 部署（镜像可含 Stockfish）、冒烟测试与基础试用护栏

**它目前不包含：**

- 完整的公开运营账号体系 / 多租户
- 应用商店级原生客户端（安卓 / iOS 仅为路线图上的「换壳」选项）
- 把 Stockfish 或 LLM 打进浏览器端（引擎与模型留在服务端）

原则是：先把 **API 契约与 Brain** 当作产品真相来源，客户端可替换。

面向大赛时可切官方 `glm-5.1`；日常开发可用任意 OpenAI 兼容接口（如千问）。无 Key、无引擎时 UI 仍可打开，分析与选着会软降级。

---

## 设计原则

1. **API 优先** — 能力经 HTTP / WebSocket 暴露；网页只是第一个客户端。
2. **引擎与模型不进端** — Stockfish / LLM 留在服务端，Web → 原生 App 时不必重做 Brain。
3. **手机优先** — 对弈 / 学习 / 联机 / 工具分页面 + 底栏；宽屏为增强而非前提。
4. **可降级** — 缺少 LLM Key 或 Stockfish 时，界面与基础对弈仍可用。
5. **许可证清晰** — 本仓库 MIT；Stockfish 等第三方组件须遵守其自身条款。

分析流水线：

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

## 功能说明

### 对弈

- 人 vs AI / 人人 / AI vs AI（LLM 选着与引擎配合，非法着法回退）
- 快评 / 深评 Council；着法列表、回放、速度控制；悔棋 / 提示
- 终局杀型结算动画；赛后复盘与准确度相关能力

### 学习

- 名局 / 残局 / 战术库（跟谱演示或 AI 代下）
- 残局闯关（通关解锁）

### 联机

- 房间码 / 分享链接，WebSocket 实时同步（适合同网演示）

### 工具

- 拍照识谱 → FEN（可纠错再分析）
- 对局历史（SQLite）、PGN、路演 Demo、调用日志（管理口令）

### 交付形态

- 手机优先多页 UI + PWA（可「添加到主屏幕」）
- Docker 一键部署
- 冒烟测试与基础限流 / 超时护栏（邀请试用向）

---

## 发行内容

本仓库主要包含：

| 路径 | 说明 |
|------|------|
| [`README.md`](README.md) | 本文件 |
| [`LICENSE`](LICENSE) | MIT 许可证正文 |
| [`requirements.txt`](requirements.txt) | Python 依赖 |
| [`.env.example`](.env.example) | 环境变量模板 |
| [`src/`](src/) | 服务端源码 |
| [`frontend/`](frontend/) | Web / PWA 客户端 |
| [`docs/`](docs/) | 大赛与路演文档 |
| [`scripts/`](scripts/) | 开发启动与冒烟脚本 |
| [`tests/`](tests/) | API 冒烟测试 |
| [`Dockerfile`](Dockerfile) · [`docker-compose.yml`](docker-compose.yml) | 容器部署 |

源码结构：

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
frontend/
├── index.html           # 对弈
├── learn.html           # 学习
├── online.html          # 联机
├── tools.html           # 工具
docs/COMPETE.md          # 大赛路演与证据包
```

---

## 编译与运行

### 环境要求

- Python ≥ 3.10
- [Stockfish](https://stockfishchess.org/)（推荐：`brew install stockfish` / `apt install stockfish`）
- OpenAI 兼容的 `LLM_API_KEY`（可空，则纯引擎或进一步降级）

### 本地启动

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

浏览器打开：[http://127.0.0.1:8000](http://127.0.0.1:8000)

### 手机演示（推荐路径）

```bash
HOST=0.0.0.0 ./scripts/run_dev.sh
```

手机与电脑同一局域网，浏览器打开 `http://<电脑局域网IP>:8000`，可「添加到主屏幕」。联机：一机创建房间 → 复制链接给另一台设备。

### Docker

```bash
cp .env.example .env   # 填 Key
docker compose up --build
```

默认：[http://127.0.0.1:8000](http://127.0.0.1:8000)

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

公网小范围试用前建议：`PUBLIC_DEMO=1`、`ADMIN_TOKEN=...`、收紧 `CORS_ORIGINS`，并运行：

```bash
./scripts/smoke.sh
# 或: pytest -q tests/test_api_smoke.py
```

### 已知边界

- 默认进程内共享「单盘分析对局」；联机房间为独立状态。
- 完整账号 / 多租户不在当前范围。
- 无 Stockfish 或无 LLM 时，部分分析与选着质量会下降，但客户端仍应可打开。

---

## 主要 API

客户端应只依赖下列契约：

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查（引擎 / LLM 状态等） |
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
| `GET` | `/api/logs/recent` | LLM 调用日志（管理口令） |

走子 / 分析响应中的 `analysis.council` 含 `agents`、`disagreement`、`debate`、`verdict`。完整路演与提交清单见 [`docs/COMPETE.md`](docs/COMPETE.md)。

---

## 与相关项目的关系

| 项目 | 关系 |
|------|------|
| [Xiangqi Council](https://github.com/qstk423/Xiang-qi-gaming) | 中国象棋姐妹项目；对弈 / 学习 / 联机 / 工具与 Council 交互同构，目标合并为 `game_type=chess\|xiangqi`。 |
| [Stockfish](https://github.com/official-stockfish/Stockfish) | 国际象棋 UCI 引擎；本项目作为 GUI / 业务壳调用它，引擎本身不含产品级界面。 |
| [Pikafish](https://github.com/official-pikafish/Pikafish) | 象棋侧目标引擎参考；由 Xiangqi Council 接入，不在本仓库发行物中。 |

---

## 路线图

**已完成**

- Council 流水线 + 可演示的手机 Web / PWA 客户端
- 学习 / 闯关 / 联机 / 识谱
- Docker 与基础上线护栏

**下一步**

1. **冻结 API 契约** — 沉淀为稳定文档或 OpenAPI，作为第二客户端唯一对接面  
2. **公网部署** — 固定 HTTPS 域名后，手机才真正「装完就能玩」  
3. **与 Xiangqi Council 合并** — 统一壳 + `game_type`  
4. **原生客户端（可选）** — 安卓 / iOS 换壳不换脑，Brain 仍走本仓库 API  
5. **多租户 / 账号** — 仅在需要公开运营时再上

原生客户端是 **换壳，不换脑**：先把服务端当产品真相来源，再谈商店与安装包。

---

## 使用条款

本项目以 [MIT License](LICENSE) 发布。你可以自由使用、修改、分发本仓库中的原创代码，惟须保留版权与许可声明。

发行物中若包含 Stockfish 等第三方引擎或模型服务，须同时满足对方许可证与服务条款。本仓库默认以 MIT 覆盖自身源码；第三方二进制 / 权重 / 云 API 不因本许可证而改变其原有约束。

---

## 致谢

- [Stockfish](https://stockfishchess.org/) — 开源国际象棋引擎  
- [python-chess](https://github.com/niklasf/python-chess) — 棋规与局面处理  
- [Xiangqi Council](https://github.com/qstk423/Xiang-qi-gaming) — 双棋种产品同构实践  

---

## 许可证

[MIT](LICENSE)
