import asyncio
import random
import time
from typing import Optional, List
from world import LOCATIONS, step_toward, location_for_pos
import ollama_client as ollama

AGENT_CONFIGS = [
    {
        "id": "alice",
        "name": "Alice",
        "personality": "Creative artist. Loves painting and meeting people. Cheerful and expressive.",
        "background": "A small-town artist who fills notebooks with sketches of neighbors, buildings, and passing moods.",
        "goals": ["find visual inspiration", "make people feel seen", "turn ordinary moments into art"],
        "speaking_rules": ["warm and expressive", "often notices colors or details", "asks playful follow-up questions"],
        "occupation": "Artist",
        "home": "house_alice",
        "color": "#FF6B6B",
        "skin": "#FFCC80",
        "hair": "#8B4513",
    },
    {
        "id": "bob",
        "name": "Bob",
        "personality": "Introverted programmer. Loves coffee and tech. Thoughtful but socially awkward.",
        "background": "A software engineer who moved to town for a quieter life and still thinks in systems and edge cases.",
        "goals": ["solve practical problems", "avoid awkward misunderstandings", "find calm places to focus"],
        "speaking_rules": ["concise and thoughtful", "can sound a little shy", "uses concrete observations instead of big emotions"],
        "occupation": "Software Engineer",
        "home": "house_bob",
        "color": "#4FC3F7",
        "skin": "#FFCC80",
        "hair": "#212121",
    },
    {
        "id": "carol",
        "name": "Carol",
        "personality": "Energetic teacher. Loves reading and helping others. Very talkative.",
        "background": "A teacher who remembers what each person is learning, worrying about, or secretly proud of.",
        "goals": ["encourage others", "share useful knowledge", "keep conversations lively"],
        "speaking_rules": ["bright and encouraging", "often explains or reframes things", "asks caring check-in questions"],
        "occupation": "Teacher",
        "home": "house_carol",
        "color": "#FFB74D",
        "skin": "#FFCCB6",
        "hair": "#FF6F00",
    },
    {
        "id": "diana",
        "name": "Diana",
        "personality": "Ambitious chef. Passionate about food and culture. Bold and confident.",
        "background": "A chef building her reputation through bold dishes, sharp instincts, and generous hospitality.",
        "goals": ["create memorable food", "push people to be braver", "bring culture and flavor into daily life"],
        "speaking_rules": ["confident and vivid", "can challenge vague opinions", "often relates feelings to taste or craft"],
        "occupation": "Chef",
        "home": "house_diana",
        "color": "#CE93D8",
        "skin": "#FFCC80",
        "hair": "#4A148C",
    },
    {
        "id": "eve",
        "name": "Eve",
        "personality": "Quiet librarian. Loves books and nature. Observant and wise.",
        "background": "A librarian who knows the town's quiet rhythms and notices the small truths people leave between words.",
        "goals": ["understand people gently", "protect quiet spaces", "connect moments to stories or nature"],
        "speaking_rules": ["soft-spoken and observant", "uses calm language", "offers thoughtful questions rather than quick advice"],
        "occupation": "Librarian",
        "home": "house_eve",
        "color": "#80CBC4",
        "skin": "#FFCC80",
        "hair": "#1B5E20",
    },
]



