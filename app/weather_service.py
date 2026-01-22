"""Weather service for fetching data from Open-Meteo API."""

import time
from typing import Any

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.cache import RedisCache, cache
from app.circuit_breaker import (
    CircuitBreakerOpenError,
    weather_api_breaker,
    with_circuit_breaker,
)
from app.config import config
from app.logging_config import get_logger

logger = get_logger(__name__)


class WeatherServiceError(Exception):
    """Base exception for weather service errors."""

    pass


class CityNotFoundError(WeatherServiceError):
    """Exception raised when city is not found."""

    pass


class ExternalAPIError(WeatherServiceError):
    """Exception raised for external API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class WeatherService:
    """Service for fetching weather data from Open-Meteo API."""

    CACHE_PREFIX_GEOCODE = "geocode"
    CACHE_PREFIX_WEATHER = "weather"

    def __init__(self, cache_client: RedisCache | None = None) -> None:
        """Initialize weather service.

        Args:
            cache_client: Optional cache client for dependency injection.
        """
        self.cache = cache_client or cache

    def get_weather(self, city: str) -> dict[str, Any]:
        """Get weather data for a city.

        First checks cache, then fetches from API if not cached.

        Args:
            city: City name to get weather for.

        Returns:
            Weather data dictionary.

        Raises:
            CityNotFoundError: If city cannot be found.
            ExternalAPIError: If external API fails.
            CircuitBreakerOpenError: If circuit breaker is open.
        """
        city = city.strip()
        if not city:
            raise CityNotFoundError("City name cannot be empty")

        # Check cache first
        cached_data = self.cache.get(self.CACHE_PREFIX_WEATHER, city)
        if cached_data:
            cached_data["cached"] = True
            return cached_data

        # Fetch fresh data
        start_time = time.time()
        try:
            weather_data = self._fetch_weather_data(city)
            duration_ms = (time.time() - start_time) * 1000

            logger.info(
                "weather_fetch_success",
                city=city,
                duration_ms=round(duration_ms, 2),
            )

            # Cache the result
            self.cache.set(self.CACHE_PREFIX_WEATHER, city, weather_data)
            weather_data["cached"] = False
            return weather_data

        except (CityNotFoundError, CircuitBreakerOpenError):
            raise
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "weather_fetch_error",
                city=city,
                duration_ms=round(duration_ms, 2),
                error=str(e),
            )
            raise

    def _fetch_weather_data(self, city: str) -> dict[str, Any]:
        """Fetch weather data from external API.

        Args:
            city: City name.

        Returns:
            Weather data dictionary.
        """
        # First, geocode the city
        coords = self._geocode_city(city)

        # Then fetch weather
        weather = self._fetch_weather_from_coords(
            coords["latitude"], coords["longitude"]
        )

        return {
            "city": coords["name"],
            "country": coords.get("country", "Unknown"),
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
            "temperature": weather["current"]["temperature_2m"],
            "temperature_unit": weather["current_units"]["temperature_2m"],
            "humidity": weather["current"].get("relative_humidity_2m"),
            "humidity_unit": weather["current_units"].get("relative_humidity_2m", "%"),
            "wind_speed": weather["current"].get("wind_speed_10m"),
            "wind_speed_unit": weather["current_units"].get("wind_speed_10m", "km/h"),
            "weather_code": weather["current"].get("weather_code"),
            "timestamp": weather["current"]["time"],
        }

    def _geocode_city(self, city: str) -> dict[str, Any]:
        """Geocode a city name to coordinates.

        Args:
            city: City name.

        Returns:
            Dictionary with name, latitude, longitude, and country.

        Raises:
            CityNotFoundError: If city not found.
        """
        # Check cache first
        cached = self.cache.get(self.CACHE_PREFIX_GEOCODE, city)
        if cached:
            return cached

        result = self._fetch_geocode(city)

        # Cache geocoding result with longer TTL (1 hour)
        self.cache.set(self.CACHE_PREFIX_GEOCODE, city, result, ttl=3600)
        return result

    @with_circuit_breaker(weather_api_breaker)
    @retry(
        stop=stop_after_attempt(config.RETRY_MAX_ATTEMPTS),
        wait=wait_exponential(multiplier=config.RETRY_WAIT_SECONDS, min=1, max=10),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def _fetch_geocode(self, city: str) -> dict[str, Any]:
        """Fetch geocoding data from API with retry and circuit breaker.

        Args:
            city: City name.

        Returns:
            Geocoding result.

        Raises:
            CityNotFoundError: If city not found.
            ExternalAPIError: If API fails.
        """
        url = f"{config.GEOCODING_API_BASE_URL}/search"
        params = {"name": city, "count": 1, "language": "en", "format": "json"}

        logger.info("geocoding_request", city=city, url=url)

        response = requests.get(
            url, params=params, timeout=config.REQUEST_TIMEOUT_SECONDS
        )

        logger.info(
            "geocoding_response",
            city=city,
            status_code=response.status_code,
        )

        if response.status_code != 200:
            raise ExternalAPIError(
                f"Geocoding API returned status {response.status_code}",
                status_code=response.status_code,
            )

        data = response.json()
        results = data.get("results", [])

        if not results:
            raise CityNotFoundError(f"City '{city}' not found")

        result = results[0]
        return {
            "name": result["name"],
            "latitude": result["latitude"],
            "longitude": result["longitude"],
            "country": result.get("country", "Unknown"),
        }

    @with_circuit_breaker(weather_api_breaker)
    @retry(
        stop=stop_after_attempt(config.RETRY_MAX_ATTEMPTS),
        wait=wait_exponential(multiplier=config.RETRY_WAIT_SECONDS, min=1, max=10),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def _fetch_weather_from_coords(
        self, latitude: float, longitude: float
    ) -> dict[str, Any]:
        """Fetch weather data from coordinates with retry and circuit breaker.

        Args:
            latitude: Latitude coordinate.
            longitude: Longitude coordinate.

        Returns:
            Weather API response.

        Raises:
            ExternalAPIError: If API fails.
        """
        url = f"{config.WEATHER_API_BASE_URL}/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code"
            ),
            "timezone": "auto",
        }

        logger.info(
            "weather_api_request",
            latitude=latitude,
            longitude=longitude,
            url=url,
        )

        response = requests.get(
            url, params=params, timeout=config.REQUEST_TIMEOUT_SECONDS
        )

        logger.info(
            "weather_api_response",
            latitude=latitude,
            longitude=longitude,
            status_code=response.status_code,
        )

        if response.status_code != 200:
            raise ExternalAPIError(
                f"Weather API returned status {response.status_code}",
                status_code=response.status_code,
            )

        return response.json()


# Global service instance
weather_service = WeatherService()
