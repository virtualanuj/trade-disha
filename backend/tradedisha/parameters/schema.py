"""Describes every tunable parameter for the editor: kind, limits, choices and help text."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from tradedisha.parameters.model import ParameterSet

Kind = Literal["number", "integer", "choice", "time"]


@dataclass(frozen=True)
class FieldSpec:
    path: str  # "bias.entry_threshold", "signal.expiry_points.NIFTY.target"
    group: str  # "bias"
    key: str  # the path without its group
    kind: Kind
    help: str
    ge: float | None = None
    gt: float | None = None
    le: float | None = None
    lt: float | None = None
    choices: list[str] | None = None


def _limits(info: FieldInfo) -> dict[str, float]:
    out: dict[str, float] = {}
    for m in info.metadata:  # pydantic keeps each bound as an object with that attribute
        for name in ("ge", "gt", "le", "lt"):
            bound = getattr(m, name, None)
            if isinstance(bound, int | float):
                out[name] = float(bound)
    return out


def _spec(path: str, info: FieldInfo, help_text: str) -> FieldSpec:
    group, key = path.split(".", 1)
    annotation: Any = info.annotation
    if get_origin(annotation) is Literal:
        return FieldSpec(path, group, key, "choice", help_text, choices=list(get_args(annotation)))
    if annotation is time:
        return FieldSpec(path, group, key, "time", help_text)
    kind: Kind = "integer" if annotation is int else "number"
    lim = _limits(info)
    return FieldSpec(
        path,
        group,
        key,
        kind,
        help_text,
        lim.get("ge"),
        lim.get("gt"),
        lim.get("le"),
        lim.get("lt"),
    )


def _walk(model: BaseModel, prefix: str, inherited: str) -> list[FieldSpec]:
    out: list[FieldSpec] = []
    for name, info in type(model).model_fields.items():
        value = getattr(model, name)
        path = f"{prefix}.{name}" if prefix else name
        help_text = info.description or inherited
        if isinstance(value, BaseModel):
            out += _walk(value, path, help_text)
        elif isinstance(value, dict):
            for k, item in value.items():
                out += _walk(item, f"{path}.{k}", help_text)
        else:
            out.append(_spec(path, info, help_text))
    return out


def describe(params: ParameterSet) -> list[FieldSpec]:
    """One entry per editable value, in the order the groups and fields are declared.

    Takes the set in force because some fields are keyed by data (expiry points per index).
    """
    return _walk(params, "", "")
