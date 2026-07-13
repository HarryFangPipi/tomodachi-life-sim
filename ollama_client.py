import httpx
import re
from config import load_config

OLLAMA_URL = load_config().ollama_url


def _clean(text: str) -> str:
    """只去掉 <think> 块，其余原样返回。"""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


async def list_models() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


async def generate(prompt: str, model: str = "qwen3", max_tokens: int = 80) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.75,
            "top_p": 0.9,
            "stop": ["\n\n"],
        },
    }
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            return _clean(r.json().get("response", ""))
    except Exception:
        return ""


async def chat(messages: list[dict], model: str = "qwen3", max_tokens: int = 120) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.75,
            "top_p": 0.9,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            return _clean(r.json().get("message", {}).get("content", ""))
    except Exception:
        return ""
