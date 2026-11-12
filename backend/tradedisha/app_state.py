"""Everything the API needs to reach, built once in the lifespan."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from tradedisha.auth import AuthService
from tradedisha.clock import MarketClock
from tradedisha.config import Settings
from tradedisha.events import EventBus
from tradedisha.market.session import FeedSession
from tradedisha.metrics.latency import LatencyTracker
from tradedisha.parameters import ParameterService


@dataclass
class AppState:
    settings: Settings
    conn: sqlite3.Connection
    clock: MarketClock
    events: EventBus
    latency: LatencyTracker
    auth: AuthService
    session: FeedSession
    params: ParameterService
