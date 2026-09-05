# ChessCouncil · 天津移动 Token 算力大赛冲奖手册

## 一句话定位

**ChessCouncil**：多模态棋局感知 + 异质多智能体分析与动态辩论 + Stockfish 引擎仲裁的实时国际象棋系统（赛道二 · AI 游戏 / 算法对抗）。

## 路演 5 分钟结构（决赛）

| 时间 | 内容 |
|---|---|
| 0:00–0:30 | 痛点：纯引擎不会讲；纯 LLM 会幻觉；多 AI 各说各话无仲裁 |
| 0:30–2:00 | **一键 Demo「希腊赠礼」**：争议度飙升 → 自动辩论 → 引擎仲裁 |
| 2:00–3:00 | AI vs AI 算法对抗 + 侧栏 Council 解说 |
| 3:00–3:40 | 多模态：截图识谱 → 加载 FEN → 再分析（若现场网络允许） |
| 3:40–4:20 | 赛后复盘报告（争议步 / 辩论次数 / PGN） |
| 4:20–5:00 | 创新点收束 + 调用日志证明 glm-5.1（或当前模型） |

## 创新点（评委三句）

1. **异质 Agent**：战术 / 战略 / 风险职责互斥，不是同一 prompt 复制粘贴。  
2. **分歧驱动辩论**：可解释加权争议度，高争议才辩论，省 Token 也更像「理事会」。  
3. **引擎接地 + 仲裁**：事实来自 python-chess / Stockfish，LLM 不能瞎编局面。

## 提交清单

- [x] 可运行代码 + README  
- [x] `.env.example`（无真实 Key）  
- [x] 说明文档（本文件可作底稿）  
- [ ] 录屏：Demo 辩论 + AI vs AI +（可选）识谱  
- [x] `docs/samples/llm_calls.sample.jsonl` 样例格式；正式提交用录屏同步的 `logs/llm_calls.jsonl`  
- [ ] 运行态模型：`glm-5.1`（大赛 Token 到位后切换）

## 现场操作顺序

1. `python -m src.main`（或 `docker compose up`）  
2. 打开页面 → 顶部路演栏点 **「希腊赠礼 · 辩论」**  
3. 等进度条结束 → 侧栏自动切到 **辩论** Tab  
4. 点 **复盘**（局面分析已写入复盘缓存）  
5. 再点 **「快速 AI 对战」**（关 Council，快进算法对抗）  
6. 点 **调用证明** 或另屏 `tail -f logs/llm_calls.jsonl`

## Token 切换（大赛发下来后）

```ini
LLM_API_KEY=<天津移动>
LLM_BASE_URL=<天津移动>
LLM_MODEL=glm-5.1
VISION_MODEL=<若官方提供视觉模型则填，否则演示期可继续用百炼 qwen-vl-plus>
```

## 风险预案

| 风险 | 预案 |
|---|---|
| API 超时 | 取消勾选 Council，纯引擎对战仍可演示；预录视频兜底 |
| 开局无辩论 | 必须用 Demo 按钮，不要从初始局面硬讲辩论 |
| 识谱失败 | 跳过 multimodal，强调 FEN 结构化 + Demo |
| 超时 | 缩短 Agent max_tokens；Demo 只跑一局 |
