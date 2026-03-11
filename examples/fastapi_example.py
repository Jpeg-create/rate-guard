"""
RateGuardian v2 — FastAPI usage examples

Three ways to use it:
  1. Middleware — global limit on every route
  2. Decorator  — per-route limit
  3. Manual     — inline check, full control over the key

Note on setup: aioredis.from_url() creates a connection pool that connects
lazily on first use, so it is safe to call at module level. Use lifespan
only for graceful shutdown (aclose).
"""

import redis.asyncio as aioredis
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request

from rate_guardian import RateGuardian, RateLimitExceeded, RateLimitMiddleware, rate_limit

# ---------------------------------------------------------------------------
# Initialize at module level — the pool connects lazily, no event loop needed.
# This also ensures the middleware receives a real limiter, not None.
# ---------------------------------------------------------------------------
_redis_client = aioredis.from_url("redis://localhost:6379", decode_responses=True)
limiter = RateGuardian(redis=_redis_client, prefix="myapp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # nothing to set up — pool connects on first request
    yield
    # graceful shutdown: drain in-flight connections
    await _redis_client.aclose()


app = FastAPI(lifespan=lifespan)

# option 1: global middleware — applied to every incoming request
app.add_middleware(RateLimitMiddleware, limiter=limiter, limit=200, window=60)


# option 2: decorator — each route has its own bucket keyed by route + IP
@app.get("/search")
@rate_limit(limiter, limit=20, window=60)
async def search(request: Request, q: str):
    return {"results": []}


# option 3: manual — useful when the key is determined by request data
@app.post("/shorten")
async def shorten(request: Request, url: str, tenant_id: int):
    try:
        await limiter.check(f"tenant:{tenant_id}", limit=10, window=60)
    except RateLimitExceeded as e:
        raise HTTPException(status_code=429, detail="Rate limit exceeded", headers=e.headers)

    return {"short_url": "https://short.ly/abc123"}
