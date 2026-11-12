"""Broker authentication state. The Upstox OAuth flow arrives with live-feed work."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AuthState = Literal["missing", "valid", "expired", "not_required"]


@dataclass
class AuthService:
    """Tracks whether a broker login exists. Synthetic and replay feeds need none."""

    required: bool

    def state(self) -> AuthState:
        return "missing" if self.required else "not_required"
