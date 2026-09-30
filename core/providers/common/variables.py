"""Common variable-name resolution helpers."""

from collections.abc import Iterable, Mapping
from typing import TypeVar


T = TypeVar("T")


def resolve_variable_name(
    available_names: Iterable[str], aliases: Iterable[str]
) -> str | None:
    """Return the first available name matching the ordered aliases."""

    names_by_casefold = {name.casefold(): name for name in available_names}
    return next(
        (names_by_casefold[name.casefold()] for name in aliases if name.casefold() in names_by_casefold),
        None,
    )


def resolve_variable(
    variables: Mapping[str, T], aliases: Iterable[str]
) -> T | None:
    """Return a variable by a case-insensitive ordered list of aliases."""

    name = resolve_variable_name(variables.keys(), aliases)
    return None if name is None else variables[name]


def resolve_lat_lon_names(available_names: Iterable[str]) -> tuple[str | None, str | None]:
    """Resolve conventional latitude/longitude coordinate variable names."""

    names = tuple(available_names)
    return (
        resolve_variable_name(names, ("latitude", "lat")),
        resolve_variable_name(names, ("longitude", "lon")),
    )
