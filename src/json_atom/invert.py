"""Compute the inverse of a reversible JSON Atom document.

Implements Section 9 (Reversibility) of the JSON Atom v0 specification.
"""

from __future__ import annotations

from typing import Any

from json_atom.apply import apply_delta
from json_atom.errors import InvertError
from json_atom.models import _DELTA_SPEC_KEYS, _OP_SPEC_KEYS, Delta, Operation
from json_atom.validate import validate_delta


def invert_delta(delta: Delta) -> Delta:
    """Compute the inverse of a reversible delta.

    The inverse delta, when applied to the target document, recovers the source.

    Requires all ``replace`` and ``remove`` operations to have ``oldValue``.
    Preserves extension properties at both envelope and operation levels.

    Raises InvertError if the delta is not reversible or structurally invalid.
    """
    # Validate structure first
    result = validate_delta(delta)
    if not result.valid:
        raise InvertError(f"Invalid delta: {'; '.join(result.errors)}")

    operations = delta["operations"]

    # Check reversibility: replace/remove need oldValue, copy needs value
    for i, op in enumerate(operations):
        op_type = op["op"]
        if op_type in ("replace", "remove") and "oldValue" not in op:
            raise InvertError(f"operations[{i}]: '{op_type}' operation missing 'oldValue' (required for inversion)")
        if op_type == "copy" and "value" not in op:
            raise InvertError(f"operations[{i}]: 'copy' operation missing 'value' (required for inversion)")

    # Build inverted operations in reverse order (spec Section 9.2)
    inverted_ops: list[Operation] = []
    for op in reversed(operations):
        inverted_ops.append(_invert_operation(op))

    # Build the inverse delta, preserving envelope-level extensions
    inverse: dict[str, Any] = {}
    for key, value in delta.items():
        if key not in _DELTA_SPEC_KEYS:
            inverse[key] = value
    inverse["format"] = delta["format"]
    inverse["version"] = delta["version"]
    inverse["operations"] = inverted_ops

    return Delta(inverse)


def _invert_operation(op: Operation) -> Operation:
    """Invert a single operation, preserving extension properties.

    Transformation rules (spec Section 9.2):
      add(path, value)              -> remove(path, oldValue=value)
      remove(path, oldValue)        -> add(path, value=oldValue)
      replace(path, value, oldValue) -> replace(path, value=oldValue, oldValue=value)
    """
    op_type = op["op"]
    inverted: dict[str, Any] = {}

    # Copy extension properties (everything not in the spec-defined set)
    for key, value in op.items():
        if key not in _OP_SPEC_KEYS:
            inverted[key] = value

    # Set the spec fields based on the inversion rules
    inverted["op"] = _inverted_op_type(op_type)
    inverted["path"] = op["path"]

    if op_type == "add":
        # add -> remove, with oldValue = original value
        inverted["oldValue"] = op["value"]

    elif op_type == "remove":
        # remove -> add, with value = original oldValue
        inverted["value"] = op["oldValue"]

    elif op_type == "replace":
        # replace -> replace, swap value and oldValue
        inverted["value"] = op["oldValue"]
        inverted["oldValue"] = op["value"]

    elif op_type == "move":
        # move(from, path) -> move(from=path, path=from)
        inverted["from"] = op["path"]
        inverted["path"] = op["from"]

    elif op_type == "copy":
        # copy(from, path, value) -> remove(path, oldValue=value)
        inverted["op"] = "remove"
        inverted["oldValue"] = op["value"]

    return Operation(inverted)


def _inverted_op_type(op_type: str) -> str:
    """Return the inverted operation type."""
    if op_type == "add":
        return "remove"
    if op_type == "remove":
        return "add"
    if op_type == "copy":
        return "remove"
    return op_type  # replace and move stay the same


def revert_delta(obj: Any, delta: Delta) -> Any:
    """Revert a delta by computing the inverse and applying it.

    Convenience wrapper: equivalent to `apply_delta(obj, invert_delta(delta))`.

    Raises InvertError if the delta is not reversible.
    Raises ApplyError if the inverse cannot be applied.
    """
    inverse = invert_delta(delta)
    return apply_delta(obj, inverse)
