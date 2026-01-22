# Weather Proxy Service

A production-ready REST API that acts as a proxy for the Open-Meteo weather API, featuring caching, resilience patterns, and comprehensive observability.

## Features

- **REST API**: Weather data endpoint with city-based lookup
- **Caching**: Redis-backed caching to minimize external API calls (5-minute TTL)
- **Resilience**: Circuit breaker pattern and retry mechanism for external API failures
- **Observability**: Structured JSON logging with request correlation
- **Metrics**: Prometheus-compatible `/metrics` endpoint
- **Frontend**: Simple web UI for querying weather data
- **Containerization**: Production-ready Docker setup with docker-compose

## Requirements

- Python 3.11+
- Docker and Docker Compose (for containerized deployment)
- Redis (provided via docker-compose)

## Quick Start

### Using Docker Compose (Recommended)

```bash
# Start the application with all dependencies
docker compose up -d

# View logs
docker compose logs -f app

# Stop the application
docker compose down
```

The application will be available at:
- **Web UI**: http://localhost:8000/
- **Weather API**: http://localhost:8000/weather?city=London
- **Health Check**: http://localhost:8000/health
- **Metrics**: http://localhost:8000/metrics

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start Redis (if not using docker-compose)
docker run -d -p 6379:6379 redis:7-alpine

# Run the application
python -m app.main

# Or with gunicorn
gunicorn --bind 0.0.0.0:8000 app.main:app
```

## API Endpoints

### GET /weather?city={city_name}

Returns current weather data for the specified city.

**Parameters:**
- `city` (required): Name of the city

**Response (200 OK):**
```json
{
  "city": "London",
  "country": "United Kingdom",
  "latitude": 51.5074,
  "longitude": -0.1278,
  "temperature": 15.5,
  "temperature_unit": "°C",
  "humidity": 72,
  "humidity_unit": "%",
  "wind_speed": 12.5,
  "wind_speed_unit": "km/h",
  "weather_code": 3,
  "timestamp": "2024-01-15T14:00",
  "cached": false
}
```

**Error Responses:**
- `400`: Missing city parameter
- `404`: City not found
- `502`: External API error
- `503`: Service unavailable (circuit breaker open)

### GET /health

Returns service health status including Redis connectivity and circuit breaker state.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "components": {
    "redis": {"status": "healthy"},
    "circuit_breaker": {
      "name": "weather_api",
      "state": "closed",
      "fail_counter": 0,
      "fail_max": 5,
      "reset_timeout": 30
    }
  }
}
```

### GET /metrics

Prometheus-compatible metrics endpoint exposing:
- `http_requests_total`: Total HTTP requests by method, endpoint, and status code
- `http_request_duration_seconds`: Request duration histogram
- `weather_requests_total`: Weather API requests by city, cache status, and result
- `upstream_requests_total`: Requests to upstream weather API

## Architecture

### Project Structure

```
weather-proxy/
├── app/
│   ├── __init__.py
│   ├── main.py              # Flask application and routes
│   ├── config.py            # Configuration management
│   ├── cache.py             # Redis caching layer
│   ├── weather_service.py   # Weather API client
│   ├── circuit_breaker.py   # Circuit breaker implementation
│   ├── logging_config.py    # Structured logging setup
│   └── metrics.py           # Prometheus metrics
├── tests/
│   ├── conftest.py          # Pytest fixtures
│   ├── test_api.py          # Integration tests
│   ├── test_cache.py        # Cache unit tests
│   ├── test_weather_service.py
│   └── test_circuit_breaker.py
├── templates/
│   └── index.html           # Frontend UI
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── pyproject.toml
```

### Design Decisions

1. **Flask Framework**: Chosen for its simplicity and wide ecosystem. For higher concurrency, consider FastAPI with async support.

2. **Redis Caching**:
   - Weather data cached for 5 minutes (configurable via `CACHE_TTL_SECONDS`)
   - Geocoding results cached for 1 hour (city coordinates rarely change)
   - Cache keys are case-insensitive for better hit rates

3. **Circuit Breaker Pattern**:
   - Opens after 5 consecutive failures (configurable)
   - Automatically resets after 30 seconds
   - Prevents cascading failures when upstream is unavailable

4. **Retry Mechanism**:
   - Uses exponential backoff (1s, 2s, 4s)
   - Maximum 3 attempts before failing
   - Only retries on transient network errors

5. **Structured Logging**:
   - JSON format in production for log aggregation
   - Request correlation via `X-Request-ID` header
   - Logs include duration, status codes, and cache hits/misses

6. **Graceful Shutdown**:
   - Handles SIGTERM for zero-downtime deployments
   - Gunicorn configured with graceful timeout

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | localhost | Redis hostname |
| `REDIS_PORT` | 6379 | Redis port |
| `REDIS_PASSWORD` | (none) | Redis password |
| `CACHE_TTL_SECONDS` | 300 | Weather cache TTL (5 min) |
| `CIRCUIT_BREAKER_FAIL_MAX` | 5 | Failures before circuit opens |
| `CIRCUIT_BREAKER_RESET_TIMEOUT` | 30 | Seconds before circuit resets |
| `RETRY_MAX_ATTEMPTS` | 3 | Max retry attempts |
| `REQUEST_TIMEOUT_SECONDS` | 10 | HTTP request timeout |
| `DEBUG` | false | Enable debug mode |

## Testing

```bash
# Run all tests with coverage
pytest

# Run specific test file
pytest tests/test_api.py

# Run with verbose output
pytest -v

# Generate HTML coverage report
pytest --cov=app --cov-report=html
```

### Test Coverage

The test suite includes:
- **Unit Tests**: Cache operations, weather service logic, circuit breaker behavior
- **Integration Tests**: API endpoints, error handling, metrics

## CI/CD

GitHub Actions workflow (`.github/workflows/ci.yml`) includes:

1. **Lint**: Black, isort, Flake8, MyPy
2. **Test**: pytest with Redis service container
3. **Build**: Docker image build and smoke test
4. **Security**: Bandit security scanning, dependency vulnerability check

## Improvements for Future Development

Given more time, the following improvements would be valuable:

### Performance
- Add connection pooling for Redis
- Implement request coalescing for concurrent identical requests
- Add response compression (gzip)

### Reliability
- Implement fallback to stale cache when upstream is unavailable
- Add rate limiting to prevent abuse
- Implement request queuing during circuit breaker open state

### Observability
- Add distributed tracing (OpenTelemetry)
- Implement custom dashboards (Grafana)
- Add alerting rules for SLO violations

### Features
- Support for multiple weather providers with failover
- Historical weather data endpoint
- Weather forecasts (hourly/daily)
- Bulk city lookup endpoint

### DevOps
- Helm chart for Kubernetes deployment
- Terraform for cloud infrastructure
- Auto-scaling based on request metrics
- Blue-green deployment configuration

### Security
- API key authentication
- Rate limiting per client
- Input validation hardening
- Security headers (CORS, CSP)

## Assumptions

1. **Usage Pattern**: The service is expected to handle moderate traffic with potential for cache effectiveness (same cities queried multiple times within the TTL window).

2. **Availability Requirements**: Brief unavailability during external API outages is acceptable, hence the circuit breaker pattern without complex fallback mechanisms.

3. **Data Freshness**: 5-minute staleness for weather data is acceptable for most use cases. Real-time requirements would need a different caching strategy.

4. **Geocoding Stability**: City coordinates don't change, allowing for longer geocode cache TTL (1 hour).

5. **Single Region**: The service is deployed in a single region. Multi-region deployment would require distributed caching considerations.

## License

MIT
