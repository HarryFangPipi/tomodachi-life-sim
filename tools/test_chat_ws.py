import asyncio
import json
import sys

import websockets


async def main() -> int:
    agent_id = sys.argv[1] if len(sys.argv) > 1 else "eve"
    text = sys.argv[2] if len(sys.argv) > 2 else "你好，能听见我吗？"
    ws = await websockets.connect("ws://127.0.0.1:8001/ws")
    await ws.recv()
    await ws.send(json.dumps({
        "type": "user_chat",
        "agent_id": agent_id,
        "text": text,
        "history": [],
    }, ensure_ascii=False))
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=180))
        if msg.get("type") == "chat_reply":
            print(json.dumps(msg.get("data"), ensure_ascii=True))
            break
    await ws.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
