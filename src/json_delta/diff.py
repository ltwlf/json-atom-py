"""Compute a JSON Delta document from two objects.

Non-normative — the spec defines what a delta looks like, not how to produce one.
The key invariant: apply(source, diff(source, target)) == target.
"""

from __future__ import annotations

import math
from typing import Any

from json_delta._identity import (
    ArrayIdentityKeys,
    _ResolvedIdentity,
    extract_identity,
    resolve_identity,
)
from json_delta._utils import json_equal, make_hashable, should_exclude_path, validate_json_value
from json_delta.errors import DiffError
from json_delta.models import (
    Delta,
    IndexSegment,
    KeyFilterSegment,
    Operation,
    PropertySegment,
    ValueFilterSegment,
)
from json_delta.path import build_path

type _Segment = PropertySegment | IndexSegment | KeyFilterSegment | ValueFilterSegment


def diff_delta(
    old_obj: Any,
    new_obj: Any,
    *,
    array_identity_keys: ArrayIdentityKeys | None = None,
    exclude_keys: set[str] | None = None,
    exclude_paths: set[str] | None = None,
    reversible: bool = True,
) -> Delta:
    """Compute a JSON Delta between two objects.

    Args:
        old_obj: The source document.
        new_obj: The target document.
        array_identity_keys: Mapping from dotted property path (or regex
            pattern) to identity key.  Values can be:

            - A string key name (e.g., ``"id"``) — key-based identity.
            - ``"$value"`` — value-based identity for primitive arrays.
            - ``"$index"`` — index-based identity (also the default).
            - A ``(str, Callable)`` tuple — ``(key_property, resolver)``.
            - An :class:`IdentityResolver` instance.

            Dict keys can be exact strings or compiled ``re.Pattern``
            objects for regex-based routing.
        exclude_keys: Property names to skip during comparison at any depth.
            Matching keys are invisible to the diff engine — they produce no
            operations regardless of whether they differ, are added, or removed.
        exclude_paths: Dotted property paths to skip during comparison at a
            specific depth.  For example, ``{"user.cache"}`` skips the ``cache``
            property only when nested under ``user``, while ``exclude_keys``
            would skip ``cache`` at every depth.
        reversible: If True (default), include ``oldValue`` on replace/remove.

    Returns:
        A :class:`Delta` document with typed :class:`Operation` instances.

    Raises:
        DiffError: If the input contains non-JSON values.
    """
    validate_json_value(old_obj, "old_obj")
    validate_json_value(new_obj, "new_obj")

    _keys = array_identity_keys or {}
    _exclude: frozenset[str] = frozenset(exclude_keys) if exclude_keys else frozenset()
    _exclude_paths: frozenset[str] = frozenset(exclude_paths) if exclude_paths else frozenset()
    operations: list[Operation] = []
    _diff_values(old_obj, new_obj, [], [], _keys, _exclude, _exclude_paths, reversible, operations)

    return Delta({
        "format": "json-delta",
        "version": 1,
        "operations": operations,
    })


# ---------------------------------------------------------------------------
# Recursive comparison
# ---------------------------------------------------------------------------


def _diff_values(
    old: Any,
    new: Any,
    segments: list[_Segment],
    prop_path: list[str],
    identity_keys: ArrayIdentityKeys,
    exclude: frozenset[str],
    exclude_paths: frozenset[str],
    reversible: bool,
    operations: list[Operation],
) -> None:
    """Recursively compare two values and emit operations."""
    if json_equal(old, new):
        return

    old_is_dict = isinstance(old, dict) and not isinstance(old, bool)
    new_is_dict = isinstance(new, dict) and not isinstance(new, bool)

    old_is_list = isinstance(old, list)
    new_is_list = isinstance(new, list)

    if old_is_dict and new_is_dict:
        _diff_objects(old, new, segments, prop_path, identity_keys, exclude, exclude_paths, reversible, operations)
    elif old_is_list and new_is_list:
        _diff_arrays(old, new, segments, prop_path, identity_keys, exclude, exclude_paths, reversible, operations)
    else:
        # Type change or scalar difference → single replace
        _emit_replace(old, new, segments, reversible, operations)


def _diff_objects(
    old: dict[str, Any],
    new: dict[str, Any],
    segments: list[_Segment],
    prop_path: list[str],
    identity_keys: ArrayIdentityKeys,
    exclude: frozenset[str],
    exclude_paths: frozenset[str],
    reversible: bool,
    operations: list[Operation],
) -> None:
    """Compare two objects and emit add/remove/replace operations."""
    all_keys = sorted((set(old.keys()) | set(new.keys())) - exclude)

    for key in all_keys:
        if should_exclude_path(prop_path, key, exclude_paths):
            continue

        seg = PropertySegment(name=key)
        child_segments = [*segments, seg]
        child_prop_path = [*prop_path, key]

        if key in old and key not in new:
            _emit_remove(old[key], child_segments, reversible, operations)
        elif key not in old and key in new:
            _emit_add(new[key], child_segments, operations)
        else:
            _diff_values(
                old[key], new[key], child_segments, child_prop_path,
                identity_keys, exclude, exclude_paths, reversible, operations,
            )


