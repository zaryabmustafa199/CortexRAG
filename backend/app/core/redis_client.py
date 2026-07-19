"""
app/core/redis_client.py
------------------------
Centralised Redis client with production-safe configuration.

Configuration enforced (§5.5):
  - ExponentialBackoff retry with cap=10s, initial=0.5s, 5 retries
  - retry_on_timeout=True
  - socket_connect_timeout=5.0s
  - socket_timeout=5.0s
  - max_connections=50
  - decode_responses=True (strings, not bytes)
"""

from __future__ import annotations

from redis.backoff import ExponentialBackoff
from redis.client import Redis
from redis.retry import Retry

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger()

_retry = Retry(
    ExponentialBackoff(cap=10, base=2),
    retries=5,
)

redis_client: Redis = Redis.from_url(
    settings.REDIS_URL,
    retry=_retry,
    retry_on_timeout=True,
    socket_connect_timeout=5.0,
    socket_timeout=5.0,
    max_connections=50,
    decode_responses=True,
)

logger.info("redis_client_initialised", url=settings.REDIS_URL)
