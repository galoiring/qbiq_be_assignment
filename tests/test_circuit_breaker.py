"""Unit tests for the circuit breaker module."""

import pybreaker
import pytest

from app.circuit_breaker import (
    CircuitBreakerOpenError,
    get_breaker_status,
    with_circuit_breaker,
)


class TestCircuitBreaker:
    """Tests for circuit breaker functionality."""

    def test_get_breaker_status(self):
        """Test getting circuit breaker status."""
        breaker = pybreaker.CircuitBreaker(
            name="test_breaker",
            fail_max=3,
            reset_timeout=10,
        )

        status = get_breaker_status(breaker)

        assert status["name"] == "test_breaker"
        assert status["fail_max"] == 3
        assert status["reset_timeout"] == 10
        assert status["fail_counter"] == 0
        assert "closed" in status["state"].lower()

    def test_circuit_breaker_opens_after_failures(self):
        """Test that circuit breaker opens after max failures."""
        breaker = pybreaker.CircuitBreaker(
            name="test_breaker",
            fail_max=2,
            reset_timeout=60,
        )

        @with_circuit_breaker(breaker)
        def failing_function():
            raise ValueError("Test error")

        # Cause failures to open the circuit
        # The circuit breaker opens on the last failure
        for _ in range(2):
            with pytest.raises((ValueError, CircuitBreakerOpenError)):
                failing_function()

        # Next call should raise CircuitBreakerOpenError
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            failing_function()

        assert exc_info.value.breaker_name == "test_breaker"

    def test_circuit_breaker_allows_success(self):
        """Test that circuit breaker allows successful calls."""
        breaker = pybreaker.CircuitBreaker(
            name="test_breaker",
            fail_max=5,
            reset_timeout=60,
        )

        @with_circuit_breaker(breaker)
        def success_function():
            return "success"

        result = success_function()
        assert result == "success"

    def test_circuit_breaker_passes_arguments(self):
        """Test that arguments are passed through circuit breaker."""
        breaker = pybreaker.CircuitBreaker(
            name="test_breaker",
            fail_max=5,
            reset_timeout=60,
        )

        @with_circuit_breaker(breaker)
        def function_with_args(a, b, keyword=None):
            return f"{a}-{b}-{keyword}"

        result = function_with_args("x", "y", keyword="z")
        assert result == "x-y-z"


class TestCircuitBreakerOpenError:
    """Tests for CircuitBreakerOpenError exception."""

    def test_error_message_contains_breaker_name(self):
        """Test that error message includes breaker name."""
        error = CircuitBreakerOpenError("my_breaker")

        assert error.breaker_name == "my_breaker"
        assert "my_breaker" in str(error)
        assert "open" in str(error).lower()
