from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limiter, limit: int, window: int):
        super().__init__(app)
        self.limiter = limiter
        self.limit = limit
        self.window = window

    async def dispatch(self, request: Request, call_next):
        key = f"ratelimit:{request.client.host}"
        try:
            allowed, headers = self.limiter.is_allowed(key, self.limit, self.window)
        except Exception:
            return await call_next(request)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"error": "Too many requests"},
                headers=headers,
            )

        response = await call_next(request)
        for k, v in headers.items():
            response.headers[k] = v
        return response
