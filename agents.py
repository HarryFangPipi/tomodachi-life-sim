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
        "occupation": "Librarian",
        "home": "house_eve",
        "color": "#80CBC4",
        "skin": "#FFCC80",
        "hair": "#1B5E20",
    },
]

class Agent:
    def __init__(self, config: dict, model: str):
        self.id = config["id"]
        self.name = config["name"]
        self.personality = config["personality"]
        self.occupation = config["occupation"]
        self.home = config["home"]
        self.color = config["color"]
        self.skin = config["skin"]
        self.hair = config["hair"]
        self.model = model

        loc = LOCATIONS[self.home]
        self.x = float(loc["center"][0])
        self.y = float(loc["center"][1])

        self.target_location = self.home
        self.current_location = self.home
        self.status = "在镇上闲逛"
        self.chat_bubble = ""
        self.chat_bubble_time = 0
        self.memories: list[str] = [f"我是{self.name}，一名{self.occupation}。"]
        self.talking_to = None  # type: Optional[str]
        self.decision_cooldown = random.randint(3, 10)
        self.thought_cooldown = random.randint(6, 18)
        self.plan: list[str] = []
        self.mood = random.randint(58, 82)
        self.hunger = random.randint(12, 35)
        self.energy = random.randint(62, 92)
        self.fun = random.randint(45, 78)
        self.social = random.randint(35, 72)
        self.relationships: dict[str, int] = {}
        self.thought = self.fallback_thought()
        self.thought_time = time.time()

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
            "memories": self.memories[-10:],
            "memories_count": len(self.memories),
            "mood": self.mood,
            "hunger": self.hunger,
            "energy": self.energy,
            "fun": self.fun,
            "social": self.social,
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
            "decision_cooldown": self.decision_cooldown,
            "thought_cooldown": self.thought_cooldown,
            "thought": self.thought,
            "thought_time": self.thought_time,
        })
        return data

    def apply_save_dict(self, data: dict):
        self.x = float(data.get("x", self.x))
        self.y = float(data.get("y", self.y))
        self.target_location = data.get("target_location", self.target_location)
        self.current_location = data.get("current_location", self.current_location)
        self.status = "在镇上闲逛"
        self.chat_bubble = data.get("chat_bubble", "")
        self.chat_bubble_time = float(data.get("chat_bubble_time", 0))
        self.memories = list(data.get("memories", self.memories))[-30:]
        self.decision_cooldown = int(data.get("decision_cooldown", self.decision_cooldown))
        self.thought_cooldown = int(data.get("thought_cooldown", self.thought_cooldown))
        self.mood = int(data.get("mood", self.mood))
        self.hunger = int(data.get("hunger", self.hunger))
        self.energy = int(data.get("energy", self.energy))
        self.fun = int(data.get("fun", self.fun))
        self.social = int(data.get("social", self.social))
        self.relationships = {str(k): int(v) for k, v in data.get("relationships", {}).items()}
        self.thought = data.get("thought") or self.fallback_thought()
        self.thought_time = float(data.get("thought_time", time.time()))

    def add_memory(self, mem: str):
        self.memories.append(mem)
        if len(self.memories) > 30:
            self.memories = self.memories[-30:]

    def set_bubble(self, text: str):
        self.chat_bubble = text[:60]
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
        recent = "; ".join(self.memories[-3:])
        loc_label = LOCATIONS.get(self.current_location, {}).get("label", "某处")
        needs = f"心情{self.mood}, 饥饿{self.hunger}, 精力{self.energy}, 娱乐{self.fun}, 社交{self.social}"
        relation_hint = f"刚刚互动对象：{other_name}\n" if other_name else ""
        prompt = (
            f"你是{self.name}（{self.occupation}），性格：{self.personality}。\n"
            f"现在时间：{game_time}，地点：{loc_label}。{relation_hint}"
            f"需求状态：{needs}。\n"
            f"近期记忆：{recent}\n"
            f"写一句中文内心活动，像游戏角色的想法，1句，15-35字，不要加引号，不要说出口："
        )
        thought = await ollama.generate(prompt, model=self.model, max_tokens=50)
        return thought.strip() or self.fallback_thought(other_name)
    async def decide_next_location(self, game_time: str) -> str:
        need_choice = self.choose_need_location(game_time)
        if random.random() < 0.65:
            return need_choice

        recent_mems = "; ".join(self.memories[-5:])
        loc_labels = ", ".join([v["label"] for v in LOCATIONS.values()])
        loc_keys = ", ".join(LOCATIONS.keys())

        prompt = (
            f"你是{self.name}，{self.occupation}。性格：{self.personality}\n"
            f"现在时间：{game_time}。你在{LOCATIONS[self.current_location]['label']}。\n"
            f"近期记忆：{recent_mems}\n"
            f"可去的地方（用英文key回答）：{loc_keys}\n"
            f"根据你的性格和时间，你最想去哪里？只回答一个英文key，不要其他内容。"
        )

        result = await ollama.generate(prompt, model=self.model, max_tokens=15)
        result = result.strip().lower().split()[0] if result.strip() else ""
        # remove punctuation
        result = "".join(c for c in result if c.isalnum() or c == "_")
        if result in LOCATIONS:
            return result
        return need_choice

    async def generate_reply(self, other_name: str, other_said: str, other_personality: str) -> str:
        recent = "; ".join(self.memories[-3:])
        prompt = (
            f"你是{self.name}（{self.occupation}），性格：{self.personality}。\n"
            f"你和{other_name}在{LOCATIONS.get(self.current_location, {}).get('label','某处')}相遇。\n"
            f"近期记忆：{recent}\n"
            f'{other_name}说："{other_said}"\n'
            f"请用中文简短回复（1-2句话，不超过50字，不要加引号）："
        )
        reply = await ollama.generate(prompt, model=self.model, max_tokens=60)
        reply = reply.strip()
        if reply:
            return reply
        choices = [
            f"{other_name}，这个主意不错。",
            "我刚好也在想这件事。",
            "下次一起去广场看看吧。",
            "听起来很有意思！",
        ]
        return random.choice(choices)

    async def generate_greeting(self, other_name: str, location_label: str) -> str:
        prompt = (
            f"你是{self.name}（{self.occupation}），性格：{self.personality}。\n"
            f"你在{location_label}遇到了{other_name}。\n"
            f"说一句简短的中文问候或开场白（1句话，不超过30字，不要引号）："
        )
        greeting = await ollama.generate(prompt, model=self.model, max_tokens=40)
        greeting = greeting.strip()
        if greeting:
            return greeting
        return random.choice([
            f"{other_name}，今天过得怎么样？",
            f"好巧啊，{other_name}！",
            "这里气氛真不错。",
            "要不要一起逛逛？",
        ])

    async def generate_action_status(self, location_label: str) -> str:
        prompt = (
            f"你是{self.name}（{self.occupation}）在{location_label}。性格：{self.personality}。\n"
            f'用中文描述你正在做什么（5-10个字，如"喝咖啡看报纸"）：'
        )
        status = await ollama.generate(prompt, model=self.model, max_tokens=20)
        return status.strip() or self.fallback_status(location_label)

    async def generate_user_reply(self, user_text: str, history: Optional[list] = None) -> str:
        """以角色身份回复正在与之聊天的玩家（访客）。支持多轮上下文。"""
        loc_label = LOCATIONS.get(self.current_location, {}).get("label", "某处")
        recent = "; ".join(self.memories[-3:])
        system = (
            f"你是{self.name}，{self.occupation}。性格：{self.personality}。\n"
            f"你现在在{loc_label}。近期记忆：{recent}。\n"
            f"一位访客正在和你聊天。请始终以{self.name}的身份、用口语化的中文回复，"
            f"符合你的性格，1-2句话，不超过50字。不要加引号，不要写旁白或动作描述。"
        )
        messages = [{"role": "system", "content": system}]
        for h in (history or [])[-6:]:
            role = "user" if h.get("role") == "user" else "assistant"
            content = str(h.get("text", "")).strip()[:200]
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": str(user_text).strip()[:200]})
        reply = await ollama.chat(messages, model=self.model, max_tokens=90)
        reply = " ".join((reply or "").strip().split())
        if reply:
            return reply[:80]
        return random.choice([
            "嗯，我在听呢。",
            "这个想法挺有意思的。",
            "你说得对，我也这么觉得。",
            "很高兴你来找我聊天！",
        ])
