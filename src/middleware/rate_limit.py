from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    retry_after = int(getattr(exc, "retry_after", 60))
    resp = JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMITED",
                "message": "Too many requests — please slow down.",
                "retry_after": retry_after,
            }
        },
    )
    resp.headers["RateLimit-Limit"] = "100"
    resp.headers["RateLimit-Remaining"] = "0"
    resp.headers["RateLimit-Reset"] = str(retry_after)
    resp.headers["Retry-After"] = str(retry_after)
    return resp
