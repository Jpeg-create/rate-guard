import time
import uuid
from upstash_redis import Redis


class RateGuard:
    def __init__(self, redis_url: str, redis_token: str):
        self.redis = Redis(url=redis_url, token=redis_token)

    def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, dict]:
        now = int(time.time() * 1000)
        window_ms = window * 1000
        oldest = now - window_ms
        request_id = str(uuid.uuid4())

        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, oldest)
        pipe.zcard(key)
        pipe.zadd(key, {request_id: now})
        pipe.expire(key, window)
        results = pipe.exec()

        count = results[1]
        allowed = count < limit
        remaining = max(0, limit - count - 1) if allowed else 0

        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(window),
        }

        if not allowed:
            headers["Retry-After"] = str(window)

        return allowed, headers
