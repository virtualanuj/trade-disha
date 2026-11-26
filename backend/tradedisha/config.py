"""Static settings loaded from the environment or a .env file.

These are values that need a restart and are not about the signal algorithm.
Tunable signal parameters are versioned in the database (parameters/, Milestone C1);
config/params.toml only seeds version 1 for a new database.
"""

from datetime import time
from pathlib import Path
from typing import Literal

from pydantic import field_validator
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

    frontend_url: str = "http://localhost:5173"  # where the Upstox login returns the browser
    # A production build here is served by the backend itself (`make start`).
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"
    serve_frontend: bool = False
    reload: bool = True  # restart the dev server when backend code changes

    data_dir: Path = REPO_ROOT / "data"  # instrument-master cache
    db_path: Path = REPO_ROOT / "data" / "tradedisha.sqlite"
    holidays_file: Path = REPO_ROOT / "config" / "nse-holidays.txt"
    params_path: Path = REPO_ROOT / "config" / "params.toml"

    indices: list[str] = ["NIFTY", "BANKNIFTY"]
    # Sector indices shown on each index's panel (display only, Milestone E11): Upstox
    # NSE_INDEX names. Changing them changes the subscription, so it needs a restart.
    sector_indices: dict[str, list[str]] = {
        "NIFTY": [
            "Nifty Auto",
            "Nifty FMCG",
            "Nifty IT",
            "Nifty Pharma",
            "Nifty Metal",
            "Nifty Energy",
            "Nifty Realty",
            "Nifty Media",
            "Nifty Fin Service",
            "Nifty PSU Bank",
        ],
        "BANKNIFTY": ["Nifty PSU Bank", "Nifty Pvt Bank", "Nifty Fin Service"],
    }
    # The NSE gold and silver ETFs on the BULLION tab, under their metal (display only,
    # Milestone E21): metal -> (trading symbol, NSE_EQ instrument key from the Upstox NSE
    # file). Changing them changes the subscription, so it needs a restart.
    bullion_etfs: dict[str, tuple[str, str]] = {
        "GOLD": ("GOLDBEES", "NSE_EQ|INF204KB17I5"),
        "SILVER": ("SILVERBEES", "NSE_EQ|INF204KC1402"),
    }
    market_open: time = time(9, 15)
    market_close: time = time(15, 30)
    pre_open_start: time = time(9, 0)
    # MCX bullion (signals and paper trades since E6, spec §6.6, §9a). MCX closes at 23:55
    # while the US is on standard time (roughly November to March) and at 23:30 otherwise:
    # change it with the season.
    mcx_open: time = time(9, 0)
    mcx_close: time = time(23, 30)
    mcx_holidays_file: Path = REPO_ROOT / "config" / "mcx-holidays.txt"
    # US data releases that pause bullion signals (E18); read at start, IST.
    us_events_file: Path = REPO_ROOT / "config" / "us-events.txt"
    bullion_live_max_tick_age_ms: int = 15_000
    # Headlines (display only, spec §6.7): which stocks. How often is `news.poll_seconds`
    # in the parameters, edited in the app.
    news_stocks_file: Path = REPO_ROOT / "config" / "news-stocks.txt"

    feed_provider: FeedProviderName = "synthetic"
    # None = enforce unless the feed is synthetic (which ticks around the clock anyway)
    enforce_signal_hours: bool | None = None
    risk_free_rate: float = 0.065  # annual, for computed Greeks
    feed_live_max_tick_age_ms: int = 5_000
    strike_window: int = 10
    recenter_strikes: int = 2

    # Synthetic feed
    synthetic_ticks_per_second: float = 2.0
    synthetic_seed: int | None = None
    synthetic_trend_per_tick: float = 0.0  # in strike-steps per spot tick; 0 = mean-reverting

    # Replay feed
    replay_date: str | None = None  # YYYY-MM-DD; defaults to latest recorded day
    replay_speed: float = 1.0  # 0 = as fast as possible
    # Fault injection: IST time ranges whose ticks are withheld, e.g. ["10:05:00-10:07:30"]
    replay_drop: list[str] = []
    # Also replay that day's recorded bullion ticks (and run the bullion desk on them). Off by
    # default: MCX trades until 23:30, so a bullion replay runs long past the NSE close.
    replay_bullion: bool = False

    # Upstox (Milestone 1b, needs an account)
    upstox_api_key: str = ""
    upstox_api_secret: str = ""
    upstox_redirect_uri: str = "http://127.0.0.1:8000/api/auth/callback"

    # WebSocket push
    ws_tick_hz: float = 20.0  # max tick frames per second per index (50 ms gap)
    ws_chain_hz: float = 2.0  # max chain frames per second per index

    @field_validator("db_path", "data_dir", "frontend_dist", mode="after")
    @classmethod
    def _relative_to_repo(cls, v: Path) -> Path:
        """`data/live.sqlite` in .env means the repo's data folder, wherever we start from."""
        if str(v) == ":memory:" or v.is_absolute():
            return v
        return REPO_ROOT / v


def hours_enforced(settings: Settings) -> bool:
    """Whether market hours gate signals, paper trades and the status banner.

    The synthetic feed ticks around the clock, so by default it ignores them.
    """
    if settings.enforce_signal_hours is not None:
        return settings.enforce_signal_hours
    return settings.feed_provider != "synthetic"


def load_settings() -> Settings:
    """Read settings once at startup."""
    return Settings()
