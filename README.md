# RateGuardian v2

Async sliding window rate limiter for Python APIs. Redis-backed, FastAPI-ready.

## What changed in v2

v1 used the Upstash HTTP client which is synchronous — in async apps you had to wrap every call in `run_in_executor` to avoid blocking the event loop. v2 is fully async and accepts your existing `redis.asyncio` client so there's no second connection or thread overhead.

v1 is kept as `RateGuardianSync` for backward compatibility (requires `pip install rate-guardian[sync]`).

### v2.0 also fixes

- **Race condition** — the old pipeline was non-transactional. Under concurrent load, multiple requests could read the same count and both slip through. v2 uses an atomic Lua script: evict, count, and conditionally add all happen server-side in a single round-trip.
- **Blocked requests polluting Redis** — the old pipeline always called `ZADD` even when the request was rejected. Blocked requests now write nothing to Redis.
- **`X-RateLimit-Reset`** — now returns a Unix epoch timestamp (when the window expires), not the raw window duration. `Retry-After` is still the number of seconds to wait.

## Install

```bash
pip install rate-guardian
```

## Usage

```python
import redis.asyncio as aioredis
from rate_guardian import RateGuardian

client = aioredis.from_url("redis://localhost:6379", decode_responses=True)
limiter = RateGuardian(redis=client, prefix="myapp")

# returns (allowed, headers)
allowed, headers = await limiter.is_allowed("user:123", limit=10, window=60)

# or raise on exceeded
await limiter.check("user:123", limit=10, window=60)  # raises RateLimitExceeded
```

## FastAPI — three ways to use it

**1. Global middleware**
```python
from rate_guardian import RateLimitMiddleware

# Initialize at module level — the pool connects lazily, no event loop needed.
# Do NOT initialize inside lifespan; add_middleware runs before lifespan starts.
client = aioredis.from_url("redis://localhost:6379", decode_responses=True)
limiter = RateGuardian(redis=client, prefix="myapp")

app.add_middleware(RateLimitMiddleware, limiter=limiter, limit=100, window=60)
```

**2. Per-route decorator**
```python
from rate_guardian import rate_limit

@app.get("/search")
@rate_limit(limiter, limit=20, window=60)
async def search(request: Request, q: str):
    ...
```

**3. Manual check — full control over the key**
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

Uses Redis sorted sets with an atomic Lua script. Each allowed request is stored as a member with the current timestamp (ms) as its score. On every check, expired entries outside the window are removed server-side before counting. Blocked requests are never written.

```lua
ZREMRANGEBYSCORE key 0 (now - window_ms)  -- evict old entries
count = ZCARD key                          -- count current requests
if count < limit then
    ZADD key now request_id               -- record only if allowed
    EXPIRE key window
    return {count, 1}                     -- allowed
else
    return {count, 0}                     -- blocked — nothing written
end
```

All operations run atomically on the Redis server — one round trip per check, no race conditions.

## Response headers

Every call returns standard rate limit headers:

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Max requests allowed in the window |
| `X-RateLimit-Remaining` | Requests left before hitting the limit |
| `X-RateLimit-Reset` | Unix timestamp when the current window expires |
| `Retry-After` | Seconds to wait before retrying (only on 429) |

## Running tests

```bash
# with Docker — spins up Redis automatically
docker compose up --abort-on-container-exit

# locally — needs Redis on port 6379
pytest tests/ -v
```

## v1 (sync) — backward compatibility

Requires the optional `sync` extra (Upstash HTTP client):

```bash
pip install rate-guardian[sync]
```

```python
from rate_guardian import RateGuardianSync

limiter = RateGuardianSync(redis_url="...", redis_token="...", prefix="myapp")
allowed, headers = limiter.is_allowed("user:123", limit=10, window=60)
```
