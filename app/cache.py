"""Redis caching layer."""

import json
from typing import Any

import redis

from app.config import config
from app.logging_config import get_logger

logger = get_logger(__name__)


class CacheError(Exception):
    """Exception raised for cache-related errors."""

    pass


class RedisCache:
    """Redis-based cache implementation."""

    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        """Initialize Redis cache.

        Args:
            redis_client: Optional Redis client for dependency injection (testing).
        """
        self._client = redis_client
        self._connected = False

    @property
    def client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._client = redis.Redis(
                host=config.REDIS_HOST,
                port=config.REDIS_PORT,
                db=config.REDIS_DB,
                password=config.REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        return self._client

    def _build_key(self, prefix: str, identifier: str) -> str:
        """Build a cache key with prefix."""
        return f"weather_proxy:{prefix}:{identifier.lower()}"

    def get(self, prefix: str, identifier: str) -> dict[str, Any] | None:
        """Get a value from cache.

        Args:
            prefix: Key prefix (e.g., 'weather', 'geocode').
            identifier: Unique identifier (e.g., city name).

        Returns:
            Cached data or None if not found/expired.
        """
        key = self._build_key(prefix, identifier)
        try:
            data = self.client.get(key)
            if data:
                logger.info("cache_hit", key=key)
                result: dict[str, Any] = json.loads(data)
                return result
            logger.info("cache_miss", key=key)
            return None
        except redis.RedisError as e:
            logger.warning("cache_get_error", key=key, error=str(e))
            return None
        except json.JSONDecodeError as e:
            logger.warning("cache_decode_error", key=key, error=str(e))
            return None

    def set(
        self, prefix: str, identifier: str, data: dict[str, Any], ttl: int | None = None
    ) -> bool:
        """Set a value in cache with TTL.

        Args:
            prefix: Key prefix.
            identifier: Unique identifier.
            data: Data to cache.
            ttl: Time-to-live in seconds (defaults to config value).

        Returns:
            True if successful, False otherwise.
        """
        key = self._build_key(prefix, identifier)
        ttl = ttl or config.CACHE_TTL_SECONDS
        try:
            self.client.setex(key, ttl, json.dumps(data))
            logger.info("cache_set", key=key, ttl=ttl)
            return True
        except (redis.RedisError, TypeError) as e:
            logger.warning("cache_set_error", key=key, error=str(e))
            return False

    def delete(self, prefix: str, identifier: str) -> bool:
        """Delete a value from cache.

        Args:
            prefix: Key prefix.
            identifier: Unique identifier.

        Returns:
            True if deleted, False otherwise.
        """
        key = self._build_key(prefix, identifier)
        try:
            self.client.delete(key)
            logger.info("cache_delete", key=key)
            return True
        except redis.RedisError as e:
            logger.warning("cache_delete_error", key=key, error=str(e))
            return False

    def health_check(self) -> bool:
        """Check if Redis is healthy.

        Returns:
            True if Redis is responsive, False otherwise.
        """
        try:
            self.client.ping()
            return True
        except redis.RedisError:
            return False


# Global cache instance
cache = RedisCache()
