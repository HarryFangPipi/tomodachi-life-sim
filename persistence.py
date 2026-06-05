import json
from pathlib import Path
from typing import Any

from agents import Agent
from world import LOCATIONS


SAVE_VERSION = 1


def _agent_config_from_save(data: dict[str, Any]) -> dict[str, Any]:
    home = data.get("home", "apartment")
    if home not in LOCATIONS:
        home = "apartment" if "apartment" in LOCATIONS else "town_square"
    return {
        "id": data["id"],
        "name": data.get("name", data["id"]),
        "personality": data.get("personality", "友善的小镇居民。"),
        "occupation": data.get("occupation", "居民"),
        "home": home,
        "color": data.get("color", "#FF6B6B"),
        "skin": data.get("skin", "#FFCC80"),
        "hair": data.get("hair", "#8B4513"),
    }


def build_save_data(engine) -> dict[str, Any]:
    return {
        "version": SAVE_VERSION,
        "tick_count": engine.tick_count,
        "game_hour": engine.game_hour,
        "model": engine.model,
        "events": engine.events[-200:],
        "agents": [agent.to_save_dict() for agent in engine.agents],
    }


def save_game(engine, path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = build_save_data(engine)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return data


def load_game(engine, path: Path) -> bool:
    if not path.exists():
        return False

    data = json.loads(path.read_text(encoding="utf-8"))
    engine.tick_count = int(data.get("tick_count", 0))
    engine.game_hour = float(data.get("game_hour", 8.0)) % 24
    engine.events = list(data.get("events", []))[-200:]

    agents = []
    existing_by_id = {agent.id: agent for agent in engine.agents}
    for saved_agent in data.get("agents", []):
        agent_id = saved_agent.get("id")
        if not agent_id:
            continue
        agent = existing_by_id.get(agent_id)
        if agent is None:
            agent = Agent(_agent_config_from_save(saved_agent), engine.model)
        agent.apply_save_dict(saved_agent)
        agents.append(agent)

    if agents:
        engine.agents = agents
    return True


def reset_save(path: Path) -> bool:
    if path.exists():
        path.unlink()
        return True
    return False
