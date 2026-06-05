import asyncio
import importlib
import json
import os
import re
import sys
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from pathlib import Path
from game import GameEngine
from config import load_config

CONFIG = load_config()

app = FastAPI(title="Tomodachi World")
app.mount("/static", StaticFiles(directory="static"), name="static")

game = GameEngine()
connections = set()  # set[WebSocket]
autosave_task = None

@app.get("/")
async def root():
    return HTMLResponse(Path("static/index.html").read_text(encoding="utf-8"))

@app.post("/api/reload-world")
async def reload_world():
    """重载 world.py 并重新初始化游戏地图，无需重启服务器"""
    import world
    import agents as agents_module
    importlib.reload(world)
    importlib.reload(agents_module)
    import game as game_module
    importlib.reload(game_module)
    global game
    if game._conv_task:
        game._conv_task.cancel()
    game = game_module.GameEngine()
    await game.initialize()
    await broadcast({"type": "state", "data": game.get_state()})
    return JSONResponse({"status": "ok", "map_cols": world.MAP_COLS, "map_rows": world.MAP_ROWS})

@app.get("/api/state")
async def get_state_api():
    return JSONResponse(game.get_state())

class NewAgentRequest(BaseModel):
    name: str
    personality: str
    occupation: str = "居民"
    color: str = "#FF6B6B"
    skin: str = "#FFCC80"
    hair: str = "#8B4513"
    home: str = "apartment"

@app.post("/api/add-agent")
async def add_agent(req: NewAgentRequest):
    from agents import Agent
    from world import LOCATIONS
    name = req.name.strip()
    if not name:
        return JSONResponse({"status": "bad_request", "error": "name required"}, status_code=400)
    if len(game.agents) >= CONFIG.max_agents:
        return JSONResponse({"status": "max_agents_reached", "max_agents": CONFIG.max_agents}, status_code=400)
    base_id = re.sub(r'[^a-z0-9]', '_', name.lower())[:16].strip('_') or "agent"
    existing_ids = {a.id for a in game.agents}
    agent_id, n = base_id, 2
    while agent_id in existing_ids:
        agent_id = f"{base_id}_{n}"; n += 1
    home = req.home if req.home in LOCATIONS else ("apartment" if "apartment" in LOCATIONS else "town_square")
    cfg = {"id": agent_id, "name": name, "personality": req.personality.strip() or f"{name}是友善的小镇居民。",
           "occupation": req.occupation, "home": home,
           "color": req.color, "skin": req.skin, "hair": req.hair}
    new_agent = Agent(cfg, game.model)
    game.agents.append(new_agent)
    game.add_event(f"新居民 {name} 加入了小镇！", "info")
    game.save(silent=True)
    # Generate an outlined sprite sheet from the resident's colors so they
    # render like the built-in characters instead of the fallback block.
    try:
        import generate_sprites
        generate_sprites.save_sprite_for(agent_id, req.hair, req.color, req.skin)
    except Exception:
        pass  # sprite is optional — drawCharacter falls back to a block
    await broadcast({"type": "state", "data": game.get_state()})
    return JSONResponse({"status": "ok", "agent_id": agent_id})

@app.delete("/api/remove-agent/{agent_id}")
async def remove_agent(agent_id: str):
    original = len(game.agents)
    removed = next((a for a in game.agents if a.id == agent_id), None)
    game.agents = [a for a in game.agents if a.id != agent_id]
    if len(game.agents) == original:
        return JSONResponse({"status": "not_found"}, status_code=404)
    if removed:
        for agent in game.agents:
            agent.relationships.pop(agent_id, None)
        game.add_event(f"{removed.name} 离开了小镇", "info")
        game.save(silent=True)
    await broadcast({"type": "state", "data": game.get_state()})
    return JSONResponse({"status": "ok"})

@app.post("/api/save")
async def save_game_api():
    data = game.save()
    await broadcast({"type": "state", "data": game.get_state()})
    return JSONResponse({"status": "ok", "agents": len(data.get("agents", [])), "path": str(CONFIG.save_path)})

@app.post("/api/load")
async def load_game_api():
    loaded = game.load()
    if loaded:
        await broadcast({"type": "state", "data": game.get_state()})
        return JSONResponse({"status": "ok", "agents": len(game.agents)})
    return JSONResponse({"status": "not_found"}, status_code=404)

@app.post("/api/reset-save")
async def reset_save_api():
    removed = game.reset_save()
    await reload_world()
    return JSONResponse({"status": "ok", "removed": removed})

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    connections.add(websocket)
    try:
        await websocket.send_json({"type": "state", "data": game.get_state()})
        while True:
            raw = await websocket.receive_text()
            await handle_ws_message(websocket, raw)
    except WebSocketDisconnect:
        connections.discard(websocket)
    except Exception:
        connections.discard(websocket)

async def handle_ws_message(websocket: WebSocket, raw: str):
    """Parse and act on a client → server WS command."""
    try:
        msg = json.loads(raw)
    except Exception:
        return
    mtype = msg.get("type")
    if mtype == "toggle_pause":
        game.paused = not game.paused
        game.add_event("⏸ 时间已暂停" if game.paused else "▶ 时间继续", "info")
        await broadcast({"type": "update", "data": game.get_state()})
    elif mtype == "set_pause":
        game.paused = bool(msg.get("paused"))
        await broadcast({"type": "update", "data": game.get_state()})
    elif mtype == "user_chat":
        result = await game.user_chat(
            msg.get("agent_id", ""), msg.get("text", ""), msg.get("history") or []
        )
        try:
            await websocket.send_json({"type": "chat_reply", "data": result})
        except Exception:
            pass
        # broadcast so the speech bubble + event log update for all viewers
        await broadcast({"type": "update", "data": game.get_state()})

async def broadcast(data: dict):
    dead = set()
    for ws in list(connections):
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    connections.difference_update(dead)

async def game_loop():
    while True:
        if not game.paused:
            await game.tick()
        state = game.get_state()
        await broadcast({"type": "update", "data": state})
        await asyncio.sleep(CONFIG.tick_seconds)

async def autosave_loop():
    while True:
        await asyncio.sleep(CONFIG.autosave_seconds)
        try:
            game.save(silent=True)
        except Exception:
            pass

@app.on_event("startup")
async def startup():
    global autosave_task
    await game.initialize()
    asyncio.create_task(game_loop())
    if CONFIG.autosave_seconds > 0:
        autosave_task = asyncio.create_task(autosave_loop())

if __name__ == "__main__":
    uvicorn.run("server:app", host=CONFIG.host, port=CONFIG.port, reload=False)
