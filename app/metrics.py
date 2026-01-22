"""Prometheus metrics for the application."""

from prometheus_client import Counter, Histogram, Info

# Application info
app_info = Info("weather_proxy", "Weather Proxy Application Information")
app_info.info({"version": "1.0.0", "python_version": "3.11"})

# Request metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Weather API specific metrics
weather_requests_total = Counter(
    "weather_requests_total",
    "Total weather API requests",
    ["city", "cached", "status"],
)

upstream_requests_total = Counter(
    "upstream_requests_total",
    "Total requests to upstream weather API",
    ["endpoint", "status_code"],
)

upstream_request_duration_seconds = Histogram(
    "upstream_request_duration_seconds",
    "Upstream API request duration in seconds",
    ["endpoint"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# Cache metrics
cache_operations_total = Counter(
    "cache_operations_total",
    "Total cache operations",
    ["operation", "status"],
)

# Circuit breaker metrics
circuit_breaker_state = Counter(
    "circuit_breaker_state_changes_total",
    "Circuit breaker state changes",
    ["breaker_name", "from_state", "to_state"],
)
