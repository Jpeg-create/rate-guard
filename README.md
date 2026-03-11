# RateGuardian v2

A sliding window rate limiter for Python APIs. Built on Redis, works great with FastAPI.

## What's new in v2

v1 was built on the Upstash HTTP client, which is synchronous. Every call in an async app had to be wrapped in `run_in_executor` to avoid blocking. v2 drops that entirely and works directly with `redis.asyncio`, so there's no extra thread overhead or second connection to manage.

v2 also ships with a few bug fixes:

- The old pipeline was non-transactional, so under concurrent load two requests could read the same count and both get through. v2 uses a Lua script that runs atomically on the Redis server, so that can't happen.
- The old pipeline always wrote to Redis even when a request was blocked. Blocked requests no longer write anything.
- `X-RateLimit-Reset` now returns a Unix timestamp instead of the raw window duration.

v1 is still available as `RateGuardianSync` if you need it.

## Install

```bash
pip install rate-guardian
```

## Basic usage

```python
import redis.asyncio as aioredis
from rate_guardian import RateGuardian

client = aioredis.from_url("redis://localhost:6379", decode_responses=True)
limiter = RateGuardian(redis=client, prefix="myapp")

# returns (allowed, headers)
allowed, headers = await limiter.is_allowed("user:123", limit=10, window=60)

# raises RateLimitExceeded if the limit is hit
await limiter.check("user:123", limit=10, window=60)
```

## Using with FastAPI

**Global middleware** -- applies to every request, keyed by IP:
```python
from rate_guardian import RateLimitMiddleware

# Initialize at module level, not inside lifespan.
# add_middleware runs at startup before lifespan begins.
client = aioredis.from_url("redis://localhost:6379", decode_responses=True)
limiter = RateGuardian(redis=client, prefix="myapp")

app.add_middleware(RateLimitMiddleware, limiter=limiter, limit=100, window=60)
```

**Per-route decorator** -- each route gets its own bucket:
```python
from rate_guardian import rate_limit

@app.get("/search")
@rate_limit(limiter, limit=20, window=60)
async def search(request: Request, q: str):
    ...
```

**Manual check** -- useful when the key depends on request data:
```python
from rate_guardian import RateLimitExceeded

@app.post("/shorten")
async def shorten(tenant_id: int):
    try:
        await limiter.check(f"tenant:{tenant_id}", limit=10, window=60)
    except RateLimitExceeded as e:
        raise HTTPException(status_code=429, headers=e.headers)
```

## How it works

Each allowed request gets stored in a Redis sorted set with its timestamp as the score. On every check, entries older than the window get evicted, the remaining count is compared against the limit, and the request is either recorded or rejected. All of this happens in a single Lua script so it's atomic.

```lua
ZREMRANGEBYSCORE key 0 (now - window_ms)  -- drop expired entries
count = ZCARD key                          -- how many are left
if count < limit then
    ZADD key now request_id               -- record it
    EXPIRE key window
    return {count, 1}                     -- allowed
else
    return {count, 0}                     -- blocked, nothing written
end
```

## Response headers

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Max requests allowed in the window |
| `X-RateLimit-Remaining` | Requests left in the current window |
| `X-RateLimit-Reset` | Unix timestamp of when the window resets |
| `Retry-After` | Seconds to wait before retrying (429 only) |

## Running tests

```bash
# locally, with Redis on port 6379
pytest tests/ -v

# with Docker
docker compose up --abort-on-container-exit
```

## v1 compatibility

If you need the old synchronous Upstash-based limiter:

```bash
pip install rate-guardian[sync]
```

```python
from rate_guardian import RateGuardianSync

limiter = RateGuardianSync(redis_url="...", redis_token="...", prefix="myapp")
allowed, headers = limiter.is_allowed("user:123", limit=10, window=60)
```