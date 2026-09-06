"""全局配置，统一从环境变量读取"""
import os
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)

# ── LLM（天津移动 Token 算力大赛默认 glm-5.1；开发期可改其它 OpenAI 兼容接口）──
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "glm-5.1")
LLM_ENABLED = bool(LLM_API_KEY)

STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "stockfish")
AI_ENGINE_DEPTH = int(os.getenv("AI_ENGINE_DEPTH", "12"))
LLM_LOG_PATH = Path(os.getenv("LLM_LOG_PATH", str(_PROJECT_ROOT / "logs" / "llm_calls.jsonl")))
AI_STEP_DELAY_MS = int(os.getenv("AI_STEP_DELAY_MS", "1200"))
COACH_LEVEL = os.getenv("COACH_LEVEL", "intermediate").strip().lower() or "intermediate"
DEBATE_THRESHOLD = float(os.getenv("DEBATE_THRESHOLD", "0.5"))
# 多模态识谱模型（阿里云百炼示例：qwen-vl-plus / qwen3-vl-plus）
VISION_MODEL = os.getenv("VISION_MODEL", "qwen-vl-plus").strip() or "qwen-vl-plus"

# ── 上线护栏 ──
# 单次 LLM 调用超时（秒）
LLM_TIMEOUT_SEC = float(os.getenv("LLM_TIMEOUT_SEC", "45"))
# 同时进行的 Council 分析上限（防打爆 Key）
LLM_MAX_CONCURRENT = max(1, int(os.getenv("LLM_MAX_CONCURRENT", "1")))
# 滑动窗口限流：每 IP 每窗口最多多少次 API（贵路径会更严）
RATE_LIMIT_WINDOW_SEC = int(os.getenv("RATE_LIMIT_WINDOW_SEC", "60"))
RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", "90"))
# PGN 全盘分析最多复盘多少半步
PGN_MAX_PLIES = max(1, int(os.getenv("PGN_MAX_PLIES", "40")))
# 敏感接口口令（日志 / ping 模型）；公开展示务必设置
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
# 公开展示：未设 ADMIN_TOKEN 时拒绝敏感接口
PUBLIC_DEMO = os.getenv("PUBLIC_DEMO", "").strip().lower() in ("1", "true", "yes", "on")
# 可选：签名访客身份。设置后 X-Owner-Id 必须由 /api/visitor 签发
OWNER_SECRET = os.getenv("OWNER_SECRET", "").strip()
# 产品版本（OpenAPI / health 共用）
APP_VERSION = os.getenv("APP_VERSION", "0.4.1").strip() or "0.4.1"
