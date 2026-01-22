"""Pytest fixtures and configuration."""

import fakeredis
import pytest
import responses

from app.cache import RedisCache
from app.main import create_app
from app.weather_service import WeatherService


@pytest.fixture
def fake_redis():
    """Create a fake Redis instance for testing."""
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def cache(fake_redis):
    """Create a cache instance with fake Redis."""
    return RedisCache(redis_client=fake_redis)


@pytest.fixture
def weather_service(cache):
    """Create a weather service instance with fake cache."""
    return WeatherService(cache_client=cache)


@pytest.fixture
def app(weather_service):
    """Create a Flask test application."""
    app = create_app(weather_svc=weather_service, json_logs=False)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()


@pytest.fixture
def mock_responses():
    """Set up responses mock for external API calls."""
    with responses.RequestsMock() as rsps:
        yield rsps


@pytest.fixture
def mock_geocode_response():
    """Sample geocoding API response."""
    return {
        "results": [
            {
                "name": "London",
                "latitude": 51.5074,
                "longitude": -0.1278,
                "country": "United Kingdom",
            }
        ]
    }


@pytest.fixture
def mock_weather_response():
    """Sample weather API response."""
    return {
        "current": {
            "time": "2024-01-15T12:00",
            "temperature_2m": 10.5,
            "relative_humidity_2m": 75,
            "wind_speed_10m": 15.2,
            "weather_code": 3,
        },
        "current_units": {
            "temperature_2m": "°C",
            "relative_humidity_2m": "%",
            "wind_speed_10m": "km/h",
        },
    }
