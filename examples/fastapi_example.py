from fastapi import FastAPI
from rateguard.limiter import RateGuard
from rateguard.middleware import RateLimitMiddleware

app = FastAPI()

REDIS_URL = "your_redis_url"
REDIS_TOKEN = "your_redis_token"

limiter = RateGuard(REDIS_URL, REDIS_TOKEN)

app.middleware("http")(RateLimitMiddleware(limiter, limit=10, window=60))


@app.get("/")
async def home():
    return {"message": "API is protected by RateGuard"}