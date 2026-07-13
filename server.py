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
from pydantic import BaseModel, Field
from pathlib import Path
from game import GameEngine
from config import load_config

CONFIG = load_config()
BUILD_HOUSE_COST = 450
REMOVE_HOUSE_REFUND = 120

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
    background: str = ""
    goals: list[str] = Field(default_factory=list)
    speaking_rules: list[str] = Field(default_factory=list)
    occupation: str = "居民"
    color: str = "#FF6B6B"
    skin: str = "#FFCC80"
    hair: str = "#8B4513"
    home: str = "apartment"

class BuildHouseRequest(BaseModel):
    block_row: int
    block_col: int
    style: str = "cabin"
    occupant_agent_id: str = ""

class AssignResidentRequest(BaseModel):
    house_key: str
    occupant_agent_id: str = ""  # empty string = vacate

class RemoveHouseRequest(BaseModel):
    house_key: str

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
           "background": req.background.strip(),
           "goals": req.goals,
           "speaking_rules": req.speaking_rules,
           "occupation": req.occupation, "home": home,
           "color": req.color, "skin": req.skin, "hair": req.hair}
    new_agent = Agent(cfg, game.model, npc_model=game.npc_model)
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

@app.post("/api/map/build-house")
async def build_house_api(req: BuildHouseRequest):
    """Visual map editor: build a prefab house on a vacant lot or on the
    ghost ring beyond the current town bounds (auto-expanding the map),
    optionally moving an existing resident in right away."""
    import world as world_module
    if req.style not in world_module.HOUSE_STYLES:
        return JSONResponse({"status": "bad_request", "error": "invalid style"}, status_code=400)
    if game.town_funds < BUILD_HOUSE_COST:
        return JSONResponse({
            "status": "insufficient_funds",
            "error": f"小镇资金不足，需要 ${BUILD_HOUSE_COST}",
            "town_funds": game.town_funds,
            "cost": BUILD_HOUSE_COST,
        }, status_code=400)

    occupant = None
    if req.occupant_agent_id:
        occupant = next((a for a in game.agents if a.id == req.occupant_agent_id), None)
        if occupant is None:
            return JSONResponse({"status": "not_found", "error": "agent not found"}, status_code=404)

    label = f"{occupant.name}家" if occupant else "空房"
    try:
        key = world_module.build_house(req.block_row, req.block_col, req.style, label)
    except ValueError as e:
        return JSONResponse({"status": "bad_request", "error": str(e)}, status_code=400)

    game.grid = world_module.build_map()
    game.town_funds = max(0, game.town_funds - BUILD_HOUSE_COST)

    if occupant is not None:
        old_home = occupant.home
        occupant.home = key
        occupant.target_location = key
        if old_home != key and world_module.get_kind(old_home) == "house":
            try:
                world_module.set_house_label(old_home, "空房")
            except Exception:
                pass

    game.add_event(f"新建筑落成：{label}（-${BUILD_HOUSE_COST}）", "money")
    game.save(silent=True)
    await broadcast({"type": "state", "data": game.get_state()})
    return JSONResponse({"status": "ok", "house_key": key, "label": label})

@app.post("/api/map/assign-resident")
async def assign_resident_api(req: AssignResidentRequest):
    """Move a resident into (or out of) an already-built custom house."""
    import world as world_module
    if world_module.get_kind(req.house_key) != "house":
        return JSONResponse({"status": "bad_request", "error": "not a custom house"}, status_code=400)

    for a in game.agents:
        if a.home == req.house_key:
            fallback = "apartment" if "apartment" in world_module.LOCATIONS else next(iter(world_module.LOCATIONS))
            a.home = fallback
            if a.target_location == req.house_key:
                a.target_location = fallback

    if req.occupant_agent_id:
        agent = next((a for a in game.agents if a.id == req.occupant_agent_id), None)
        if agent is None:
            return JSONResponse({"status": "not_found"}, status_code=404)
        old_home = agent.home
        agent.home = req.house_key
        agent.target_location = req.house_key
        if old_home != req.house_key and world_module.get_kind(old_home) == "house":
            try:
                world_module.set_house_label(old_home, "空房")
            except Exception:
                pass
        world_module.set_house_label(req.house_key, f"{agent.name}家")
        game.add_event(f"{agent.name} 搬进了新家", "info")
    else:
        world_module.set_house_label(req.house_key, "空房")

    game.save(silent=True)
    await broadcast({"type": "state", "data": game.get_state()})
    return JSONResponse({"status": "ok"})

@app.post("/api/map/remove-house")
async def remove_house_api(req: RemoveHouseRequest):
    """Bulldoze a previously-built custom house (default town buildings can't be removed)."""
    import world as world_module
    try:
        pos = world_module.remove_house(req.house_key)
    except ValueError as e:
        return JSONResponse({"status": "bad_request", "error": str(e)}, status_code=400)
    if pos is None:
        return JSONResponse({"status": "not_found"}, status_code=404)

    fallback = "apartment" if "apartment" in world_module.LOCATIONS else next(iter(world_module.LOCATIONS))
    for a in game.agents:
        if a.home == req.house_key:
            a.home = fallback
        if a.target_location == req.house_key:
            a.target_location = fallback
        if a.current_location == req.house_key:
            a.current_location = fallback

    game.grid = world_module.build_map()
    game.town_funds += REMOVE_HOUSE_REFUND
    game.add_event(f"一栋房子被拆除了（回收 +${REMOVE_HOUSE_REFUND}）", "money")
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
