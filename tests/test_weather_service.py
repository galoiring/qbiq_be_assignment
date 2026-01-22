"""Unit tests for the weather service module."""

import pytest
import responses

from app.config import config
from app.weather_service import CityNotFoundError, ExternalAPIError


class TestWeatherService:
    """Tests for WeatherService class."""

    @responses.activate
    def test_get_weather_success(
        self, weather_service, mock_geocode_response, mock_weather_response
    ):
        """Test successful weather fetch."""
        # Mock geocoding API
        responses.add(
            responses.GET,
            f"{config.GEOCODING_API_BASE_URL}/search",
            json=mock_geocode_response,
            status=200,
        )

        # Mock weather API
        responses.add(
            responses.GET,
            f"{config.WEATHER_API_BASE_URL}/forecast",
            json=mock_weather_response,
            status=200,
        )

        result = weather_service.get_weather("London")

        assert result["city"] == "London"
        assert result["country"] == "United Kingdom"
        assert result["temperature"] == 10.5
        assert result["humidity"] == 75
        assert result["cached"] is False

    @responses.activate
    def test_get_weather_returns_cached_data(
        self, weather_service, cache, mock_geocode_response, mock_weather_response
    ):
        """Test that cached data is returned on subsequent requests."""
        # Mock APIs
        responses.add(
            responses.GET,
            f"{config.GEOCODING_API_BASE_URL}/search",
            json=mock_geocode_response,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{config.WEATHER_API_BASE_URL}/forecast",
            json=mock_weather_response,
            status=200,
        )

        # First request - fetches from API
        result1 = weather_service.get_weather("London")
        assert result1["cached"] is False

        # Second request - should return cached data
        result2 = weather_service.get_weather("London")
        assert result2["cached"] is True

        # Verify only 2 API calls were made (geocode + weather)
        assert len(responses.calls) == 2

    @responses.activate
    def test_get_weather_city_not_found(self, weather_service):
        """Test handling of city not found."""
        # Mock geocoding API with empty results
        responses.add(
            responses.GET,
            f"{config.GEOCODING_API_BASE_URL}/search",
            json={"results": []},
            status=200,
        )

        with pytest.raises(CityNotFoundError) as exc_info:
            weather_service.get_weather("NonexistentCity12345")

        assert "NonexistentCity12345" in str(exc_info.value)

    def test_get_weather_empty_city_name(self, weather_service):
        """Test handling of empty city name."""
        with pytest.raises(CityNotFoundError) as exc_info:
            weather_service.get_weather("")

        assert "empty" in str(exc_info.value).lower()

    def test_get_weather_whitespace_city_name(self, weather_service):
        """Test handling of whitespace-only city name."""
        with pytest.raises(CityNotFoundError):
            weather_service.get_weather("   ")

    @responses.activate
    def test_get_weather_geocoding_api_error(self, weather_service):
        """Test handling of geocoding API errors."""
        responses.add(
            responses.GET,
            f"{config.GEOCODING_API_BASE_URL}/search",
            json={"error": "Server error"},
            status=500,
        )

        with pytest.raises(ExternalAPIError) as exc_info:
            weather_service.get_weather("London")

        assert exc_info.value.status_code == 500

    @responses.activate
    def test_get_weather_weather_api_error(
        self, weather_service, mock_geocode_response
    ):
        """Test handling of weather API errors."""
        # Mock successful geocoding
        responses.add(
            responses.GET,
            f"{config.GEOCODING_API_BASE_URL}/search",
            json=mock_geocode_response,
            status=200,
        )

        # Mock failed weather API
        responses.add(
            responses.GET,
            f"{config.WEATHER_API_BASE_URL}/forecast",
            json={"error": "Server error"},
            status=503,
        )

        with pytest.raises(ExternalAPIError) as exc_info:
            weather_service.get_weather("London")

        assert exc_info.value.status_code == 503

    @responses.activate
    def test_geocode_result_is_cached(
        self, weather_service, cache, mock_geocode_response, mock_weather_response
    ):
        """Test that geocoding results are cached separately."""
        # Mock APIs for first call
        responses.add(
            responses.GET,
            f"{config.GEOCODING_API_BASE_URL}/search",
            json=mock_geocode_response,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{config.WEATHER_API_BASE_URL}/forecast",
            json=mock_weather_response,
            status=200,
        )

        # First request
        weather_service.get_weather("London")

        # Clear weather cache but keep geocode cache
        cache.delete("weather", "london")

        # Mock only weather API for second call
        responses.add(
            responses.GET,
            f"{config.WEATHER_API_BASE_URL}/forecast",
            json=mock_weather_response,
            status=200,
        )

        # Second request should use cached geocode
        weather_service.get_weather("London")

        # Should be 3 calls: geocode + weather + weather (no second geocode)
        assert len(responses.calls) == 3


class TestWeatherDataFormat:
    """Tests for weather data format."""

    @responses.activate
    def test_weather_response_contains_required_fields(
        self, weather_service, mock_geocode_response, mock_weather_response
    ):
        """Test that response contains all required fields."""
        responses.add(
            responses.GET,
            f"{config.GEOCODING_API_BASE_URL}/search",
            json=mock_geocode_response,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{config.WEATHER_API_BASE_URL}/forecast",
            json=mock_weather_response,
            status=200,
        )

        result = weather_service.get_weather("London")

        required_fields = [
            "city",
            "country",
            "latitude",
            "longitude",
            "temperature",
            "temperature_unit",
            "humidity",
            "wind_speed",
            "timestamp",
            "cached",
        ]

        for field in required_fields:
            assert field in result, f"Missing field: {field}"
