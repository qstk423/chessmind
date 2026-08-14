"""Agent 基类——封装 LLM 调用"""
from openai import AsyncOpenAI


class BaseAgent:
    """所有分析 Agent 的基类"""

    def __init__(self, name: str, role_prompt: str, client: AsyncOpenAI, model: str):
        self.name = name
        self.role_prompt = role_prompt
        self.client = client
        self.model = model

    async def analyze(self, fen: str, move_history: list[str], extra_context: str = "") -> str:
        """
        分析一个局面，返回自然语言分析文本。
        """
        history_text = " ".join(move_history) if move_history else "开局"
        user_prompt = self._build_prompt(fen, history_text, extra_context)

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

    def _build_prompt(self, fen: str, history_text: str, extra_context: str) -> str:
        parts = [
            f"当前棋盘 FEN：{fen}",
            f"最近走法历史：{history_text}",
        ]
        if extra_context:
            parts.append(f"额外信息：{extra_context}")
        parts.append("请给出你的分析。")
        return "\n\n".join(parts)
