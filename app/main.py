"""Main Flask application factory and routes."""

import signal
import sys
import time
from typing import Any

from flask import Flask, Response, jsonify, render_template, request
from prometheus_client import generate_latest

from app.cache import cache
from app.circuit_breaker import (
    CircuitBreakerOpenError,
    get_breaker_status,
    weather_api_breaker,
)
from app.history import Transaction, TransactionHistory, transaction_history
from app.logging_config import configure_logging, get_logger, set_request_id
from app.metrics import (
    http_request_duration_seconds,
    http_requests_total,
    weather_requests_total,
)
from app.weather_service import (
    CityNotFoundError,
    ExternalAPIError,
    WeatherService,
    weather_service,
)

logger = get_logger(__name__)

# Graceful shutdown flag
shutdown_flag = False


def create_app(
    weather_svc: WeatherService | None = None,
    history_store: TransactionHistory | None = None,
    json_logs: bool = True,
) -> Flask:
    """Create and configure the Flask application.

    Args:
        weather_svc: Optional weather service for dependency injection.
        history_store: Optional transaction history for dependency injection.
        json_logs: Whether to use JSON format for logs.

    Returns:
        Configured Flask application.
    """
    # Configure logging
    configure_logging(json_logs=json_logs)

    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.config["JSON_SORT_KEYS"] = False

    # Use injected services or global instances
    svc = weather_svc or weather_service
    history = history_store or transaction_history

    # Register signal handlers for graceful shutdown
    _register_signal_handlers()

    @app.before_request
    def before_request() -> None:
        """Set up request context."""
        # Set request ID from header or generate new one
        request_id = request.headers.get("X-Request-ID")
        set_request_id(request_id)
        request.start_time = time.time()  # type: ignore

        logger.info(
            "request_started",
            method=request.method,
            path=request.path,
            remote_addr=request.remote_addr,
        )

    @app.after_request
    def after_request(response: Response) -> Response:
        """Log request completion and record metrics."""
        duration = time.time() - request.start_time  # type: ignore

        # Record metrics
        endpoint = request.endpoint or "unknown"
        http_requests_total.labels(
            method=request.method,
            endpoint=endpoint,
            status_code=response.status_code,
        ).inc()

        http_request_duration_seconds.labels(
            method=request.method,
            endpoint=endpoint,
        ).observe(duration)

        logger.info(
            "request_completed",
            method=request.method,
            path=request.path,
            status_code=response.status_code,
            duration_ms=round(duration * 1000, 2),
        )

        return response

    @app.route("/")
    def index() -> str:
        """Serve the frontend page."""
        return render_template("index.html")

    @app.route("/weather")
    def get_weather() -> tuple[Response, int]:
        """Get weather data for a city.

        Query Parameters:
            city: Name of the city.

        Returns:
            JSON response with weather data or error.
        """
        city = request.args.get("city", "").strip()
        start_time = time.time()

        if not city:
            return jsonify({"error": "City parameter is required"}), 400

        try:
            data = svc.get_weather(city)
            response_time_ms = round((time.time() - start_time) * 1000, 2)

            # Record metric
            weather_requests_total.labels(
                city=city.lower(),
                cached=str(data.get("cached", False)).lower(),
                status="success",
            ).inc()

            # Record transaction history
            history.add_transaction(
                Transaction(
                    timestamp=time.time(),
                    city=data.get("city", city),
                    success=True,
                    cached=data.get("cached", False),
                    response_time_ms=response_time_ms,
                    status_code=200,
                    temperature=data.get("temperature"),
                    country=data.get("country"),
                )
            )

            return jsonify(data), 200

        except CityNotFoundError as e:
            response_time_ms = round((time.time() - start_time) * 1000, 2)
            logger.warning("city_not_found", city=city, error=str(e))
            weather_requests_total.labels(
                city=city.lower(),
                cached="false",
                status="not_found",
            ).inc()
            history.add_transaction(
                Transaction(
                    timestamp=time.time(),
                    city=city,
                    success=False,
                    cached=False,
                    response_time_ms=response_time_ms,
                    status_code=404,
                    error="City not found",
                )
            )
            return jsonify({"error": f"City '{city}' not found"}), 404

        except CircuitBreakerOpenError as e:
            response_time_ms = round((time.time() - start_time) * 1000, 2)
            logger.error("circuit_breaker_open", city=city, breaker=e.breaker_name)
            weather_requests_total.labels(
                city=city.lower(),
                cached="false",
                status="circuit_open",
            ).inc()
            history.add_transaction(
                Transaction(
                    timestamp=time.time(),
                    city=city,
                    success=False,
                    cached=False,
                    response_time_ms=response_time_ms,
                    status_code=503,
                    error="Circuit breaker open",
                )
            )
            return (
                jsonify(
                    {
                        "error": "Service temporarily unavailable",
                        "detail": "External weather service is currently "
                        "unavailable. Please try again later.",
                    }
                ),
                503,
            )

        except ExternalAPIError as e:
            response_time_ms = round((time.time() - start_time) * 1000, 2)
            logger.error(
                "external_api_error",
                city=city,
                error=str(e),
                status_code=e.status_code,
            )
            weather_requests_total.labels(
                city=city.lower(),
                cached="false",
                status="upstream_error",
            ).inc()
            history.add_transaction(
                Transaction(
                    timestamp=time.time(),
                    city=city,
                    success=False,
                    cached=False,
                    response_time_ms=response_time_ms,
                    status_code=502,
                    error=str(e),
                )
            )
            return (
                jsonify(
                    {
                        "error": "Failed to fetch weather data",
                        "detail": str(e),
                    }
                ),
                502,
            )

        except Exception as e:
            response_time_ms = round((time.time() - start_time) * 1000, 2)
            logger.exception("unexpected_error", city=city, error=str(e))
            weather_requests_total.labels(
                city=city.lower(),
                cached="false",
                status="error",
            ).inc()
            history.add_transaction(
                Transaction(
                    timestamp=time.time(),
                    city=city,
                    success=False,
                    cached=False,
                    response_time_ms=response_time_ms,
                    status_code=500,
                    error="Internal server error",
                )
            )
            return jsonify({"error": "Internal server error"}), 500

    @app.route("/health")
    def health() -> tuple[Response, int]:
        """Health check endpoint.

        Returns:
            JSON response with health status.
        """
        redis_healthy = cache.health_check()
        breaker_status = get_breaker_status(weather_api_breaker)

        health_status: dict[str, Any] = {
            "status": "healthy" if redis_healthy else "degraded",
            "components": {
                "redis": {"status": "healthy" if redis_healthy else "unhealthy"},
                "circuit_breaker": breaker_status,
            },
        }

        status_code = 200 if redis_healthy else 503
        return jsonify(health_status), status_code

    @app.route("/metrics")
    def metrics() -> Response:
        """Prometheus metrics endpoint.

        Returns:
            Prometheus metrics in text format.
        """
        return Response(generate_latest(), mimetype="text/plain")

    @app.route("/history")
    def history_page() -> str:
        """Serve the history/analytics page."""
        return render_template("history.html")

    @app.route("/api/history")
    def get_history() -> tuple[Response, int]:
        """Get transaction history.

        Query Parameters:
            limit: Maximum number of transactions (default 50).

        Returns:
            JSON response with transaction history.
        """
        limit = request.args.get("limit", "50")
        try:
            limit_int = min(int(limit), 100)  # Cap at 100
        except ValueError:
            limit_int = 50

        transactions = history.get_history(limit_int)
        return (
            jsonify(
                {
                    "transactions": [t.to_dict() for t in transactions],
                    "count": len(transactions),
                }
            ),
            200,
        )

    @app.route("/api/statistics")
    def get_statistics() -> tuple[Response, int]:
        """Get aggregated statistics.

        Returns:
            JSON response with statistics.
        """
        stats = history.get_statistics()
        return jsonify(stats), 200

    @app.route("/api/history", methods=["DELETE"])
    def clear_history() -> tuple[Response, int]:
        """Clear transaction history.

        Returns:
            JSON response confirming deletion.
        """
        success = history.clear_history()
        if success:
            return jsonify({"message": "History cleared"}), 200
        return jsonify({"error": "Failed to clear history"}), 500

    @app.errorhandler(404)
    def not_found(error: Any) -> tuple[Response, int]:
        """Handle 404 errors."""
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def internal_error(error: Any) -> tuple[Response, int]:
        """Handle 500 errors."""
        logger.exception("unhandled_error", error=str(error))
        return jsonify({"error": "Internal server error"}), 500

    return app


def _register_signal_handlers() -> None:
    """Register signal handlers for graceful shutdown."""
    global shutdown_flag

    def handle_shutdown(signum: int, frame: Any) -> None:
        global shutdown_flag
        signal_name = signal.Signals(signum).name
        logger.info("shutdown_signal_received", signal=signal_name)
        shutdown_flag = True
        # Allow current requests to complete
        logger.info("graceful_shutdown_initiated")
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)


def is_shutting_down() -> bool:
    """Check if the application is shutting down."""
    return shutdown_flag


# Application instance for WSGI servers
app = create_app()

if __name__ == "__main__":
    # Development server - only for local development
    # In production, use gunicorn: gunicorn app.main:app
    import os

    dev_app = create_app(json_logs=False)
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    dev_app.run(
        host="127.0.0.1",  # Bind to localhost only for security
        port=int(os.getenv("PORT", "8000")),
        debug=debug_mode,  # nosec B201 - controlled by environment variable
    )
