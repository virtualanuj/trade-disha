"""Static settings loaded from the environment or a .env file.

These are values that need a restart and are not about the signal algorithm.
Tunable signal parameters live in config/params.toml (Milestone 3).
"""

from datetime import time
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

FeedProviderName = Literal["synthetic", "replay", "upstox"]


class Settings(BaseSettings):
    """Process-level configuration."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_prefix="TRADEDISHA_", extra="ignore"
    )

    bind_host: str = "127.0.0.1"
    bind_port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    db_path: Path = REPO_ROOT / "data" / "tradedisha.sqlite"
    holidays_file: Path = REPO_ROOT / "config" / "nse-holidays.txt"

    indices: list[str] = ["NIFTY", "BANKNIFTY"]
    market_open: time = time(9, 15)
    market_close: time = time(15, 30)
    pre_open_start: time = time(9, 0)

    feed_provider: FeedProviderName = "synthetic"
    strike_window: int = 10
    recenter_strikes: int = 2

    # Synthetic feed
    synthetic_ticks_per_second: float = 2.0
    synthetic_seed: int | None = None

    # Replay feed
    replay_date: str | None = None  # YYYY-MM-DD; defaults to latest recorded day
    replay_speed: float = 1.0  # 0 = as fast as possible

    # Upstox (Milestone 1b, needs an account)
    upstox_api_key: str = ""
    upstox_api_secret: str = ""
    upstox_redirect_uri: str = "http://127.0.0.1:8000/api/auth/callback"

    # WebSocket push
    ws_tick_hz: float = 20.0  # max tick frames per second per index (50 ms gap)


def load_settings() -> Settings:
    """Read settings once at startup."""
    return Settings()
