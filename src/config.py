"""全局配置，统一从环境变量读取"""
import os
from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
# 未配置 API Key 时运行纯引擎模式（走子/评分/分类正常，Agent 文本分析跳过）
LLM_ENABLED = bool(LLM_API_KEY)

STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "stockfish")
