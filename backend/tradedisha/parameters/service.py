"""The tunable parameters in force, and every version of them that was saved.

The database is the source of truth: each save is a new numbered, tagged version and the
highest version is in force. `config/params.toml` only supplies version 1 for a database
that has none. A save that fails validation changes nothing. Spec §3.2.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import tomllib
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from tradedisha.clock import epoch_ms_now
from tradedisha.parameters.model import FACTOR_SCOPES, ParameterSet
from tradedisha.store.config_versions import ConfigVersion, ConfigVersionStore, Source

log = logging.getLogger(__name__)

MAX_TAG = 60
SEED_TAG = "initial"


class ParameterValidationError(Exception):
    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__("invalid parameters")
        self.errors = errors


@dataclass(frozen=True)
class LoadedParameters:
    params: ParameterSet
    version: int
    tag: str
    created_ts: int


def _format_errors(exc: ValidationError) -> list[dict[str, str]]:
    return [
        {
            "field": ".".join(str(p) for p in e["loc"]) or "<root>",
            "message": e["msg"].removeprefix("Value error, "),
        }
        for e in exc.errors()
    ]


def validate_values(data: object) -> ParameterSet:
    try:
        return ParameterSet.model_validate(data)
    except ValidationError as e:
        raise ParameterValidationError(_format_errors(e)) from e


def parse_params(text: str) -> ParameterSet:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ParameterValidationError([{"field": "<toml>", "message": str(e)}]) from e
    return validate_values(data)


def load_file(path: Path) -> ParameterSet:
    """Parse and validate a parameter file; raises ParameterValidationError on failure."""
    if not path.exists():
        raise ParameterValidationError([{"field": "<file>", "message": f"{path} does not exist"}])
    return parse_params(path.read_text())


def _dump(params: ParameterSet) -> str:
    return json.dumps(params.model_dump(mode="json"), separators=(",", ":"))


def _clean_tag(tag: str) -> str:
    tag = tag.strip()
    if not tag:
        raise ParameterValidationError([{"field": "tag", "message": "a tag is required"}])
    if len(tag) > MAX_TAG:
        raise ParameterValidationError(
            [{"field": "tag", "message": f"at most {MAX_TAG} characters"}]
        )
    return tag


class ParameterService:
    def __init__(self, conn: sqlite3.Connection, seed_path: Path) -> None:
        self.seed_path = seed_path
        self._store = ConfigVersionStore(conn)
        self._loaded: LoadedParameters | None = None

    def load(self) -> LoadedParameters:
        """The version in force; a database with none takes version 1 from the seed file.

        Raises ParameterValidationError when a version is needed from the file and the
        file is missing or invalid.
        """
        latest = self._store.latest()
        if latest is None:
            return self._insert(load_file(self.seed_path), SEED_TAG, "seed", None)
        try:
            params = validate_values(json.loads(latest.params_json))
        except ParameterValidationError as e:
            # Saved by a build whose parameters this one no longer accepts.
            log.error(
                "config v%d is no longer valid (%s); using the file", latest.version, e.errors
            )
            tag = f"file defaults: v{latest.version} no longer valid"
            return self._insert(load_file(self.seed_path), tag, "seed", None)
        self._loaded = LoadedParameters(params, latest.version, latest.tag, latest.created_ts)
        log.info("parameters loaded: config v%d (%s)", latest.version, latest.tag)
        return self._loaded

    def save(
        self,
        params: ParameterSet,
        tag: str,
        *,
        source: Source = "edit",
        reverted_from: int | None = None,
    ) -> LoadedParameters:
        """Store `params` as the next version and put it in force."""
        tag = _clean_tag(tag)
        if self._loaded is not None and params == self._loaded.params:
            raise ParameterValidationError(
                [{"field": "<params>", "message": "nothing changed: these values are in force"}]
            )
        return self._insert(params, tag, source, reverted_from)

    def save_values(self, values: object, tag: str) -> LoadedParameters:
        """Validate values as they come from the editor, then save them.

        The typed editor has no factor switches (they are flipped one at a time, see
        `set_factor`), so values without `factors` keep the switches in force.
        """
        if isinstance(values, dict) and "factors" not in values and self._loaded is not None:
            values = {**values, "factors": self._loaded.params.factors.model_dump(mode="json")}
        return self.save(validate_values(values), tag)

    def set_factor(self, scope: str, name: str, *, enabled: bool) -> LoadedParameters:
        """Switch one factor of an index's or metal's bias on or off, as a new version
        tagged `Factor NIFTY.pcr: off`. Nothing is saved when it is already so."""
        current = self.current.params
        field = FACTOR_SCOPES.get(scope)
        switches = current.factors.scope_model(scope)
        if field is None or switches is None or name not in type(switches).model_fields:
            raise ParameterValidationError(
                [{"field": "factors", "message": f"{scope} has no factor {name}"}]
            )
        value = "on" if enabled else "off"
        if getattr(switches, name) == value:
            return self.current
        factors = current.factors.model_copy(
            update={field: switches.model_copy(update={name: value})}
        )
        return self.save(
            current.model_copy(update={"factors": factors}), f"Factor {scope}.{name}: {value}"
        )

    def revert(self, version: int, tag: str | None = None) -> LoadedParameters:
        """Put an old version's values back in force, as a new version."""
        old = self._store.get(version)
        if old is None:
            raise ParameterValidationError(
                [{"field": "version", "message": f"there is no version {version}"}]
            )
        params = validate_values(json.loads(old.params_json))
        return self.save(
            params, tag or f"Revert to v{version}", source="revert", reverted_from=version
        )

    def versions(self) -> list[ConfigVersion]:
        """Every saved version, newest first."""
        return self._store.list()

    def get(self, version: int) -> ConfigVersion | None:
        return self._store.get(version)

    def _insert(
        self, params: ParameterSet, tag: str, source: Source, reverted_from: int | None
    ) -> LoadedParameters:
        v = self._store.insert(
            tag=tag,
            created_ts=epoch_ms_now(),
            source=source,
            params_json=_dump(params),
            reverted_from=reverted_from,
        )
        self._loaded = LoadedParameters(params, v.version, v.tag, v.created_ts)
        log.info("config v%d saved (%s, %s)", v.version, v.source, v.tag)
        return self._loaded

    @property
    def current(self) -> LoadedParameters:
        if self._loaded is None:
            raise RuntimeError("parameters not loaded")
        return self._loaded

    @property
    def params(self) -> ParameterSet:
        return self.current.params