def _diff_arrays(
    old: list[Any],
    new: list[Any],
    segments: list[_Segment],
    prop_path: list[str],
    identity_keys: ArrayIdentityKeys,
    exclude: frozenset[str],
    exclude_paths: frozenset[str],
    reversible: bool,
    operations: list[Operation],
) -> None:
    """Compare two arrays using the appropriate identity model."""
    identity = resolve_identity(prop_path, identity_keys)

    if identity.mode == "$index":
        _diff_arrays_index(old, new, segments, prop_path, identity_keys, exclude, exclude_paths, reversible, operations)
    elif identity.mode == "$value":
        _diff_arrays_value(old, new, segments, reversible, operations)
    else:
        _diff_arrays_keyed(
            old, new, segments, prop_path, identity_keys, identity, exclude, exclude_paths, reversible, operations,
        )


# ---------------------------------------------------------------------------
# Index-based array comparison
# ---------------------------------------------------------------------------


def _diff_arrays_index(
    old: list[Any],
    new: list[Any],
    segments: list[_Segment],
    prop_path: list[str],
    identity_keys: ArrayIdentityKeys,
    exclude: frozenset[str],
    exclude_paths: frozenset[str],
    reversible: bool,
    operations: list[Operation],
) -> None:
    """Compare arrays by positional index."""
    min_len = min(len(old), len(new))

    # Compare shared positions
    for i in range(min_len):
        seg = IndexSegment(index=i)
        child_segments = [*segments, seg]
        _diff_values(
            old[i], new[i], child_segments, prop_path,
            identity_keys, exclude, exclude_paths, reversible, operations,
        )

    # Elements removed from the end (remove from highest index first)
    for i in range(len(old) - 1, min_len - 1, -1):
        seg = IndexSegment(index=i)
        child_segments = [*segments, seg]
        _emit_remove(old[i], child_segments, reversible, operations)

    # Elements added at the end
    for i in range(min_len, len(new)):
        seg = IndexSegment(index=i)
        child_segments = [*segments, seg]
        _emit_add(new[i], child_segments, operations)


# ---------------------------------------------------------------------------
# Key-based array comparison
# ---------------------------------------------------------------------------


def _diff_arrays_keyed(
    old: list[Any],
    new: list[Any],
    segments: list[_Segment],
    prop_path: list[str],
    identity_keys: ArrayIdentityKeys,
    identity: _ResolvedIdentity,
    exclude: frozenset[str],
    exclude_paths: frozenset[str],
    reversible: bool,
    operations: list[Operation],
) -> None:
    """Compare arrays by a key property on each element."""
    key_property = identity.key_property
    if key_property is None:
        raise DiffError("Internal error: key_property is None for mode='key' in _diff_arrays_keyed")
    resolver = identity.resolver

    path_str = build_path(segments)

    # Build lookup maps, caching (elem, key_val) to avoid re-calling the resolver.
    old_by_key: dict[Any, tuple[Any, Any]] = {}
    for elem in old:
        key_val = extract_identity(elem, key_property, resolver)
        hashable_key = make_hashable(key_val)
        if hashable_key in old_by_key:
            raise DiffError(
                f"Duplicate identity '{key_property}=={key_val!r}' in old array at {path_str}"
            )
        old_by_key[hashable_key] = (elem, key_val)

    new_by_key: dict[Any, tuple[Any, Any]] = {}
    new_key_order: list[Any] = []
    for elem in new:
        key_val = extract_identity(elem, key_property, resolver)
        hashable_key = make_hashable(key_val)
        if hashable_key in new_by_key:
            raise DiffError(
                f"Duplicate identity '{key_property}=={key_val!r}' in new array at {path_str}"
            )
        new_by_key[hashable_key] = (elem, key_val)
        new_key_order.append(hashable_key)

    # Removed elements (in old but not in new)
    for hashable_key, (old_elem, key_val) in old_by_key.items():
        if hashable_key not in new_by_key:
            filter_seg = KeyFilterSegment(property=key_property, value=key_val)
            child_segments = [*segments, filter_seg]
            _emit_remove(old_elem, child_segments, reversible, operations)

    # Shared elements — recurse into properties for deep diffs
    for hashable_key in new_key_order:
        if hashable_key in old_by_key:
            old_elem, key_val = old_by_key[hashable_key]
            new_elem = new_by_key[hashable_key][0]
            if not json_equal(old_elem, new_elem):
                filter_seg = KeyFilterSegment(property=key_property, value=key_val)
                _diff_keyed_element(
                    old_elem, new_elem, [*segments, filter_seg], prop_path,
                    identity_keys, exclude, exclude_paths, reversible, operations,
                )

    # Added elements (in new but not in old)
    for hashable_key in new_key_order:
        if hashable_key not in old_by_key:
            new_elem, key_val = new_by_key[hashable_key]
            filter_seg = KeyFilterSegment(property=key_property, value=key_val)
            child_segments = [*segments, filter_seg]
            _emit_add(new_elem, child_segments, operations)