class Agent:
    def __init__(self, config: dict, model: str, npc_model: str = ""):
        self.id = config["id"]
        self.name = config["name"]
        self.personality = config["personality"]
        self.occupation = config["occupation"]
        self.background = str(config.get("background") or self._default_background())
        self.goals = self._clean_text_list(config.get("goals"), self._default_goals())
        self.speaking_rules = self._clean_text_list(
            config.get("speaking_rules"),
            self._default_speaking_rules(),
        )
        self.home = config["home"]
        self.color = config["color"]
        self.skin = config["skin"]
        self.hair = config["hair"]
        self.model = model               # 大模型：玩家对话
        self.npc_model = npc_model or model  # 小模型：NPC 自主行为

        loc = LOCATIONS[self.home]
        self.x = float(loc["center"][0])
        self.y = float(loc["center"][1])

        self.target_location = self.home
        self.current_location = self.home
        self.status = "在镇上闲逛"
        self.chat_bubble = ""
        self.chat_bubble_time = 0
        self.memories: list[str] = [f"我是{self.name}，一名{self.occupation}。"]
        # Persistent player↔this-character chat log (kept separate from `memories`
        # so what the player tells the character is never crowded out by the
        # character's own autonomous activity, and survives reloads via the save).
        self.player_log: list[dict] = []
        self.talking_to = None  # type: Optional[str]
        self.decision_cooldown = random.randint(3, 10)
        self.thought_cooldown = random.randint(6, 18)
        self.plan: list[str] = []
        self.mood = random.randint(58, 82)
        self.hunger = random.randint(12, 35)
        self.energy = random.randint(62, 92)
        self.fun = random.randint(45, 78)
        self.social = random.randint(35, 72)
        self.money = random.randint(90, 180)
        self.relationships: dict[str, int] = {}
        self.thought = self.fallback_thought()
        self.thought_time = time.time()

    def _clean_text_list(self, value, fallback: list[str]) -> list[str]:
        if isinstance(value, str):
            items = [part.strip() for part in value.replace("；", ";").split(";")]
        elif isinstance(value, list):
            items = [str(part).strip() for part in value]
        else:
            items = []
        cleaned = [item for item in items if item]
        return cleaned[:5] or fallback

    def _default_background(self) -> str:
        return f"{self.name} is a {self.occupation} living in this small town."

    def _default_goals(self) -> list[str]:
        return ["过好今天", "和镇上的人保持自然的关系", "做符合自己性格的小事"]

    def _default_speaking_rules(self) -> list[str]:
        return ["口语化", "符合自己的职业和性格", "不要突然变成旁白或解释设定"]

    def role_card_prompt(self) -> str:
        goals = "；".join(self.goals)
        rules = "；".join(self.speaking_rules)
        return (
            f"你是{self.name}（{self.occupation}）。\n"
            f"性格风格：{self.personality}。\n"
            f"人物背景：{self.background}\n"
            f"当前目标：{goals}\n"
            f"说话规则：{rules}\n"
            f"请始终保持这个角色，不要跳出角色或解释设定。"
        )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "x": round(self.x, 3),
            "y": round(self.y, 3),
            "color": self.color,
            "skin": self.skin,
            "hair": self.hair,
            "home": self.home,
            "status": self.status,
            "chat_bubble": self.chat_bubble if time.time() - self.chat_bubble_time < 6 else "",
            "current_location": self.current_location,
            "target_location": self.target_location,
            "occupation": self.occupation,
            "personality": self.personality,
            "background": self.background,
            "goals": list(self.goals),
            "speaking_rules": list(self.speaking_rules),
            "memories": self.memories[-10:],
            "memories_count": len(self.memories),
            "player_log": self.player_log[-20:],
            "mood": self.mood,
            "hunger": self.hunger,
            "energy": self.energy,
            "fun": self.fun,
            "social": self.social,
            "money": self.money,
            "relationships": dict(sorted(self.relationships.items())),
            "thought": self.thought,
            "thought_time": self.thought_time,
        }

    def to_save_dict(self) -> dict:
        data = self.to_dict()
        data.update({
            "x": self.x,
            "y": self.y,
            "chat_bubble": self.chat_bubble,
            "chat_bubble_time": self.chat_bubble_time,
            "memories": list(self.memories),
            "player_log": list(self.player_log),
            "decision_cooldown": self.decision_cooldown,
            "thought_cooldown": self.thought_cooldown,
            "thought": self.thought,
            "thought_time": self.thought_time,
        })
        return data

    def apply_save_dict(self, data: dict):
        self.x = float(data.get("x", self.x))
        self.y = float(data.get("y", self.y))
        # Restore which house this resident lives in. Without this, a default
        # named resident (Alice/Bob/Carol/Diana/Eve) who gets moved into a
        # custom-built house via the map editor would silently snap back to
        # their original hardcoded home on the next server restart, since
        # those agents are reconstructed from AGENT_CONFIGS first and this
        # method is what layers the saved state on top.
        saved_home = data.get("home")
        if saved_home and saved_home in LOCATIONS:
            self.home = saved_home
        elif saved_home and saved_home not in LOCATIONS:
            # The saved home (e.g. a removed custom house) no longer exists.
            self.home = "apartment" if "apartment" in LOCATIONS else self.home
        self.target_location = data.get("target_location", self.target_location)
        self.current_location = data.get("current_location", self.current_location)
        if self.target_location not in LOCATIONS:
            self.target_location = self.home
        if self.current_location not in LOCATIONS:
            self.current_location = self.home
        self.status = "在镇上闲逛"
        self.chat_bubble = data.get("chat_bubble", "")
        self.chat_bubble_time = float(data.get("chat_bubble_time", 0))
        self.memories = list(data.get("memories", self.memories))[-30:]
        self.player_log = [m for m in data.get("player_log", []) if isinstance(m, dict)][-40:]
        self.background = str(data.get("background") or self.background or self._default_background())
        self.goals = self._clean_text_list(data.get("goals"), self.goals or self._default_goals())
        self.speaking_rules = self._clean_text_list(
            data.get("speaking_rules"),
            self.speaking_rules or self._default_speaking_rules(),
        )
        self.decision_cooldown = int(data.get("decision_cooldown", self.decision_cooldown))
        self.thought_cooldown = int(data.get("thought_cooldown", self.thought_cooldown))
        self.mood = int(data.get("mood", self.mood))
        self.hunger = int(data.get("hunger", self.hunger))
        self.energy = int(data.get("energy", self.energy))
        self.fun = int(data.get("fun", self.fun))
        self.social = int(data.get("social", self.social))
        self.money = int(data.get("money", self.money))
        self.relationships = {str(k): int(v) for k, v in data.get("relationships", {}).items()}
        self.thought = data.get("thought") or self.fallback_thought()
        self.thought_time = float(data.get("thought_time", time.time()))

    def add_memory(self, mem: str):
        self.memories.append(mem)
        if len(self.memories) > 40:
            self.memories = self.memories[-40:]

    def _rel_desc(self, other_id: str) -> str:
        v = self.relationships.get(other_id, 0)
        if v < 10:  return "第一次见面"
        if v < 30:  return "点头之交"
        if v < 55:  return "普通朋友"
        if v < 75:  return "好朋友"
        return "挚友"

    def _shared_memories(self, other_name: str) -> str:
        shared = [m for m in self.memories if other_name in m]
        return shared[-1] if shared else ""

    def set_bubble(self, text: str):
        self.chat_bubble = text[:100]
        self.chat_bubble_time = time.time()

    def set_thought(self, text: str):
        clean = " ".join((text or "").strip().split())
        if clean:
            self.thought = clean[:80]
            self.thought_time = time.time()

    def tick_needs(self, game_hour: float):
        """Small Tamagotchi-style needs loop that keeps residents legible without AI."""
        hour = int(game_hour) % 24
        self.hunger = min(100, self.hunger + random.choice([0, 1, 1, 2]))
        self.fun = max(0, self.fun - random.choice([0, 0, 1]))
        self.social = max(0, self.social - random.choice([0, 0, 1]))
        self.energy = max(0, self.energy - (2 if 23 <= hour or hour < 6 else random.choice([0, 1])))

        if self.current_location == "cafe":
            self.hunger = max(0, self.hunger - 5)
            self.fun = min(100, self.fun + 2)
        elif self.current_location == "park":
            self.energy = min(100, self.energy + 2)
            self.fun = min(100, self.fun + 3)
        elif self.current_location == "library":
            self.energy = min(100, self.energy + 1)
            self.fun = min(100, self.fun + 1)
        elif self.current_location == self.home:
            self.energy = min(100, self.energy + 4)

        self.mood = max(0, min(100, 90 - self.hunger // 2 + self.fun // 5 + self.social // 6 + self.energy // 8))

    def choose_need_location(self, game_time: str) -> str:
        hour = int(game_time.split(":")[0])
        if self.energy < 28 or hour >= 22 or hour < 7:
            return self.home
        if self.hunger > 68:
            return "cafe"
        if self.social < 24:
            return random.choice(["town_square", "park", "cafe"])
        if self.fun < 30:
            return random.choice(["park", "library", "town_square"])
        profile_text = " ".join([self.personality, self.background, *self.goals, *self.speaking_rules]).lower()
        preference_pool: list[str] = []
        preference_rules = [
            (("art", "inspiration", "creative", "画", "艺术", "灵感"), ["park", "town_square", "cafe"]),
            (("book", "story", "library", "quiet", "书", "故事", "安静"), ["library", "park"]),
            (("food", "chef", "taste", "cafe", "吃", "料理", "味道"), ["cafe", "town_square"]),
            (("tech", "code", "focus", "system", "program", "技术", "编程"), ["office", "library"]),
            (("help", "teach", "encourage", "care", "帮助", "照顾", "鼓励"), ["town_square", "office", "library"]),
            (("social", "people", "friend", "lively", "朋友", "热闹", "社交"), ["town_square", "cafe", "park"]),
        ]
        for keywords, locations in preference_rules:
            if any(keyword in profile_text for keyword in keywords):
                preference_pool.extend([loc for loc in locations if loc in LOCATIONS])
        if preference_pool and random.random() < 0.35:
            return random.choice(preference_pool)
        if self.occupation.lower() in ("teacher", "software engineer") and 9 <= hour <= 17:
            return "office"
        if self.occupation.lower() == "librarian" and 9 <= hour <= 18:
            return "library"
        if self.occupation.lower() == "chef" and 10 <= hour <= 20:
            return "cafe"
        if self.occupation.lower() == "artist":
            return random.choice(["park", "town_square", "cafe"])
        choices = [k for k in LOCATIONS if k != self.current_location]
        return random.choice(choices)

    def improve_relationship(self, other_id: str, amount: int):
        self.relationships[other_id] = max(-100, min(100, self.relationships.get(other_id, 0) + amount))
        self.social = min(100, self.social + 12)
        self.fun = min(100, self.fun + 5)
        self.mood = min(100, self.mood + 4)

    def fallback_status(self, location_label: str) -> str:
        by_location = {
            "cafe": ["喝咖啡", "看报纸", "享受下午茶"],
            "library": ["安静看书", "翻阅书籍", "查找资料"],
            "park": ["散步晒太阳", "欣赏风景", "发呆放空"],
            "town_square": ["看人来人往", "四处闲逛", "晒太阳"],
            "office": ["认真工作", "处理事务", "敲着键盘"],
            "apartment": ["在家休息", "整理房间", "放松发呆"],
        }
        key = self.current_location
        if key == self.home:
            options = ["在家休息", "悠闲地待着", "打个盹"]
        else:
            options = by_location.get(key, [f"在{location_label}逛逛"])
        if self.hunger > 72:
            return "饿得想吃东西"
        if self.energy < 25:
            return "累得想休息"
        return random.choice(options)

    def fallback_thought(self, other_name: str = "") -> str:
        if other_name:
            return random.choice([
                f"刚才和{other_name}聊天还挺开心的。",
                f"下次想再找{other_name}聊聊。",
                f"不知道{other_name}现在在想什么。",
            ])
        if self.hunger > 72:
            return "肚子有点饿，想找点好吃的。"
        if self.energy < 28:
            return "有点累了，想回家休息。"
        if self.social < 28:
            return "今天想见见小镇里的朋友。"
        if self.fun < 32:
            return "想做点有趣的事换换心情。"
        if self.mood < 45:
            return "心情不太稳定，需要慢慢调整。"
        if self.current_location == self.home:
            return "在家待着也不错。"
        loc = LOCATIONS.get(self.current_location, {}).get("label", "这里")
        return random.choice([
            f"今天的{loc}让人想多待一会儿。",
            "等会儿要不要换个地方走走？",
            "小镇今天好像挺热闹的。",
        ])

    async def generate_thought(self, game_time: str, other_name: str = "") -> str:
        recent = "；".join(self.memories[-4:])
        loc_label = LOCATIONS.get(self.current_location, {}).get("label", "某处")
        # Build a natural state hint
        state_hints = []
        if self.hunger > 70: state_hints.append("有点饿")
        if self.energy < 28: state_hints.append("有些疲倦")
        if self.social < 25: state_hints.append("想见见朋友")
        if self.fun < 28: state_hints.append("想找点乐子")
        if self.mood > 75: state_hints.append("心情不错")
        state_line = "当前状态：" + "，".join(state_hints) + "。\n" if state_hints else ""
        after_chat = f"刚和{other_name}聊过天。\n" if other_name else ""
        prompt = (
            f"{self.role_card_prompt()}\n"
            f"现在{game_time}，你在{loc_label}。\n"
            f"{state_line}{after_chat}"
            f"近期经历：{recent}\n"
            f"只输出一句内心独白（15-35字，无引号，无emoji，无旁白，纯中文）："
        )
        thought = await ollama.generate(prompt, model=self.npc_model, max_tokens=60)
        return thought.strip() or self.fallback_thought(other_name)
    async def decide_next_location(self, game_time: str) -> str:
        need_choice = self.choose_need_location(game_time)
        if random.random() < 0.65:
            return need_choice

        recent_mems = "; ".join(self.memories[-5:])
        loc_labels = ", ".join([v["label"] for v in LOCATIONS.values()])
        loc_keys = ", ".join(LOCATIONS.keys())

        prompt = (
            f"{self.role_card_prompt()}\n"
            f"现在时间：{game_time}。你在{LOCATIONS[self.current_location]['label']}。\n"
            f"近期记忆：{recent_mems}\n"
            f"可去的地方（用英文key回答）：{loc_keys}\n"
            f"根据你的性格和时间，你最想去哪里？只回答一个英文key，不要其他内容。"
        )

        result = await ollama.generate(prompt, model=self.npc_model, max_tokens=15)
        result = result.strip().lower().split()[0] if result.strip() else ""
        # remove punctuation
        result = "".join(c for c in result if c.isalnum() or c == "_")
        if result in LOCATIONS:
            return result
        return need_choice

    async def generate_reply(self, other_name: str, history: list[dict],
                             other_personality: str, other_id: str = "") -> str:
        """基于完整对话历史生成回复，history 是 [{"role":"user/assistant","content":...}] 列表。"""
        rel_desc = self._rel_desc(other_id)
        shared = self._shared_memories(other_name)
        shared_line = f"你们上次的记忆：{shared}\n" if shared else ""
        recent = "；".join(self.memories[-3:])
        loc_label = LOCATIONS.get(self.current_location, {}).get("label", "某处")
        mood_hint = (
            "你现在心情很好。" if self.mood > 70
            else "你今天有点疲惫。" if self.energy < 30
            else ""
        )
        system = (
            f"{self.role_card_prompt()}\n"
            f"你和{other_name}（{other_personality}）在{loc_label}，你们是{rel_desc}。\n"
            f"{shared_line}"
            f"你的近期经历：{recent}\n"
            f"{mood_hint}\n"
            f"【规则】只输出{self.name}说的一句话（1-2句，不超过50字）。"
            f"禁止：emoji、括号动作描述、引号、元评论、英文、乱码。"
            f"要求：紧扣上文话题，口语化，可以追问或分享感受。"
        )
        messages = [{"role": "system", "content": system}] + history
        reply = await ollama.chat(messages, model=self.npc_model, max_tokens=100)
        return reply.strip() or ""

    async def generate_greeting(self, other_name: str, location_label: str,
                                other_id: str = "") -> str:
        rel_desc = self._rel_desc(other_id)
        shared = self._shared_memories(other_name)
        shared_line = f"上次见面：{shared}\n" if shared else ""
        hour = int(self.thought_time % 86400 // 3600) if False else 0  # placeholder
        time_hint = ""
        prompt = (
            f"{self.role_card_prompt()}\n"
            f"你在{location_label}遇到了{other_name}，你们是{rel_desc}。\n"
            f"{shared_line}"
            f"只输出一句中文打招呼的话（不超过25字，无引号，无emoji，无旁白）："
        )
        greeting = await ollama.generate(prompt, model=self.npc_model, max_tokens=60)
        return greeting.strip() or ""

    async def generate_action_status(self, location_label: str) -> str:
        mood_hint = "心情愉快，" if self.mood > 70 else "有些心不在焉，" if self.mood < 40 else ""
        prompt = (
            f"{self.role_card_prompt()}\n"
            f"你{mood_hint}正在{location_label}。\n"
            f"用5-10个中文字描述你此刻在做的具体事情（如\"翻阅一本旧画册\"），不加引号："
        )
        status = await ollama.generate(prompt, model=self.npc_model, max_tokens=25)
        return status.strip() or self.fallback_status(location_label)

    async def generate_user_reply(self, user_text: str, history: Optional[list] = None) -> str:
        """以角色身份回复正在与之聊天的玩家（访客）。

        上下文优先用服务端持久化的 `player_log`（跨会话保留、且不被日常记忆冲掉），
        客户端传来的 history 仅作回退。这样角色能"记住访客告诉过它的事"。"""
        loc_label = LOCATIONS.get(self.current_location, {}).get("label", "某处")
        system = (
            f"{self.role_card_prompt()}\n"
            f"你现在在{loc_label}。\n"
            f"下面的对话记录是你和这位访客以前聊过的内容——请牢牢记住其中访客告诉过你的"
            f"信息（名字、喜好、约定、要求等），回答时要体现出你记得这些。\n"
            f"请始终以{self.name}的身份、用口语化的中文回复，符合你的性格，"
            f"1-2句话，不超过50字。不要加引号，不要写旁白或动作描述。"
        )
        messages = [{"role": "system", "content": system}]
        # 优先用持久化的玩家对话日志；为空时回退到客户端传来的 history
        log = self.player_log[-24:] if self.player_log else (history or [])[-12:]
        for h in log:
            role = "user" if h.get("role") == "user" else "assistant"
            content = str(h.get("text", "")).strip()[:200]
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": str(user_text).strip()[:200]})
        reply = await ollama.chat(messages, model=self.model, max_tokens=120)
        return " ".join((reply or "").strip().split())[:100]
