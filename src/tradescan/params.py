"""Declared, range-checked parameters.

A parameter is declared once, on the dataclass field that holds it (`period: int = param(20, ...)`),
so its default, allowed range and label live together. The API publishes the declarations, the web
UI builds its forms from them, and `with_overrides` applies validated values for a single run.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass, replace
from enum import StrEnum
from typing import Any, TypeVar

T = TypeVar("T")

ParamValue = int | float | tuple[int, ...] | tuple[float, ...] | Mapping[str, float]
Overrides = Mapping[str, Any]  # parameter name -> raw value, validated by `with_overrides`
GroupOverrides = Mapping[str, Overrides]  # owner (settings section or signal name) -> overrides

_KEY = "tradescan.param"


class ParamKind(StrEnum):
    INT = "int"
    FLOAT = "float"
    INT_LIST = "int_list"
    FLOAT_LIST = "float_list"
    WEIGHTS = "weights"  # name -> float; overrides are merged into the defaults


@dataclass(frozen=True)
class _Declaration:
    kind: ParamKind
    minimum: float
    maximum: float
    step: float
    label: str
    unit: str
    help: str
    keys: tuple[str, ...] | None  # allowed WEIGHTS keys; None means any


@dataclass(frozen=True)
class ParamSpec:
    name: str
    kind: ParamKind
    default: ParamValue
    minimum: float
    maximum: float
    step: float
    label: str
    unit: str = ""
    help: str = ""
    keys: tuple[str, ...] | None = None


def _kind_of(default: Any) -> ParamKind:
    if isinstance(default, Mapping):
        return ParamKind.WEIGHTS
    if isinstance(default, tuple):
        return ParamKind.INT_LIST if all(isinstance(item, int) for item in default) else ParamKind.FLOAT_LIST
    return ParamKind.INT if isinstance(default, int) else ParamKind.FLOAT


def param(
    default: Any,
    *,
    minimum: float,
    maximum: float,
    step: float,
    label: str,
    unit: str = "",
    help: str = "",
    keys: Sequence[str] | None = None,
) -> Any:
    """A dataclass field holding an adjustable parameter. The kind follows the default's type."""
    declaration = _Declaration(
        kind=_kind_of(default),
        minimum=minimum,
        maximum=maximum,
        step=step,
        label=label,
        unit=unit,
        help=help,
        keys=tuple(keys) if keys is not None else None,
    )
    metadata = {_KEY: declaration}
    if isinstance(default, Mapping):
        frozen = dict(default)
        return field(default_factory=lambda: dict(frozen), metadata=metadata)
    return field(default=default, metadata=metadata)


def _declarations(obj: Any) -> dict[str, tuple[_Declaration, Any]]:
    """Declared parameters of a dataclass (instance or class) with their field default."""
    if not is_dataclass(obj):
        return {}
    result = {}
    for item in fields(obj):
        declaration = item.metadata.get(_KEY)
        if declaration is not None:
            default = item.default_factory() if callable(item.default_factory) else item.default
            result[item.name] = (declaration, default)
    return result


def parameters_of(obj: Any) -> tuple[ParamSpec, ...]:
    """Specs of the declared parameters. For an instance, `default` is its current value."""
    instance = not isinstance(obj, type)
    return tuple(
        ParamSpec(
            name=name,
            kind=declaration.kind,
            default=getattr(obj, name) if instance else default,
            minimum=declaration.minimum,
            maximum=declaration.maximum,
            step=declaration.step,
            label=declaration.label,
            unit=declaration.unit,
            help=declaration.help,
            keys=declaration.keys,
        )
        for name, (declaration, default) in _declarations(obj).items()
    )


def _number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{where} must be a number, got {value!r}")
    return float(value)


def _whole(value: Any, where: str) -> int:
    number = _number(value, where)
    if not number.is_integer():
        raise ValueError(f"{where} must be a whole number, got {value!r}")
    return int(number)


def _in_range(value: float, declaration: _Declaration, where: str) -> None:
    if not declaration.minimum <= value <= declaration.maximum:
        raise ValueError(f"{where} must be between {declaration.minimum:g} and {declaration.maximum:g}, got {value:g}")


def _coerce(value: Any, declaration: _Declaration, current: Any, where: str) -> Any:
    kind = declaration.kind
    if kind is ParamKind.WEIGHTS:
        if not isinstance(value, Mapping):
            raise ValueError(f"{where} must be a mapping of names to numbers")
        unknown = sorted(set(value) - set(declaration.keys)) if declaration.keys is not None else []
        if unknown:
            raise ValueError(f"{where}: unknown key(s) {', '.join(unknown)}. Use: {', '.join(declaration.keys or ())}")
        merged = dict(current)
        for key, item in value.items():
            number = _number(item, f"{where}.{key}")
            _in_range(number, declaration, f"{where}.{key}")
            merged[str(key)] = number
        return merged
    if kind in (ParamKind.INT_LIST, ParamKind.FLOAT_LIST):
        items = list(value) if isinstance(value, list | tuple) else [value]
        if not items:
            raise ValueError(f"{where} needs at least one value")
        convert = _whole if kind is ParamKind.INT_LIST else _number
        result = tuple(convert(item, where) for item in items)
        for number in result:
            _in_range(number, declaration, where)
        return result
    number = _whole(value, where) if kind is ParamKind.INT else _number(value, where)
    _in_range(number, declaration, where)
    return number


def with_overrides(obj: T, values: Overrides | None, owner: str) -> T:
    """Copy of the dataclass `obj` with validated parameter values.

    Only declared parameters can be changed; anything else (paths, names) is refused. Cross-field
    rules live in the dataclass's `__post_init__`, which runs on the copy.
    """
    if not values:
        return obj
    declarations = _declarations(obj)
    unknown = sorted(set(values) - set(declarations))
    if unknown:
        known = ", ".join(declarations) or "none"
        raise ValueError(f"{owner}: unknown or fixed parameter(s) {', '.join(unknown)}. Adjustable: {known}")
    changes = {
        name: _coerce(value, declarations[name][0], getattr(obj, name), f"{owner}.{name}")
        for name, value in values.items()
    }
    return replace(obj, **changes)  # type: ignore[type-var]


def check_values(obj: Any, name: str, values: Sequence[Any], owner: str) -> tuple[int | float, ...]:
    """Validated values for one declared single-number parameter of `obj`, e.g. the points of a sweep.

    Only the declared range and kind are checked; cross-field rules need the other values and are left
    to `with_overrides`. Lists and weights are refused.
    """
    declarations = _declarations(obj)
    if name not in declarations:
        known = ", ".join(declarations) or "none"
        raise ValueError(f"{owner}: unknown or fixed parameter '{name}'. Adjustable: {known}")
    declaration = declarations[name][0]
    if declaration.kind not in (ParamKind.INT, ParamKind.FLOAT):
        raise ValueError(f"{owner}.{name} is not a single number")
    return tuple(_coerce(value, declaration, None, f"{owner}.{name}") for value in values)


def validate(obj: Any, owner: str) -> None:
    """Check that every declared parameter's current value is inside its range (e.g. values from a file)."""
    for name, (declaration, _) in _declarations(obj).items():
        _coerce(getattr(obj, name), declaration, {}, f"{owner}.{name}")


def check_group(overrides: Mapping[str, Any], known: Sequence[str], what: str) -> None:
    """Refuse keys that name nothing known, e.g. overrides for a signal that does not exist."""
    unknown = sorted(set(overrides) - set(known))
    if unknown:
        raise ValueError(f"Parameters given for unknown {what}: {', '.join(unknown)}")
