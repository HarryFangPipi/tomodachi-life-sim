import httpx
import json
import asyncio
import re
from config import load_config

def _strip_think(text: str) -> str:
    """Remove qwen3 <think>...</think> blocks from response."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

OLLAMA_URL = load_config().ollama_url

async def list_models() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
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
            "temperature": 0.8,
            "top_p": 0.9,
            "stop": ["\n\n", "Human:", "User:"]
        }
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            data = r.json()
            return _strip_think(data.get("response", ""))
    except Exception:
        return ""

async def chat(messages: list[dict], model: str = "qwen3", max_tokens: int = 80) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.85,
            "top_p": 0.9,
        }
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            data = r.json()
            return _strip_think(data.get("message", {}).get("content", ""))
    except Exception:
        return ""
