"""Integration tests for API endpoints."""

import json

import responses

from app.config import config


class TestWeatherEndpoint:
    """Integration tests for /weather endpoint."""

    @responses.activate
    def test_weather_endpoint_success(
        self, client, mock_geocode_response, mock_weather_response
    ):
        """Test successful weather request."""
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

        response = client.get("/weather?city=London")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["city"] == "London"
        assert data["temperature"] == 10.5
        assert "cached" in data

    def test_weather_endpoint_missing_city_param(self, client):
        """Test weather endpoint without city parameter."""
        response = client.get("/weather")

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data
        assert "required" in data["error"].lower()

    def test_weather_endpoint_empty_city_param(self, client):
        """Test weather endpoint with empty city parameter."""
        response = client.get("/weather?city=")

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data

    @responses.activate
    def test_weather_endpoint_city_not_found(self, client):
        """Test weather endpoint with non-existent city."""
        responses.add(
            responses.GET,
            f"{config.GEOCODING_API_BASE_URL}/search",
            json={"results": []},
            status=200,
        )

        response = client.get("/weather?city=NonexistentCity12345")

        assert response.status_code == 404
        data = json.loads(response.data)
        assert "error" in data
        assert "not found" in data["error"].lower()

    @responses.activate
    def test_weather_endpoint_external_api_error(self, client):
        """Test weather endpoint when external API fails."""
        responses.add(
            responses.GET,
            f"{config.GEOCODING_API_BASE_URL}/search",
            json={"error": "Internal error"},
            status=500,
        )

        response = client.get("/weather?city=London")

        assert response.status_code == 502
        data = json.loads(response.data)
        assert "error" in data

    @responses.activate
    def test_weather_endpoint_returns_cached_data(
        self, client, mock_geocode_response, mock_weather_response
    ):
        """Test that cached data is returned on second request."""
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
        response1 = client.get("/weather?city=London")
        data1 = json.loads(response1.data)
        assert data1["cached"] is False

        # Second request
        response2 = client.get("/weather?city=London")
        data2 = json.loads(response2.data)
        assert data2["cached"] is True


class TestHealthEndpoint:
    """Integration tests for /health endpoint."""

    def test_health_endpoint_returns_status(self, client):
        """Test health endpoint returns proper structure."""
        response = client.get("/health")

        # May return 200 or 503 depending on Redis availability
        assert response.status_code in [200, 503]
        data = json.loads(response.data)

        assert "status" in data
        assert "components" in data
        assert "redis" in data["components"]
        assert "circuit_breaker" in data["components"]

    def test_health_endpoint_circuit_breaker_status(self, client):
        """Test health endpoint includes circuit breaker status."""
        response = client.get("/health")
        data = json.loads(response.data)

        cb_status = data["components"]["circuit_breaker"]
        assert "name" in cb_status
        assert "state" in cb_status
        assert "fail_counter" in cb_status


class TestMetricsEndpoint:
    """Integration tests for /metrics endpoint."""

    def test_metrics_endpoint_returns_prometheus_format(self, client):
        """Test metrics endpoint returns Prometheus format."""
        response = client.get("/metrics")

        assert response.status_code == 200
        assert response.content_type == "text/plain; charset=utf-8"

        # Check for some expected metrics
        data = response.data.decode("utf-8")
        assert "http_requests_total" in data
        assert "http_request_duration_seconds" in data

    @responses.activate
    def test_metrics_increment_on_requests(
        self, client, mock_geocode_response, mock_weather_response
    ):
        """Test that metrics are incremented on requests."""
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

        # Make a weather request
        client.get("/weather?city=London")

        # Check metrics
        response = client.get("/metrics")
        data = response.data.decode("utf-8")

        # Should have weather request metrics
        assert "weather_requests_total" in data


class TestIndexEndpoint:
    """Integration tests for / endpoint (frontend)."""

    def test_index_returns_html(self, client):
        """Test index endpoint returns HTML page."""
        response = client.get("/")

        assert response.status_code == 200
        assert b"Weather Proxy" in response.data
        assert b"<html" in response.data

    def test_index_contains_search_form(self, client):
        """Test index page contains search form."""
        response = client.get("/")

        assert b"cityInput" in response.data
        assert b"weatherForm" in response.data


class TestErrorHandling:
    """Integration tests for error handling."""

    def test_404_returns_json(self, client):
        """Test that 404 errors return JSON."""
        response = client.get("/nonexistent-endpoint")

        assert response.status_code == 404
        data = json.loads(response.data)
        assert "error" in data
