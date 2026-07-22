"""
Dynamic configuration manager.

Stores pipeline tuning parameters in a Redis hash so they can be changed at runtime without redeploying. It makes the platform configurable per workspace — a compliance client can enable groundedness checks while a cost-sensitive client runs lean.

Parameters are stored in Redis as a hash:
    system:tuning:parameters → {
        "default_llm_provider": "ollama",
        "max_chunk_tokens": "500",
        ...
    }

Why Redis and not just the database?
- Reads are ~0.1ms (Redis) vs ~2ms (Postgres) — these values are read
  on every single query and ingestion job
- No connection pool pressure on Postgres
- Can be invalidated instantly
"""

import json
import logging
from functools import lru_cache
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Redis key for the tuning parameters hash
REDIS_KEY = "system:tuning:parameters"

# Default configuration values
# These are used if no value has been set in Redis
DEFAULT_CONFIG = {
    "default_llm_provider": "ollama",
    "max_chunk_tokens": 500,
    "chunk_overlap_tokens": 50,
    "rrf_k_constant": 60,
    "top_k_vector": 20,
    "top_k_keyword": 20,
    "top_k_final": 10,
    "context_token_limit": 8000,
    "no_answer_threshold": 0.50,
}


class ConfigManager:
    """
    Reads and writes dynamic pipeline configuration from Redis.
    
    Usage:
        manager = ConfigManager(redis_client)
        provider = await manager.get("default_llm_provider")  # → "ollama"
        await manager.set("default_llm_provider", "openai")
    """

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

    async def get(self, key: str) -> Any:
        """
        Get a single config value. Falls back to DEFAULT_CONFIG.
        """
        value = await self.redis.hget(REDIS_KEY, key)
        if value is not None:
            # Try to parse as JSON (handles numbers, booleans, lists)
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        # Fall back to defaults
        return DEFAULT_CONFIG.get(key)

    async def set(self, key: str, value: Any) -> None:
        """
        Set a single config value.
        """
        await self.redis.hset(REDIS_KEY, key, json.dumps(value))

    async def get_all(self) -> dict:
        """
        Get all config values, merged with defaults.
        """
        stored = await self.redis.hgetall(REDIS_KEY)

        # Start with defaults, override with stored values
        config = dict(DEFAULT_CONFIG)
        for k, v in stored.items():
            try:
                config[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                config[k] = v

        return config

    async def delete(self, key: str) -> None:
        """
        Delete a config value (reverts to default).
        """
        await self.redis.hdel(REDIS_KEY, key)