"""Internal identity resolution for array comparison.

Determines how array elements are matched during diff and compare:
by key, by value, by index, or by custom callable.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from json_atom._utils import json_equal
from json_atom.errors import DiffError
from json_atom.path import _NESTED_PATH_RE


@dataclass(frozen=True, slots=True)
class IdentityResolver:
    """Custom identity resolution for array elements.

    The ``property`` name appears in filter paths: ``[?(@.{property}==...)]``.
    The ``resolve`` callable extracts the identity value from an element.

    .. important::

        The value returned by ``resolve`` **must** match the value actually
        stored under ``elem[property]`` for that element.  JSON Atom applies
        keyed-array filters by testing ``elem[property] == literal``, so if
        the resolver returns a synthetic or composite value that is not
        literally stored on the element, the generated delta paths will not
        match during ``apply_delta`` / ``resolve_path``.

    Example::

        # Simple key: use the ``id`` field directly
        IdentityResolver("id", lambda e: e["id"])

        # Validation: coerce to int, ensuring consistency
        # (only safe when the stored value round-trips through int)
        IdentityResolver("id", lambda e: int(e["id"]))
    """

    property: str
    resolve: Callable[[Any], Any]


# All valid forms for specifying an identity key
type IdentityKey = str | IdentityResolver | tuple[str, Callable[[Any], Any]]

# Full mapping: path (exact or regex) → identity key
type ArrayIdentityKeys = dict[str | re.Pattern[str], IdentityKey]


@dataclass(frozen=True, slots=True)
class _ResolvedIdentity:
    """The resolved identity model for a specific array.

    Internal type — not part of the public API.
    """

    mode: Literal["$index", "$value", "key"]
    key_property: str | None = None
    resolver: Callable[[Any], Any] | None = None


def resolve_identity(
    prop_path: list[str],
    array_identity_keys: ArrayIdentityKeys,
) -> _ResolvedIdentity:
    """Determine the identity model for an array at the given property path.

    Matches against exact string keys first, then regex patterns
    (in dict insertion order). Falls back to ``$index`` if no match.
    """
    path_str = ".".join(prop_path)

    # 1. Try exact string matches first
    for key, value in array_identity_keys.items():
        if isinstance(key, str) and key == path_str:
            return _normalize_identity_value(value)

    # 2. Try regex pattern matches (insertion order)
    for key, value in array_identity_keys.items():
        if isinstance(key, re.Pattern) and key.search(path_str):
            return _normalize_identity_value(value)

    # 3. Default: index-based
    return _ResolvedIdentity(mode="$index")


def _normalize_identity_value(value: IdentityKey) -> _ResolvedIdentity:
    """Normalize the various forms of identity key values."""
    if isinstance(value, str):
        if value == "$index":
            return _ResolvedIdentity(mode="$index")
        if value == "$value":
            return _ResolvedIdentity(mode="$value")
        return _ResolvedIdentity(mode="key", key_property=value)

    if isinstance(value, IdentityResolver):
        return _ResolvedIdentity(
            mode="key",
            key_property=value.property,
            resolver=value.resolve,
        )

    if isinstance(value, tuple) and len(value) == 2:
        prop_name, resolver_fn = value
        if not isinstance(prop_name, str) or not callable(resolver_fn):
            raise DiffError(
                f"Tuple identity key must be (str, Callable), "
                f"got ({type(prop_name).__name__}, {type(resolver_fn).__name__})"
            )
        return _ResolvedIdentity(
            mode="key",
            key_property=prop_name,
            resolver=resolver_fn,
        )

    raise DiffError(
        f"Invalid identity key value: {value!r}. "
        f"Expected str, (str, Callable), or IdentityResolver."
    )


_SENTINEL = object()


def _resolve_nested(elem: Any, key_property: str) -> Any:
    """Resolve a possibly-nested dot path on a dict element.

    Returns ``_SENTINEL`` if any segment is missing.
    For non-nested keys, falls back to a simple dict lookup.
    """
    if not isinstance(elem, dict):
        return _SENTINEL
    is_nested = "." in key_property and _NESTED_PATH_RE.match(key_property) is not None
    if not is_nested:
        return elem.get(key_property, _SENTINEL)
    current: Any = elem
    for seg in key_property.split("."):
        if not isinstance(current, dict) or seg not in current:
            return _SENTINEL
        current = current[seg]
    return current


def extract_identity(
    elem: Any,
    key_property: str,
    resolver: Callable[[Any], Any] | None,
) -> Any:
    """Extract the identity value from an array element.

    Uses the custom resolver if provided, otherwise reads the key property
    directly from the element dict.  Supports nested dot paths like
    ``positionNumber.value`` → ``elem["positionNumber"]["value"]``.

    The returned value must be a JSON scalar (str, int, float, bool, or None)
    suitable for use in filter paths.

    Raises:
        DiffError: If the element is missing the key property or the resolver
            raises an exception or returns a non-scalar value.
    """
    if resolver is not None:
        try:
            value = resolver(elem)
        except Exception as exc:
            raise DiffError(
                f"Identity resolver for '{key_property}' failed on element {elem!r}: {exc}"
            ) from exc
        # Verify the element has the key property and that the stored value
        # matches the resolved value — apply_delta matches filter paths via
        # the key property, so a mismatch would produce unapplyable deltas.
        stored = _resolve_nested(elem, key_property)
        if stored is _SENTINEL:
            raise DiffError(
                f"Resolver for '{key_property}' returned {value!r} but element "
                f"is missing identity path '{key_property}': {elem!r}"
            )
        if not json_equal(stored, value):
            raise DiffError(
                f"Resolver for '{key_property}' returned {value!r} but "
                f"stored value at '{key_property}' is {stored!r} — filter path would not match"
            )
    else:
        stored = _resolve_nested(elem, key_property)
        if stored is _SENTINEL:
            raise DiffError(f"Array element missing identity key '{key_property}': {elem!r}")
        value = stored

    if not isinstance(value, (str, int, float, bool, type(None))):
        raise DiffError(
            f"Identity value for '{key_property}' must be a JSON scalar, "
            f"got {type(value).__name__}: {value!r}"
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise DiffError(
            f"Identity value for '{key_property}' must be a finite number, "
            f"got {value!r}"
        )
    return value
