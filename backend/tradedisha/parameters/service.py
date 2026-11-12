"""Loads config/params.toml, validates it, and swaps it in on demand.

The file is the source of truth. Startup refuses an invalid file; a reload that fails
keeps the previous set and reports the field errors. Spec §3.2.
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from tradedisha.clock import epoch_ms_now
from tradedisha.parameters.model import ParameterSet

log = logging.getLogger(__name__)


class ParameterValidationError(Exception):
    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__("invalid parameters")
        self.errors = errors


@dataclass(frozen=True)
class LoadedParameters:
    params: ParameterSet
    loaded_at: int
    path: Path


def _format_errors(exc: ValidationError) -> list[dict[str, str]]:
    return [
        {"field": ".".join(str(p) for p in e["loc"]) or "<root>", "message": e["msg"]}
        for e in exc.errors()
    ]


def parse_params(text: str) -> ParameterSet:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ParameterValidationError([{"field": "<toml>", "message": str(e)}]) from e
    try:
        return ParameterSet.model_validate(data)
    except ValidationError as e:
        raise ParameterValidationError(_format_errors(e)) from e


class ParameterService:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._loaded: LoadedParameters | None = None

    def load(self) -> LoadedParameters:
        """Parse and validate the file; raises ParameterValidationError on failure."""
        if not self.path.exists():
            raise ParameterValidationError(
                [{"field": "<file>", "message": f"{self.path} does not exist"}]
            )
        params = parse_params(self.path.read_text())
        self._loaded = LoadedParameters(params, epoch_ms_now(), self.path)
        log.info("parameters loaded from %s", self.path)
        return self._loaded

    def reload(self) -> LoadedParameters:
        """Same as load; kept separate so callers read as intended."""
        return self.load()

    @property
    def current(self) -> LoadedParameters:
        if self._loaded is None:
            raise RuntimeError("parameters not loaded")
        return self._loaded

    @property
    def params(self) -> ParameterSet:
        return self.current.params
