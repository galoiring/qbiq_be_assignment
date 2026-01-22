"""Unit tests for the cache module."""


class TestRedisCache:
    """Tests for RedisCache class."""

    def test_get_returns_none_for_missing_key(self, cache):
        """Test that get returns None for non-existent keys."""
        result = cache.get("weather", "nonexistent")
        assert result is None

    def test_set_and_get_value(self, cache):
        """Test setting and retrieving a value."""
        data = {"temperature": 20.5, "city": "London"}
        cache.set("weather", "london", data)

        result = cache.get("weather", "london")
        assert result == data

    def test_key_is_case_insensitive(self, cache):
        """Test that cache keys are case-insensitive."""
        data = {"temperature": 20.5}
        cache.set("weather", "LONDON", data)

        result = cache.get("weather", "london")
        assert result == data

    def test_set_with_custom_ttl(self, cache, fake_redis):
        """Test setting a value with custom TTL."""
        data = {"temperature": 20.5}
        cache.set("weather", "london", data, ttl=600)

        # Verify key exists and has TTL
        key = "weather_proxy:weather:london"
        assert fake_redis.exists(key)
        ttl = fake_redis.ttl(key)
        assert ttl > 0 and ttl <= 600

    def test_delete_removes_key(self, cache):
        """Test deleting a cached value."""
        data = {"temperature": 20.5}
        cache.set("weather", "london", data)

        cache.delete("weather", "london")

        result = cache.get("weather", "london")
        assert result is None

    def test_build_key_format(self, cache):
        """Test that keys are built with correct format."""
        key = cache._build_key("weather", "New York")
        assert key == "weather_proxy:weather:new york"

    def test_health_check_returns_true_when_healthy(self, cache):
        """Test health check with working Redis."""
        assert cache.health_check() is True

    def test_get_handles_invalid_json(self, cache, fake_redis):
        """Test that invalid JSON in cache returns None."""
        key = "weather_proxy:weather:invalid"
        fake_redis.setex(key, 300, "not-valid-json")

        result = cache.get("weather", "invalid")
        assert result is None
