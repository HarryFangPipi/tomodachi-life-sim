import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ROOT_DIR / "config.json"


DEFAULT_CONFIG: dict[str, Any] = {
    "host": "0.0.0.0",
    "port": 8000,
    "ollama_url": "http://localhost:11434",
    "preferred_models": ["qwen3.6", "gpt-oss:20b", "deepseek-r1:8b", "qwen3", "llama3.2:3b", "llama3.2", "llama3:8b", "llama3", "mistral", "phi3", "gemma2:2b"],
    "tick_seconds": 0.8,
    "game_hours_per_tick": 0.05,
    "max_agents": 24,
    "save_path": "data/savegame.json",
    "autoload_save": True,
    "autosave_seconds": 20,
}


@dataclass(frozen=True)
class AppConfig:
    host: str
    port: int
    ollama_url: str
    preferred_models: list[str]
    tick_seconds: float
    game_hours_per_tick: float
    max_agents: int
    save_path: Path
    autoload_save: bool
    autosave_seconds: float


def load_config() -> AppConfig:
    raw = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        raw.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))

    save_path = Path(raw["save_path"])
    if not save_path.is_absolute():
        save_path = ROOT_DIR / save_path

    return AppConfig(
        host=str(raw["host"]),
        port=int(raw["port"]),
        ollama_url=str(raw["ollama_url"]).rstrip("/"),
        preferred_models=[str(m) for m in raw["preferred_models"]],
        tick_seconds=float(raw["tick_seconds"]),
        game_hours_per_tick=float(raw["game_hours_per_tick"]),
        max_agents=int(raw["max_agents"]),
        save_path=save_path,
        autoload_save=bool(raw["autoload_save"]),
        autosave_seconds=float(raw["autosave_seconds"]),
    )