def _diff_keyed_element(
    old_elem: dict[str, Any],
    new_elem: dict[str, Any],
    segments: list[_Segment],
    prop_path: list[str],
    identity_keys: ArrayIdentityKeys,
    exclude: frozenset[str],
    exclude_paths: frozenset[str],
    reversible: bool,
    operations: list[Operation],
) -> None:
    """Diff two keyed-array elements, emitting property-level operations."""
    all_keys = sorted((set(old_elem.keys()) | set(new_elem.keys())) - exclude)

    for key in all_keys:
        if should_exclude_path(prop_path, key, exclude_paths):
            continue

        seg = PropertySegment(name=key)
        child_segments = [*segments, seg]
        child_prop_path = [*prop_path, key]

        if key in old_elem and key not in new_elem:
            _emit_remove(old_elem[key], child_segments, reversible, operations)
        elif key not in old_elem and key in new_elem:
            _emit_add(new_elem[key], child_segments, operations)
        else:
            _diff_values(
                old_elem[key], new_elem[key], child_segments, child_prop_path,
                identity_keys, exclude, exclude_paths, reversible, operations,
            )


# ---------------------------------------------------------------------------
# Value-based array comparison
# ---------------------------------------------------------------------------


def _diff_arrays_value(
    old: list[Any],
    new: list[Any],
    segments: list[_Segment],
    reversible: bool,
    operations: list[Operation],
) -> None:
    """Compare arrays by element value (for primitive arrays).

    Value filters require each element to be unique — duplicate values
    produce ambiguous paths that ``apply_delta`` cannot resolve.

    Raises:
        DiffError: If either array contains duplicate or non-scalar values.
    """
    path_str = build_path(segments)
    _check_value_scalars(old, "old", path_str)
    _check_value_scalars(new, "new", path_str)
    _check_value_duplicates(old, "old", path_str)
    _check_value_duplicates(new, "new", path_str)

    # Find removed values (in old but not in new)
    for old_val in old:
        found = any(json_equal(old_val, new_val) for new_val in new)
        if not found:
            filter_seg = ValueFilterSegment(value=old_val)
            child_segments = [*segments, filter_seg]
            _emit_remove(old_val, child_segments, reversible, operations)

    # Find added values (in new but not in old)
    for new_val in new:
        found = any(json_equal(new_val, old_val) for old_val in old)
        if not found:
            filter_seg = ValueFilterSegment(value=new_val)
            child_segments = [*segments, filter_seg]
            _emit_add(new_val, child_segments, operations)


# ---------------------------------------------------------------------------
# Operation emission
# ---------------------------------------------------------------------------


def _emit_replace(
    old_val: Any,
    new_val: Any,
    segments: list[_Segment],
    reversible: bool,
    operations: list[Operation],
) -> None:
    """Emit a replace operation."""
    path = build_path(segments)
    if reversible:
        operations.append(Operation(op="replace", path=path, value=new_val, oldValue=old_val))
    else:
        operations.append(Operation(op="replace", path=path, value=new_val))


def _emit_add(
    value: Any,
    segments: list[_Segment],
    operations: list[Operation],
) -> None:
    """Emit an add operation."""
    path = build_path(segments)
    operations.append(Operation(op="add", path=path, value=value))


def _emit_remove(
    old_val: Any,
    segments: list[_Segment],
    reversible: bool,
    operations: list[Operation],
) -> None:
    """Emit a remove operation."""
    path = build_path(segments)
    if reversible:
        operations.append(Operation(op="remove", path=path, oldValue=old_val))
    else:
        operations.append(Operation(op="remove", path=path))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_value_scalars(arr: list[Any], label: str, path_str: str) -> None:
    """Raise DiffError if a $value array contains non-scalar elements.

    Value filter paths use literal comparisons (``[?(@=='x')]``), so elements
    must be JSON scalars (str, int, float, bool, None).  Dicts and lists
    cannot appear in value filter paths.
    """
    for val in arr:
        if isinstance(val, (dict, list)):
            raise DiffError(
                f"Non-scalar value {type(val).__name__} in {label} array at {path_str}; "
                f"$value identity requires scalar elements"
            )
        if isinstance(val, float) and not math.isfinite(val):
            raise DiffError(
                f"Non-finite float {val!r} in {label} array at {path_str}; "
                f"$value identity requires finite scalars"
            )


def _check_value_duplicates(arr: list[Any], label: str, path_str: str) -> None:
    """Raise DiffError if a $value array contains duplicate values.

    Value filters require each element to match exactly one position,
    so duplicates make the resulting delta paths ambiguous.

    Uses ``make_hashable`` for O(n) duplicate detection while keeping
    bool/int distinct (JSON semantics).
    """
    seen: set[Any] = set()
    for val in arr:
        key = make_hashable(val)
        if key in seen:
            raise DiffError(
                f"Duplicate value {val!r} in {label} array at {path_str}; "
                f"$value identity requires unique elements"
            )
        seen.add(key)

