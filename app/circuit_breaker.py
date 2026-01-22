"""Circuit breaker implementation for external API resilience."""

from functools import wraps
from typing import Any, Callable, TypeVar

import pybreaker

from app.config import config
from app.logging_config import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class CircuitBreakerListener(pybreaker.CircuitBreakerListener):
    """Listener for circuit breaker state changes."""

    def state_change(
        self, cb: pybreaker.CircuitBreaker, old_state: Any, new_state: Any
    ) -> None:
        """Log state changes."""
        logger.warning(
            "circuit_breaker_state_change",
            breaker_name=cb.name,
            old_state=str(old_state),
            new_state=str(new_state),
        )

    def failure(self, cb: pybreaker.CircuitBreaker, exc: Exception) -> None:
        """Log failures."""
        logger.warning(
            "circuit_breaker_failure",
            breaker_name=cb.name,
            failure_count=cb.fail_counter,
            error=str(exc),
        )

    def success(self, cb: pybreaker.CircuitBreaker) -> None:
        """Log successful calls after failures."""
        if cb.fail_counter > 0:
            logger.info(
                "circuit_breaker_success_after_failure",
                breaker_name=cb.name,
            )


# Create circuit breaker for weather API
weather_api_breaker = pybreaker.CircuitBreaker(
    name="weather_api",
    fail_max=config.CIRCUIT_BREAKER_FAIL_MAX,
    reset_timeout=config.CIRCUIT_BREAKER_RESET_TIMEOUT,
    listeners=[CircuitBreakerListener()],
)


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""

    def __init__(self, breaker_name: str) -> None:
        self.breaker_name = breaker_name
        super().__init__(f"Circuit breaker '{breaker_name}' is open")


def with_circuit_breaker(breaker: pybreaker.CircuitBreaker) -> Callable[[F], F]:
    """Decorator to wrap a function with circuit breaker protection.

    Args:
        breaker: The circuit breaker instance to use.

    Returns:
        Decorated function.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return breaker.call(func, *args, **kwargs)
            except pybreaker.CircuitBreakerError:
                raise CircuitBreakerOpenError(breaker.name)

        return wrapper  # type: ignore

    return decorator


def get_breaker_status(breaker: pybreaker.CircuitBreaker) -> dict[str, Any]:
    """Get the current status of a circuit breaker.

    Args:
        breaker: The circuit breaker to check.

    Returns:
        Dictionary with breaker status information.
    """
    return {
        "name": breaker.name,
        "state": str(breaker.current_state),
        "fail_counter": breaker.fail_counter,
        "fail_max": breaker.fail_max,
        "reset_timeout": breaker.reset_timeout,
    }
