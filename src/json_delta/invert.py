"""Compute the inverse of a reversible JSON Delta document.

Implements Section 9 (Reversibility) of the JSON Delta v0 specification.
"""

from __future__ import annotations

from typing import Any

from json_delta.apply import apply_delta
from json_delta.errors import InvertError
from json_delta.models import Delta, Operation
from json_delta.validate import validate_delta

# Fields defined by the spec for operations — everything else is an extension
_OP_SPEC_FIELDS = {"op", "path", "value", "oldValue"}

# Fields defined by the spec for the envelope — everything else is an extension
_ENVELOPE_SPEC_FIELDS = {"format", "version", "operations"}


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

    # Check reversibility: all replace and remove ops must have oldValue
    for i, op in enumerate(operations):
        op_type = op["op"]
        if op_type in ("replace", "remove") and "oldValue" not in op:
            raise InvertError(f"operations[{i}]: '{op_type}' operation missing 'oldValue' (required for inversion)")

    # Build inverted operations in reverse order (spec Section 9.2)
    inverted_ops: list[Operation] = []
    for op in reversed(operations):
        inverted_ops.append(_invert_operation(op))

    # Build the inverse delta, preserving envelope-level extensions
    inverse: dict[str, Any] = {}
    for key, value in delta.items():
        if key not in _ENVELOPE_SPEC_FIELDS:
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
        if key not in _OP_SPEC_FIELDS:
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

    return Operation(inverted)


def _inverted_op_type(op_type: str) -> str:
    """Return the inverted operation type."""
    if op_type == "add":
        return "remove"
    if op_type == "remove":
        return "add"
    return op_type  # replace stays replace


def revert_delta(obj: Any, delta: Delta) -> Any:
    """Revert a delta by computing the inverse and applying it.

    Convenience wrapper: equivalent to `apply_delta(obj, invert_delta(delta))`.

    Raises InvertError if the delta is not reversible.
    Raises ApplyError if the inverse cannot be applied.
    """
    inverse = invert_delta(delta)
    return apply_delta(obj, inverse)
