# ChessMind ♟️

国际象棋多 Agent 实时分析系统——在自建棋盘上每走一步，战术 / 战略 / 开局三个 Agent 并行分析后汇总，Stockfish 引擎交叉验证。

## 功能特性

- **自建对弈棋盘**：点击走子（选中高亮 + 合法点位提示 + 吃子标记），支持翻转棋盘、升变
- **实时引擎评估**：每步走子前后各一次 Stockfish 深度评估，胜率条实时更新
- **走子质量分类**：按走子方视角的评分变化，将每步棋分为 妙手 / 好棋 / 正常 / 缓着 / 漏着 / 大漏
- **多 Agent 并行分析**：战术、战略、开局三个 Agent 同时分析，汇总 Agent 融合输出
- **Agent 接地（Grounding）**：由 python-chess 提取结构化局面事实（子力、悬子、兵形、王安全、中心控制、开放线）并连同引擎最佳续着（PV）注入各 Agent 提示词，杜绝 LLM 误读 FEN
- **PGN 复盘**：粘贴 PGN 棋谱逐步分析（独立于当前对局，支持 FEN 头自定义起始局面）
- **无 Key 降级**：不配置 LLM API Key 也能完整使用引擎功能（评分 / 胜率 / 分类），Agent 文本分析自动跳过

## 工作原理

```
走子请求
   │
   ├─ ① 走子前 Stockfish 评估（深度 15）
   ├─ ② 执行走子（python-chess）
   ├─ ③ 走子后 Stockfish 评估 + 走子分类（走子方视角）
   ├─ ④ 结构化局面特征提取（接地上下文）
   │
   ├─ ⑤ 并行：战术 Agent ┐
   │        战略 Agent ├── async 并发调用 LLM
   │        开局 Agent ┘
   │
   └─ ⑥ 汇总 Agent：融合三份分析 + 引擎事实 → 统一棋评
```

所有 Agent 的提示词中都注入了程序计算的确定性事实，汇总 Agent 被要求**以引擎事实为准**处理矛盾分析。

## 环境要求

- **Python ≥ 3.10**（代码使用 `X | None` 语法，3.9 无法运行）
- **Stockfish**
  - macOS：`brew install stockfish`
  - Ubuntu/Debian：`sudo apt install stockfish`
- **LLM API Key（可选）**：支持 DeepSeek / OpenAI / 任何 OpenAI 兼容接口

## 快速启动

```bash
git clone https://github.com/qstk423/chessmind.git
cd chessmind
pip install -r requirements.txt
brew install stockfish            # 或 apt install stockfish
cp .env.example .env              # 填入 LLM API Key（可留空，见下方降级说明）
python -m src.main
```

打开 http://localhost:8000

### 配置说明（.env）

```ini
LLM_API_KEY=sk-xxxx               # 留空 = 纯引擎模式
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
STOCKFISH_PATH=/opt/homebrew/bin/stockfish   # 按实际安装路径修改，留空则用 PATH 中的 stockfish
```

**纯引擎模式**：未配置 Key 时，每步走子仍返回 Stockfish 评分、胜率与走子分类，仅 Agent 文本分析显示占位说明；配置后无需改代码，重启即生效。

## API 一览

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/game/new` | POST | 开始新对局 |
| `/api/game/move` | POST | 走一步棋（UCI，升变如 `e7e8q`），返回评分 / 分类 / Agent 分析 |
| `/api/game/state` | GET | 当前棋局状态与 PGN |
| `/api/analyze/pgn` | POST | 导入 PGN 逐步复盘（不影响当前对局） |

走子响应示例（节选）：

```json
{
  "move": { "san": "e4", "uci": "e2e4", "number": 1 },
  "evaluation": {
    "before": { "score_cp": 49, "win_prob_white": 0.557 },
    "after":  { "score_cp": 46, "win_prob_white": 0.566, "pv": ["c5", "Nf3", "e6"] },
    "classification": "good"
  },
  "analysis": { "tactical": "...", "strategic": "...", "pattern": "...", "summary": "..." },
  "game_over": false,
  "fen": "..."
}
```

## 项目结构

```
src/
├── main.py                     # FastAPI 入口（lifespan 管理引擎生命周期）
├── config.py                   # 环境变量配置
├── orchestrator.py             # 多 Agent 编排总控
├── api/routes.py               # 对弈 + PGN 复盘路由
├── board/
│   ├── game_state.py           # 走子记录、PGN 导出、终局判定
│   ├── move_evaluator.py       # Stockfish 评分、走子方视角分类、胜率换算
│   └── position_features.py    # 结构化局面特征提取（Agent 接地）
└── agents/
    ├── base_agent.py           # Agent 基类（LLM 调用、无 Key 降级、容错）
    ├── tactical.py             # 战术 Agent：悬子/牵制/闪击/双捉/杀棋
    ├── strategic.py            # 战略 Agent：兵形/中心/王安全/空间
    ├── pattern.py              # 开局 Agent：体系识别/谱着判断/典型计划
    └── summarizer.py           # 汇总 Agent：融合分析 + 引擎事实
frontend/
├── index.html                  # 棋盘 + 分析面板
├── app.js                      # 点击走子、面板渲染（含 XSS 转义）
└── style.css
```

## 已知技术要点

- chessboard.js v1.0.0 的走子动画在 jQuery 3.x 下 complete 回调不触发（棋子消失 / 克隆残留），前端统一使用瞬时渲染 `position(fen, false)`
- python-chess 的 `engine.Cp` / `Mate` 对象不能直接参与算术运算，需 `.score()` 转换；`Mate.score()` 返回 `None` 需手工构造大数评分
- PV（最佳续着）转 SAN 必须在逐步推演的棋盘上顺序生成
- PGN 导出使用标准 Result 标记（`1-0` / `0-1` / `1/2-1/2`），中文结果仅用于界面展示

## License

MIT
