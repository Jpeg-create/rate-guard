import time
import uuid
from typing import Tuple

import redis.asyncio as aioredis

# ---------------------------------------------------------------------------
# Lua script — runs atomically on the Redis server (no round-trip races).
#
# Evicts expired entries, counts what remains, and ONLY records this request
# if it is within the limit.  Blocked requests are never written to Redis.
#
# Returns [count_before_this_request, allowed]  (allowed: 1 = yes, 0 = no)
# ---------------------------------------------------------------------------
_LUA_SCRIPT = """
local key    = KEYS[1]
local now    = tonumber(ARGV[1])
local oldest = tonumber(ARGV[2])
local limit  = tonumber(ARGV[3])
local window = tonumber(ARGV[4])
local req_id = ARGV[5]

redis.call('ZREMRANGEBYSCORE', key, 0, oldest)
local count = tonumber(redis.call('ZCARD', key))

if count < limit then
    redis.call('ZADD', key, now, req_id)
    redis.call('EXPIRE', key, window)
    return {count, 1}
else
    return {count, 0}
end
"""


class RateLimitExceeded(Exception):
    """Raised by RateGuardian.check() when the rate limit is exceeded."""

    def __init__(self, headers: dict):
        self.headers = headers
        super().__init__("Rate limit exceeded")


class RateGuardian:
    """
    Async sliding window rate limiter backed by Redis.

    Accepts your existing redis.asyncio client — no second connection needed.
    Keys are namespaced by prefix so multiple apps can share one Redis instance.
    An atomic Lua script handles every check in a single round-trip with no
    race conditions and no wasted writes for blocked requests.
    """

    def __init__(self, redis: aioredis.Redis, prefix: str = "rg"):
        self._redis = redis
        self._prefix = prefix
        self._script = redis.register_script(_LUA_SCRIPT)

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    async def is_allowed(self, key: str, limit: int, window: int) -> Tuple[bool, dict]:
        """
        Check and (conditionally) record one request using a sliding window.

        Returns (allowed, headers) where headers contain X-RateLimit-* values.
        Blocked requests are NOT written to Redis — only allowed ones are.
        """
        now = int(time.time() * 1000)
        oldest = now - (window * 1000)
        request_id = str(uuid.uuid4())

        count, allowed_int = await self._script(
            keys=[self._key(key)],
            args=[now, oldest, limit, window, request_id],
        )
        count = int(count)
        allowed = bool(int(allowed_int))
        remaining = max(0, limit - count - 1) if allowed else 0
        reset_at = int(time.time()) + window  # Unix epoch when window expires

        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_at),
        }
        if not allowed:
            headers["Retry-After"] = str(window)

        return allowed, headers

    async def check(self, key: str, limit: int, window: int) -> dict:
        """
        Like is_allowed() but raises RateLimitExceeded when the limit is hit.
        Useful for route handlers that prefer catching an exception over checking a bool.
        """
        allowed, headers = await self.is_allowed(key, limit, window)
        if not allowed:
            raise RateLimitExceeded(headers)
        return headers

    async def reset(self, key: str) -> None:
        """Delete the counter for a key. Useful in tests."""
        await self._redis.delete(self._key(key))


class RateGuardianSync:
    """
    Synchronous version kept for backward compatibility with v1.
    Uses the Upstash HTTP client.

    Requires the optional 'sync' extra:
        pip install rate-guardian[sync]

    For async apps, use RateGuardian instead.
    """

    def __init__(self, redis_url: str, redis_token: str, prefix: str = "rg"):
        try:
            from upstash_redis import Redis as UpstashRedis  # lazy — optional dep
        except ImportError as exc:
            raise ImportError(
                "upstash-redis is required for RateGuardianSync. "
                "Install it with: pip install rate-guardian[sync]"
            ) from exc

        self._redis = UpstashRedis(url=redis_url, token=redis_token)
        self._prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def is_allowed(self, key: str, limit: int, window: int) -> Tuple[bool, dict]:
        now = int(time.time() * 1000)
        oldest = now - (window * 1000)
        request_id = str(uuid.uuid4())
        full_key = self._key(key)

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(full_key, 0, oldest)
        pipe.zcard(full_key)
        pipe.zadd(full_key, {request_id: now})
        pipe.expire(full_key, window)
        results = pipe.exec()

        count = results[1]
        allowed = count < limit
        remaining = max(0, limit - count - 1) if allowed else 0
        reset_at = int(time.time()) + window

        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_at),
        }
        if not allowed:
            headers["Retry-After"] = str(window)

        return allowed, headers

    def reset(self, key: str) -> None:
        """Delete the counter for a key."""
        self._redis.delete(self._key(key))
