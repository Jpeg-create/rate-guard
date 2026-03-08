# RateGuard

A distributed rate limiting library for Python APIs using Redis.

[![PyPI version](https://badge.fury.io/py/rate-guardian.svg)](https://pypi.org/project/rate-guardian/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

## Features

- **Sliding Window** rate limiting with millisecond precision
- **Redis Sorted Sets** — no member collisions, accurate counts
- **FastAPI Middleware** — global limits applied to every route
- **Per-route decorator** — override limits on specific endpoints
- **Distributed** — works across multiple API servers via shared Redis
- **Fail open** — if Redis is unreachable, requests are allowed through

## How It Works

RateGuard uses the **Sliding Window** algorithm with Redis Sorted Sets.

1. Each request is stored with a millisecond timestamp + unique ID
2. Requests older than the window are removed on every check
3. The remaining count determines whether the request is allowed
4. Standard rate limit headers are returned on every response
```
Client → FastAPI → RateGuard Middleware → Redis → Decision
```

## Installation
```bash
pip install rate-guardian
```

Or for local development:
```bash
pip install -r requirements.txt
```

## Quick Start

Copy `.env.example` to `.env` and fill in your [Upstash Redis](https://upstash.com) credentials.
```python
import os
from fastapi import FastAPI, Request
from rateguard import RateGuard, RateLimitMiddleware, rate_limit

app = FastAPI()
limiter = RateGuard(
    redis_url=os.environ["UPSTASH_REDIS_REST_URL"],
    redis_token=os.environ["UPSTASH_REDIS_REST_TOKEN"],
)

# Global: 10 requests per 60 seconds per IP
app.add_middleware(RateLimitMiddleware, limiter=limiter, limit=10, window=60)


@app.get("/")
async def home():
    return {"message": "API is protected by RateGuard"}


# Per-route override: tighter limit on an expensive endpoint
@app.get("/search")
@rate_limit(limiter, limit=5, window=60)
async def search(request: Request, q: str = ""):
    return {"query": q, "results": []}
```

## Run the Example
```bash
cp .env.example .env   # add your Redis credentials
uvicorn examples.fastapi_example:app --reload
```

## Response Headers

Every response includes standard rate limit headers:

| Header | Description |
| --- | --- |
| `X-RateLimit-Limit` | Maximum requests allowed in the window |
| `X-RateLimit-Remaining` | Requests remaining in the current window |
| `X-RateLimit-Reset` | Seconds until the oldest request expires |
| `Retry-After` | Seconds to wait before retrying (only on 429) |

## Running Tests
```bash
pip install pytest httpx
pytest tests/ -v
```

## License

MIT