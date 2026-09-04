"""汇总 Agent——融合三个 Agent 的分析 + Stockfish 评分"""
from src.agents.base_agent import BaseAgent

SUMMARIZER_PROMPT = """你是 ChessMind 的汇总分析师。你会收到三类分析和一个引擎评估：

1. 战术分析（Tactical）
2. 战略分析（Strategic）
3. 开局/模式分析（Pattern）
4. Stockfish 引擎评分、结构化局面信息和走子分类

其中结构化局面信息与引擎评分为程序计算的可信事实，是最终结论的主要依据。

你的任务：
- 把三份分析融合成一段连贯、统一的综述
- 如果三份分析与引擎事实有矛盾，以引擎事实为准并指出矛盾
- 结合 Stockfish 评分，对当前走子的质量给出结论
- 包含胜率信息

输出格式（三段）：
【局面综述】一句话概括当前局面
【走子评价】结合 Stockfish 分类（妙手/好棋/正常/缓着/漏着/大漏）评价最近一步
【综合建议】未来可以考虑的方向（不超过两条）

语言要求：专业但通俗，像人类棋评，不要罗列数据。用中文输出。"""


class SummarizerAgent(BaseAgent):
    def __init__(self, client, model):
        super().__init__("汇总Agent", SUMMARIZER_PROMPT, client, model)

    async def summarize(
        self,
        tactical: str,
        strategic: str,
        pattern: str,
        stockfish_info: dict,
        move_class: str,
        fen: str,
        grounding: str = "",
    ) -> str:
        """汇总多 Agent 分析 + Stockfish 评分 + 结构化局面信息"""
        mate_text = ""
        if stockfish_info.get("is_mate"):
            mate_text = f"\n将杀：{stockfish_info.get('mate_in')} 步内"

        context = f"""=== 结构化局面信息（可信事实） ===
{grounding or "（无）"}

=== 战术分析 ===
{tactical}

=== 战略分析 ===
{strategic}

=== 开局分析 ===
{pattern}

=== Stockfish 引擎 ===
评分：{stockfish_info.get('score_cp', 'N/A')} cp{mate_text}
白方胜率：{stockfish_info.get('win_prob_white', 'N/A')}
走子分类：{move_class}

当前 FEN：{fen}"""

        return await self.analyze(fen="", move_history=[], extra_context=context)
