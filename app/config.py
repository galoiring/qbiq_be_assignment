"""Application configuration."""

import os
from dataclasses import dataclass


@dataclass
class Config:
    """Application configuration settings."""

    # Flask
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    TESTING: bool = os.getenv("TESTING", "false").lower() == "true"

    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: str | None = os.getenv("REDIS_PASSWORD")

    # Cache settings
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "300"))  # 5 minutes

    # Weather API (Open-Meteo)
    WEATHER_API_BASE_URL: str = os.getenv(
        "WEATHER_API_BASE_URL", "https://api.open-meteo.com/v1"
    )
    GEOCODING_API_BASE_URL: str = os.getenv(
        "GEOCODING_API_BASE_URL", "https://geocoding-api.open-meteo.com/v1"
    )

    # Circuit Breaker settings
    CIRCUIT_BREAKER_FAIL_MAX: int = int(os.getenv("CIRCUIT_BREAKER_FAIL_MAX", "5"))
    CIRCUIT_BREAKER_RESET_TIMEOUT: int = int(
        os.getenv("CIRCUIT_BREAKER_RESET_TIMEOUT", "30")
    )

    # Retry settings
    RETRY_MAX_ATTEMPTS: int = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
    RETRY_WAIT_SECONDS: float = float(os.getenv("RETRY_WAIT_SECONDS", "1.0"))

    # Request timeout
    REQUEST_TIMEOUT_SECONDS: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))

    @property
    def redis_url(self) -> str:
        """Build Redis URL from components."""
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


config = Config()
