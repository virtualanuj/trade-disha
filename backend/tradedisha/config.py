"""Static settings loaded from the environment or a .env file.

These are values that need a restart and are not about the signal algorithm.
Tunable signal parameters live in config/params.toml (Milestone 3).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-level configuration."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="TRADEDISHA_", extra="ignore")

    bind_host: str = "127.0.0.1"
    bind_port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173"]


def load_settings() -> Settings:
    """Read settings once at startup."""
    return Settings()
