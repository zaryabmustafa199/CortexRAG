"""
app/core/rate_limiter.py
------------------------
Rate limiting using Redis.
"""
from __future__ import annotations

import time

import structlog

from app.core.exceptions import RateLimitException
from app.core.redis_client import redis_client

logger = structlog.get_logger()


def check_rate_limit(key: str, limit: int = 60, window: int = 60) -> None:
    """
    Check rate limit using a fixed window in Redis.
    Raises RateLimitException if the limit is exceeded.
    
    Fails open on Redis connection issues.
    """
    current_bucket = int(time.time() // window)
    redis_key = f"ratelimit:{key}:{current_bucket}"

    try:
        count = int(redis_client.incr(redis_key))  # type: ignore[arg-type]
        if count == 1:
            redis_client.expire(redis_key, window)
    except Exception as exc:
        logger.error("rate_limiter_redis_error", key=key, error=str(exc))
        return

    if count > limit:
        logger.warning("rate_limit_exceeded", key=key, count=count, limit=limit)
        raise RateLimitException(
            message=f"Rate limit exceeded. Maximum {limit} requests per {window} seconds."
        )
