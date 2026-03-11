"""
Shared pytest fixtures for RateGuardian tests.

pytest-asyncio is configured in pyproject.toml:
  [tool.pytest.ini_options]
  asyncio_mode = "auto"

All async test functions and fixtures are picked up automatically —
no @pytest.mark.asyncio needed.
"""

import os
import pytest
import redis.asyncio as aioredis

from rate_guardian import RateGuardian

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


@pytest.fixture
async def redis_client():
    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
async def limiter(redis_client):
    return RateGuardian(redis=redis_client, prefix="test")
