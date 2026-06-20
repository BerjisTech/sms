"""Configuration loaded from environment / .env file."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Android gateway (the phone).
    gateway_scheme: str = "http"
    gateway_host: str = Field(..., description="LAN IP of the phone")
    gateway_port: int = 8080
    gateway_username: str
    gateway_password: str

    # This server's own basic-auth credentials.
    server_username: str
    server_password: str
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    # Rate limiting.
    rate_limit_per_day: int = 100
    rate_limit_min_interval_seconds: float = 5.0
    max_attempts: int = 3

    # Storage / logging.
    db_path: str = "sms_gateway.db"
    log_file: str = "sms_gateway.log"

    @property
    def gateway_base_url(self) -> str:
        return f"{self.gateway_scheme}://{self.gateway_host}:{self.gateway_port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
