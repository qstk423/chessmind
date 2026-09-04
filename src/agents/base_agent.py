"""Agent 基类——封装 LLM 调用"""
from openai import AsyncOpenAI
from src.config import LLM_ENABLED


class BaseAgent:
    """所有分析 Agent 的基类"""

    def __init__(self, name: str, role_prompt: str, client: AsyncOpenAI | None, model: str):
        self.name = name
        self.role_prompt = role_prompt
        self.client = client
        self.model = model

    async def analyze(self, fen: str, move_history: list[str], extra_context: str = "") -> str:
        """
        分析一个局面，返回自然语言分析文本。
        未配置 API Key 时降级为占位说明；调用失败时返回错误提示而非崩溃，
        保证引擎评分与走子分类等核心功能不受影响。
        """
        if not LLM_ENABLED or self.client is None:
            return "（未配置 LLM_API_KEY，Agent 分析已跳过；引擎评分与走子分类不受影响。）"

        history_text = " ".join(move_history) if move_history else "开局"
        user_prompt = self._build_prompt(fen, history_text, extra_context)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.role_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.4,
                max_tokens=600,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"（{self.name}调用失败：{type(e).__name__}，请检查 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 配置。）"

    def _build_prompt(self, fen: str, history_text: str, extra_context: str) -> str:
        parts = []
        if fen:
            parts.append(f"当前棋盘 FEN：{fen}")
        parts.append(f"最近走法历史：{history_text}")
        if extra_context:
            parts.append(f"结构化局面信息（程序提取的确定性事实，必须以此为准）：\n{extra_context}")
        parts.append("请给出你的分析。")
        return "\n\n".join(parts)
