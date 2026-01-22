"""Transaction history storage for analytics."""

import json
from dataclasses import asdict, dataclass
from typing import Any

import redis

from app.config import config
from app.logging_config import get_logger

logger = get_logger(__name__)

# Maximum number of transactions to keep in history
MAX_HISTORY_SIZE = 100
HISTORY_KEY = "weather_proxy:transaction_history"


@dataclass
class Transaction:
    """Represents a single API transaction."""

    timestamp: float
    city: str
    success: bool
    cached: bool
    response_time_ms: float
    status_code: int
    error: str | None = None
    temperature: float | None = None
    country: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transaction":
        """Create from dictionary."""
        return cls(**data)


class TransactionHistory:
    """Stores and retrieves transaction history using Redis."""

    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        """Initialize transaction history.

        Args:
            redis_client: Optional Redis client for dependency injection.
        """
        self._client = redis_client

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

    def add_transaction(self, transaction: Transaction) -> bool:
        """Add a transaction to history.

        Args:
            transaction: The transaction to store.

        Returns:
            True if successful, False otherwise.
        """
        try:
            # Add to list (newest first)
            self.client.lpush(HISTORY_KEY, json.dumps(transaction.to_dict()))
            # Trim to max size
            self.client.ltrim(HISTORY_KEY, 0, MAX_HISTORY_SIZE - 1)
            logger.info(
                "transaction_recorded",
                city=transaction.city,
                cached=transaction.cached,
                response_time_ms=transaction.response_time_ms,
            )
            return True
        except redis.RedisError as e:
            logger.warning("transaction_record_error", error=str(e))
            return False

    def get_history(self, limit: int = 50) -> list[Transaction]:
        """Get recent transaction history.

        Args:
            limit: Maximum number of transactions to return.

        Returns:
            List of transactions, newest first.
        """
        try:
            data = self.client.lrange(HISTORY_KEY, 0, limit - 1)
            transactions = []
            for item in data:
                try:
                    tx_dict = json.loads(item)
                    transactions.append(Transaction.from_dict(tx_dict))
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning("transaction_parse_error", error=str(e))
            return transactions
        except redis.RedisError as e:
            logger.warning("transaction_history_error", error=str(e))
            return []

    def get_statistics(self) -> dict[str, Any]:
        """Get aggregated statistics from transaction history.

        Returns:
            Dictionary with statistics.
        """
        transactions = self.get_history(MAX_HISTORY_SIZE)

        if not transactions:
            return {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "cache_hits": 0,
                "cache_misses": 0,
                "cache_hit_rate": 0.0,
                "avg_response_time_ms": 0.0,
                "avg_cached_response_time_ms": 0.0,
                "avg_fresh_response_time_ms": 0.0,
                "unique_cities": 0,
            }

        total = len(transactions)
        successful = sum(1 for t in transactions if t.success)
        failed = total - successful
        cache_hits = sum(1 for t in transactions if t.cached and t.success)
        cache_misses = sum(1 for t in transactions if not t.cached and t.success)

        all_times = [t.response_time_ms for t in transactions]
        cached_times = [t.response_time_ms for t in transactions if t.cached]
        fresh_times = [t.response_time_ms for t in transactions if not t.cached]

        unique_cities = len(set(t.city.lower() for t in transactions))

        return {
            "total_requests": total,
            "successful_requests": successful,
            "failed_requests": failed,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "cache_hit_rate": (
                round(cache_hits / successful * 100, 1) if successful > 0 else 0.0
            ),
            "avg_response_time_ms": (
                round(sum(all_times) / len(all_times), 1) if all_times else 0.0
            ),
            "avg_cached_response_time_ms": (
                round(sum(cached_times) / len(cached_times), 1) if cached_times else 0.0
            ),
            "avg_fresh_response_time_ms": (
                round(sum(fresh_times) / len(fresh_times), 1) if fresh_times else 0.0
            ),
            "unique_cities": unique_cities,
        }

    def clear_history(self) -> bool:
        """Clear all transaction history.

        Returns:
            True if successful, False otherwise.
        """
        try:
            self.client.delete(HISTORY_KEY)
            logger.info("transaction_history_cleared")
            return True
        except redis.RedisError as e:
            logger.warning("transaction_clear_error", error=str(e))
            return False


# Global instance
transaction_history = TransactionHistory()
