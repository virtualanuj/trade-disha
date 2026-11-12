"""Shared fixtures: an app wired to the synthetic feed and an in-memory database."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tradedisha.config import Settings
from tradedisha.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "test.sqlite",
        feed_provider="synthetic",
        synthetic_ticks_per_second=200,
        synthetic_seed=7,
        strike_window=2,
        ws_tick_hz=50,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c
