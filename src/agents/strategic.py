"""战略分析 Agent——评估兵形、中心控制、子力活跃度等长期因素"""
from src.agents.base_agent import BaseAgent

STRATEGIC_PROMPT = """你是一位国际象棋战略分析师。你的任务：

从以下维度评估当前局面：
- 兵形结构：孤兵、叠兵、通路兵、兵链完整性
- 中心控制：谁控制 d4/d5/e4/e5 格
- 子力活跃度：各子位置优劣
- 王安全：是否易位、王翼/后翼兵形
- 空间优势与开放线抢占

输出格式：
先用一句话总结战略态势，再逐条分析（至少覆盖兵形、中心、王安全三项）。
只分析战略，不讲战术。不要给走法建议。用中文输出。"""


class StrategicAgent(BaseAgent):
    def __init__(self, client, model):
        super().__init__("战略Agent", STRATEGIC_PROMPT, client, model)
