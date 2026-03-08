from functools import wraps
from fastapi import Request
from fastapi.responses import JSONResponse


def rate_limit(limiter, limit: int, window: int):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get("request")
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request:
                key = f"ratelimit:{func.__name__}:{request.client.host}"
                try:
                    allowed, headers = limiter.is_allowed(key, limit, window)
                    if not allowed:
                        return JSONResponse(
                            status_code=429,
                            content={"error": "Too many requests"},
                            headers=headers,
                        )
                except Exception:
                    pass

            return await func(*args, **kwargs)
        return wrapper
    return decorator
