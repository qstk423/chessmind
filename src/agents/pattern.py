"""模式匹配 Agent——开局识别与数据库查询"""
from src.agents.base_agent import BaseAgent

PATTERN_PROMPT = """你是一位国际象棋开局专家。你的任务：

根据当前局面的 FEN 和走法历史，识别：
1. 这属于什么开局体系（如西西里防御、后翼弃兵、西班牙开局等）
2. 双方是否还在开局理论范围内，还是已脱离谱着
3. 该开局的典型计划是什么

输出格式：
先写出开局名称，再简要说明典型计划和当前执行情况。
只做开局/模式分析，不讲战术和战略细节。用中文输出。"""


class PatternAgent(BaseAgent):
    def __init__(self, client, model):
        super().__init__("模式Agent", PATTERN_PROMPT, client, model)
