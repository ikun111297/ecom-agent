import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# 模型、地址、采样温度都走环境变量，想换模型不用改代码
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# 业务回答的温度。客服属于事实性回答，压低一些让同一问题两次回答保持一致；
# 检索改写和评测裁判另外显式传 temperature=0。
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))

# 延迟建客户端：这样即使 .env 里没配 key，也能 import 本模块拿到清晰的报错，
# 而不是在 import 阶段就抛一个看不懂的异常
_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY，请在项目根目录的 .env 里配置")
        _client = OpenAI(api_key=api_key, base_url=BASE_URL)
    return _client


def chat(messages, tools=None, temperature=None):
    """发送对话给模型。传了 tools 就返回原始响应（可能含工具调用请求）"""
    kwargs = {
        "model": MODEL,
        "messages": messages,
        "temperature": TEMPERATURE if temperature is None else temperature,
    }
    if tools:
        kwargs["tools"] = tools
    return _get_client().chat.completions.create(**kwargs)
