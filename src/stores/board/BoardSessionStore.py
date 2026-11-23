import json
import redis.asyncio as redis


class BoardSessionStore:

    def __init__(self, redis_url: str, ttl: int):
        self.r = redis.from_url(redis_url, decode_responses=True)
        self.ttl = ttl

    async def add_board(self, session_id: str, text: str):
        key = f"board:{session_id}:boards"
        await self.r.rpush(key, text)
        await self.r.expire(key, self.ttl)

    async def get_boards(self, session_id: str):
        return await self.r.lrange(f"board:{session_id}:boards", 0, -1)

    async def add_message(self, session_id: str, role: str, content: str):
        key = f"board:{session_id}:chat"
        await self.r.rpush(key, json.dumps({"role": role, "content": content}))
        await self.r.expire(key, self.ttl)

    async def get_history(self, session_id: str, limit: int = 10):
        items = await self.r.lrange(f"board:{session_id}:chat", -limit, -1)
        return [json.loads(i) for i in items]