import asyncio
import importlib
import logging
import os
import random
import time
from datetime import datetime
from agents import Agent, AGENT_CONFIGS
import world as _world_mod
from world import build_map, LOCATIONS, step_toward, location_for_pos, has_line_of_sight, MAP_COLS, MAP_ROWS
import ollama_client as ollama
from config import load_config
from persistence import load_game, reset_save, save_game

CONFIG = load_config()

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
ENCOUNTER_RANGE = 1.05
ENCOUNTER_RELEASE_RANGE = 2.0
STARTING_TOWN_FUNDS = 3500

def _setup_logging() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(LOG_DIR, f"tomodachi_{date_str}.log")

    logger = logging.getLogger("tomodachi")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
        logger.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(ch)

    return logger

logger = _setup_logging()


class GameEngine:
    def __init__(self):
        self.grid = []
        self.agents = []  # list[Agent]
        self.tick_count = 0
        self.game_hour = 8.0  # start at 8 AM
        self.model = "qwen3"
        self.events: list[dict] = []
        self.town_funds = STARTING_TOWN_FUNDS
        self.last_economy_hour = int(self.game_hour) % 24
        self.active_conversations: dict[frozenset, int] = {}  # pair -> turns remaining
        self.conversation_queue: asyncio.Queue = asyncio.Queue()
        self.conversation_cooldowns: dict[frozenset, int] = {}
        self._conv_task = None
        self._llm_sem = asyncio.Semaphore(1)  # 同一时间只跑一个 NPC 对话，避免 36B 模型卡死
        self._world_mtime: float = os.path.getmtime(_world_mod.__file__)
        self.save_loaded = False
        self.paused = False  # when True, game_loop skips tick() — time/movement frozen

    async def initialize(self):
        logger.info("=" * 50)
        logger.info(f"=== game start {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
        logger.info("=" * 50)

        self.grid = build_map()
        models = await ollama.list_models()

        def pick_model(prefs):
            for pref in prefs:
                for m in models:
                    if pref in m.lower():
                        return m
            return models[0] if models else "qwen3"

        # 大模型用于玩家对话，小模型用于 NPC 自主行为（快）
        self.model = pick_model(CONFIG.preferred_models)
        fast_prefs = ["qwen3:0.6", "qwen3", "llama3.2:3b", "llama3.2"]
        self.npc_model = pick_model(fast_prefs)
        logger.info(f"[INIT] player model: {self.model}  npc model: {self.npc_model}")

        for cfg in AGENT_CONFIGS:
            self.agents.append(Agent(cfg, self.model, npc_model=self.npc_model))
        logger.info(f"[INIT] loaded {len(self.agents)} agents")

        if CONFIG.autoload_save:
            self.save_loaded = load_game(self, CONFIG.save_path)
            if self.save_loaded:
                self.add_event("已读取小镇存档", "info")

        self._conv_task = asyncio.create_task(self._conversation_worker())

    def save(self, silent: bool = False) -> dict:
        data = save_game(self, CONFIG.save_path)
        if not silent:
            self.add_event("小镇已保存", "info")
        return data

    def load(self) -> bool:
        loaded = load_game(self, CONFIG.save_path)
        if loaded:
            self.add_event("小镇存档已载入", "info")
        return loaded

    def reset_save(self) -> bool:
        return reset_save(CONFIG.save_path)

    def get_time_str(self) -> str:
        h = int(self.game_hour) % 24
        m = int((self.game_hour % 1) * 60)
        return f"{h:02d}:{m:02d}"

    def add_event(self, text: str, kind: str = "info", agent_id: str = ""):
        t = self.get_time_str()
        self.events.append({"t": t, "text": text, "kind": kind, "agent": agent_id})
        if len(self.events) > 200:
            self.events = self.events[-200:]
        logger.info(f"[{t}] [{kind.upper():4s}] {text}")

    def get_state(self) -> dict:
        blocks, block_bounds = _world_mod.block_grid_payload()
        return {
            "tick": self.tick_count,
            "time": self.get_time_str(),
            "paused": self.paused,
            "game_hour": round(self.game_hour, 2),
            "agents": [a.to_dict() for a in self.agents],
            "events": self.events[-50:],
            "grid": self.grid,
            "map_cols": _world_mod.MAP_COLS,
            "map_rows": _world_mod.MAP_ROWS,
            "model": self.model,
            "town_mood": self._town_mood(),
            "town_funds": self.town_funds,
            "economy": {
                "town_funds": self.town_funds,
                "build_house_cost": 450,
                "remove_house_refund": 120,
            },
            "locations": {
                k: {
                    "label": v["label"],
                    "center": list(v["center"]),
                    "color": v.get("color", "#888888"),
                    "kind": v.get("kind", "fixed"),
                    "occupant": next((a.name for a in self.agents if a.home == k), None),
                }
                for k, v in _world_mod.LOCATIONS.items()
            },
            "blocks": blocks,
            "block_bounds": block_bounds,
            "house_styles": _world_mod.HOUSE_STYLES,
        }

    def _town_mood(self) -> int:
        if not self.agents:
            return 0
        return round(sum(a.mood for a in self.agents) / len(self.agents))

    def _hot_reload_world(self):
        """Reload world.py if changed on disk and refresh module-level symbols."""
        global LOCATIONS, step_toward, location_for_pos, has_line_of_sight, MAP_COLS, MAP_ROWS, build_map
        try:
            current_mtime = os.path.getmtime(_world_mod.__file__)
            if current_mtime != self._world_mtime:
                importlib.reload(_world_mod)
                self._world_mtime = current_mtime
                LOCATIONS = _world_mod.LOCATIONS
                step_toward = _world_mod.step_toward
                location_for_pos = _world_mod.location_for_pos
                has_line_of_sight = _world_mod.has_line_of_sight
                MAP_COLS = _world_mod.MAP_COLS
                MAP_ROWS = _world_mod.MAP_ROWS
                build_map = _world_mod.build_map
                import agents as agents_module
                agents_module.LOCATIONS = _world_mod.LOCATIONS
                self.grid = _world_mod.build_map()
                default_loc = next(iter(_world_mod.LOCATIONS))
                for agent in self.agents:
                    if agent.target_location not in _world_mod.LOCATIONS:
                        agent.target_location = default_loc
                    if agent.current_location not in _world_mod.LOCATIONS:
                        agent.current_location = default_loc
                self.add_event("map hot-reloaded", "info")
                logger.info(f"[HOT-RELOAD] world.py reloaded MAP={_world_mod.MAP_COLS}x{_world_mod.MAP_ROWS}")
        except Exception as e:
            logger.warning(f"[WARN] hot-reload failed: {e}")

    async def tick(self) -> list[dict]:
        self._hot_reload_world()
        self.tick_count += 1
        prev_hour = int(self.game_hour) % 24
        self.game_hour = (self.game_hour + CONFIG.game_hours_per_tick) % 24
        current_hour = int(self.game_hour) % 24
        new_events = []

        if current_hour != prev_hour:
            self._tick_economy(current_hour)

        for pair in list(self.conversation_cooldowns):
            self.conversation_cooldowns[pair] -= 1
            if self.conversation_cooldowns[pair] <= 0:
                del self.conversation_cooldowns[pair]

        for agent in self.agents:
            agent.tick_needs(self.game_hour)

            # 对话中：冻结移动和决策，让双方驻足
            if agent.talking_to is not None:
                agent.decision_cooldown = max(agent.decision_cooldown, 8)
                agent.thought_cooldown -= 1
                if agent.thought_cooldown <= 0:
                    agent.thought_cooldown = random.randint(35, 75)
                    asyncio.create_task(self._agent_think(agent))
                continue

            target_loc = LOCATIONS[agent.target_location]
            tc, tr = target_loc["center"]
            agent.x, agent.y = step_toward(self.grid, agent.x, agent.y, tc, tr)

            loc = location_for_pos(agent.x, agent.y)
            if loc:
                agent.current_location = loc
                if agent.current_location == agent.target_location and random.random() < 0.04:
                    agent.status = agent.fallback_status(LOCATIONS[loc]["label"])

            agent.decision_cooldown -= 1
            if agent.decision_cooldown <= 0:
                agent.decision_cooldown = random.randint(20, 50)
                asyncio.create_task(self._agent_decide(agent))

            agent.thought_cooldown -= 1
            if agent.thought_cooldown <= 0:
                agent.thought_cooldown = random.randint(35, 75)
                asyncio.create_task(self._agent_think(agent))

        await self._check_encounters()
        return new_events

    def _tick_economy(self, hour: int):
        """Settle simple hourly income and spending for the town economy."""
        for agent in self.agents:
            earned = self._hourly_income(agent, hour)
            if earned:
                agent.money += earned
                self.town_funds += max(1, earned // 5)
                if random.random() < 0.08:
                    self.add_event(f"{agent.name} 工作赚了 ${earned}", "money", agent.id)

            spent = self._hourly_spending(agent, hour)
            if spent and agent.money >= spent:
                agent.money -= spent
                self.town_funds += max(1, spent // 2)
                if agent.current_location == "cafe":
                    agent.hunger = max(0, agent.hunger - 8)
                    agent.fun = min(100, agent.fun + 3)
                if random.random() < 0.06:
                    self.add_event(f"{agent.name} 花了 ${spent}", "money", agent.id)
            elif spent and agent.money < spent and agent.current_location == "cafe":
                agent.status = "看着菜单犹豫"

        self.town_funds = max(0, min(999999, int(self.town_funds)))

    def _hourly_income(self, agent: Agent, hour: int) -> int:
        loc = agent.current_location
        job = agent.occupation.lower()
        if loc == "office" and 9 <= hour <= 17:
            if job in ("teacher", "software engineer", "engineer", "programmer"):
                return random.randint(16, 26)
            return random.randint(8, 14)
        if loc == "library" and 9 <= hour <= 18 and job == "librarian":
            return random.randint(12, 20)
        if loc == "cafe" and 10 <= hour <= 20 and job == "chef":
            return random.randint(16, 28)
        if job == "artist" and loc in ("park", "town_square", "cafe") and 10 <= hour <= 19:
            return random.randint(5, 15)
        return 0

    def _hourly_spending(self, agent: Agent, hour: int) -> int:
        if agent.current_location == "cafe" and 7 <= hour <= 22:
            return random.randint(6, 12)
        if agent.current_location == "town_square" and 10 <= hour <= 20 and random.random() < 0.25:
            return random.randint(2, 6)
        return 0

    async def _agent_decide(self, agent: Agent):
        try:
            new_loc = await agent.decide_next_location(self.get_time_str())
            if new_loc != agent.target_location:
                agent.target_location = new_loc
                label = LOCATIONS[new_loc]["label"]
                agent.status = f"前往{label}"
                self.add_event(f"{agent.name} 前往{label}", "move", agent.id)
                asyncio.create_task(self._update_agent_status(agent, new_loc))
        except Exception as e:
            logger.warning(f"[WARN] decide failed {agent.name}: {e}")

    async def _agent_think(self, agent: Agent, other_name: str = ""):
        try:
            thought = await agent.generate_thought(self.get_time_str(), other_name)
            agent.set_thought(thought)
        except Exception as e:
            logger.warning(f"[WARN] thought gen failed {agent.name}: {e}")
            agent.set_thought(agent.fallback_thought(other_name))

    async def _update_agent_status(self, agent: Agent, loc_key: str):
        try:
            label = LOCATIONS[loc_key]["label"]
            status = await agent.generate_action_status(label)
            if status:
                agent.status = status
        except Exception as e:
            logger.warning(f"[WARN] status gen failed {agent.name}: {e}")

    async def _check_encounters(self):
        for i, a1 in enumerate(self.agents):
            for a2 in self.agents[i+1:]:
                dist = ((a1.x - a2.x)**2 + (a1.y - a2.y)**2)**0.5
                pair = frozenset([a1.id, a2.id])
                visible = (
                    dist <= ENCOUNTER_RELEASE_RANGE
                    and has_line_of_sight(self.grid, a1.x, a1.y, a2.x, a2.y)
                )
                if (
                    dist <= ENCOUNTER_RANGE
                    and visible
                    and pair not in self.active_conversations
                    and pair not in self.conversation_cooldowns
                    and a1.talking_to is None
                    and a2.talking_to is None
                ):
                    self.active_conversations[pair] = 0
                    await self.conversation_queue.put((a1, a2))
                if pair in self.active_conversations and (dist > ENCOUNTER_RELEASE_RANGE or not visible):
                    del self.active_conversations[pair]

    async def _conversation_worker(self):
        while True:
            try:
                a1, a2 = await asyncio.wait_for(
                    self.conversation_queue.get(), timeout=1.0
                )
                async with self._llm_sem:
                    await self._run_conversation(a1, a2)
                self.conversation_queue.task_done()
                await asyncio.sleep(0.5)
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.warning(f"[WARN] conv worker error: {e}")

    async def _run_conversation(self, a1: Agent, a2: Agent):
        pair = frozenset([a1.id, a2.id])
        loc_label = LOCATIONS.get(a1.current_location, {}).get("label", "某处")
        self.add_event(f"{a1.name} 在{loc_label}遇见了 {a2.name}", "meet", a1.id)

        a1.talking_to = a2.id
        a2.talking_to = a1.id
        a1.set_thought(a1.fallback_thought(a2.name))
        a2.set_thought(a2.fallback_thought(a1.name))
        a1.thought_cooldown = random.randint(20, 45)
        a2.thought_cooldown = random.randint(20, 45)

        greeting = await a1.generate_greeting(a2.name, loc_label, other_id=a2.id)
        if not greeting:
            a1.talking_to = None
            a2.talking_to = None
            self.conversation_cooldowns[pair] = random.randint(18, 35)
            return

        a1.set_bubble(greeting)
        a1.add_memory(f"在{loc_label}遇到{a2.name}，说：{greeting}")
        self.add_event(f"{a1.name}: {greeting}", "chat", a1.id)
        a1.improve_relationship(a2.id, random.randint(4, 9))
        a2.improve_relationship(a1.id, random.randint(3, 8))

        # 维护完整对话历史（从 a2 视角：a1 是 user，a2 是 assistant）
        # 每轮回复时将历史翻转，以当前说话人视角构造 user/assistant
        history: list[dict] = [{"role": "user", "content": greeting}]

        # 3-4 轮交替对话
        turns = random.randint(3, 4)
        speakers = [a2, a1, a2, a1]
        listeners = [a1, a2, a1, a2]

        for i in range(turns):
            await asyncio.sleep(random.uniform(0.4, 0.7))
            spk, lst = speakers[i], listeners[i]

            # 从说话人视角：对方说的是 user，自己说的是 assistant
            spk_history = []
            for j, msg in enumerate(history):
                role = "user" if j % 2 == 0 else "assistant"
                spk_history.append({"role": role, "content": msg["content"]})

            reply = await spk.generate_reply(
                lst.name, spk_history, lst.personality, other_id=lst.id
            )
            if not reply:
                break
            spk.set_bubble(reply)
            spk.add_memory(f"和{lst.name}在{loc_label}聊：{reply}")
            self.add_event(f"{spk.name}: {reply}", "chat", spk.id)
            spk.improve_relationship(lst.id, random.randint(2, 5))
            lst.improve_relationship(spk.id, random.randint(1, 4))
            history.append({"role": "assistant", "content": reply})

        # 把对话要点存入双方记忆
        if len(history) >= 2:
            summary = "、".join(m["content"][:20] for m in history[-2:])
            a1.add_memory(f"和{a2.name}在{loc_label}聊到：{summary}")
            a2.add_memory(f"和{a1.name}在{loc_label}聊到：{summary}")

        a1.talking_to = None
        a2.talking_to = None
        # 对话结束后原地多停一会儿，让玩家看清最后一句话再散开
        linger = random.randint(12, 22)
        a1.decision_cooldown = linger
        a2.decision_cooldown = linger
        self.conversation_cooldowns[pair] = random.randint(25, 45)

    async def user_chat(self, agent_id: str, text: str, history: list | None = None) -> dict:
        """玩家（访客）直接对某个角色说话，角色用 LLM 以其性格回复。"""
        agent = next((a for a in self.agents if a.id == agent_id), None)
        if agent is None:
            return {"ok": False, "error": "agent_not_found"}
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "empty"}
        try:
            reply = await agent.generate_user_reply(text, history)
        except Exception as e:
            logger.warning(f"[WARN] user_chat failed {agent.name}: {e}")
            reply = "（……我现在有点走神了，等会儿再聊好吗？）"
        agent.set_bubble(reply)
        # Append this exchange to the persistent player log (kept ≤40 entries) so
        # the character keeps remembering it across turns and across restarts.
        agent.player_log.append({"role": "user", "text": text})
        agent.player_log.append({"role": "agent", "text": reply})
        if len(agent.player_log) > 40:
            agent.player_log = agent.player_log[-40:]
        # Chatting lifts the resident's social/mood a little
        agent.social = min(100, agent.social + 6)
        agent.mood = min(100, agent.mood + 3)
        self.add_event(f"你 → {agent.name}：{text}", "chat", agent.id)
        self.add_event(f"{agent.name}：{reply}", "chat", agent.id)
        # Persist immediately so a refresh/restart doesn't lose what you just told them
        try:
            self.save(silent=True)
        except Exception:
            pass
        return {"ok": True, "agent_id": agent_id, "text": reply}
