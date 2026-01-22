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
    json_logs: bool = True,
) -> Flask:
    """Create and configure the Flask application.

    Args:
        weather_svc: Optional weather service for dependency injection.
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

    # Use injected service or global instance
    svc = weather_svc or weather_service

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

        if not city:
            return jsonify({"error": "City parameter is required"}), 400

        try:
            data = svc.get_weather(city)

            # Record metric
            weather_requests_total.labels(
                city=city.lower(),
                cached=str(data.get("cached", False)).lower(),
                status="success",
            ).inc()

            return jsonify(data), 200

        except CityNotFoundError as e:
            logger.warning("city_not_found", city=city, error=str(e))
            weather_requests_total.labels(
                city=city.lower(),
                cached="false",
                status="not_found",
            ).inc()
            return jsonify({"error": f"City '{city}' not found"}), 404

        except CircuitBreakerOpenError as e:
            logger.error("circuit_breaker_open", city=city, breaker=e.breaker_name)
            weather_requests_total.labels(
                city=city.lower(),
                cached="false",
                status="circuit_open",
            ).inc()
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
            logger.exception("unexpected_error", city=city, error=str(e))
            weather_requests_total.labels(
                city=city.lower(),
                cached="false",
                status="error",
            ).inc()
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
    # Development server
    dev_app = create_app(json_logs=False)
    dev_app.run(host="0.0.0.0", port=8000, debug=True)
