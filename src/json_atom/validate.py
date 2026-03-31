"""Delta document structural validation.

Implements validation per JSON Atom v0 spec Section 4, 6, and Appendix A (JSON Schema).
"""

from __future__ import annotations

from typing import Any

from json_atom.models import ValidationResult

# Fields defined by the spec for the delta envelope
_ENVELOPE_REQUIRED = {"format", "version", "operations"}

# Known operation types
_VALID_OPS = {"add", "remove", "replace"}


def validate_delta(delta: Any) -> ValidationResult:
    """Validate the structural correctness of a JSON Atom document.

    Pure structural check — does NOT validate path well-formedness,
    filter semantics, or value types beyond what's required by the spec.

    Returns ValidationResult with valid=True if the delta is structurally correct,
    or valid=False with a list of error messages.
    """
    errors: list[str] = []

    # Must be a dict (JSON object)
    if not isinstance(delta, dict):
        errors.append(f"Delta must be a JSON object, got {type(delta).__name__}")
        return ValidationResult(valid=False, errors=tuple(errors))

    # Required field: format
    if "format" not in delta:
        errors.append("Missing required field: 'format'")
    elif delta["format"] != "json-atom":
        errors.append(f"Invalid format: expected 'json-atom', got {delta['format']!r}")

    # Required field: version
    if "version" not in delta:
        errors.append("Missing required field: 'version'")
    elif not isinstance(delta["version"], int) or isinstance(delta["version"], bool):
        errors.append(f"Invalid version: expected integer, got {type(delta['version']).__name__}")

    # Required field: operations
    if "operations" not in delta:
        errors.append("Missing required field: 'operations'")
    elif not isinstance(delta["operations"], list):
        errors.append(f"Invalid operations: expected array, got {type(delta['operations']).__name__}")
    else:
        # Validate each operation
        for i, op in enumerate(delta["operations"]):
            _validate_operation(op, i, errors)

    return ValidationResult(valid=len(errors) == 0, errors=tuple(errors))


def _validate_operation(op: Any, index: int, errors: list[str]) -> None:
    """Validate a single operation object."""
    prefix = f"operations[{index}]"

    if not isinstance(op, dict):
        errors.append(f"{prefix}: operation must be a JSON object, got {type(op).__name__}")
        return

    # Required: op
    if "op" not in op:
        errors.append(f"{prefix}: missing required field 'op'")
    elif op["op"] not in _VALID_OPS:
        errors.append(f"{prefix}: invalid op {op['op']!r}, must be one of: add, remove, replace")

    # Required: path
    if "path" not in op:
        errors.append(f"{prefix}: missing required field 'path'")
    elif not isinstance(op["path"], str):
        errors.append(f"{prefix}: 'path' must be a string, got {type(op['path']).__name__}")

    # Op-specific field rules (spec Section 6.1-6.3)
    op_type = op.get("op")

    if op_type == "add":
        if "value" not in op:
            errors.append(f"{prefix}: 'add' operation requires 'value'")
        if "oldValue" in op:
            errors.append(f"{prefix}: 'add' operation must not include 'oldValue'")

    elif op_type == "remove":
        if "value" in op:
            errors.append(f"{prefix}: 'remove' operation must not include 'value'")
        # Note: oldValue is OPTIONAL on remove per spec (needed for reversibility, but not required)

    elif op_type == "replace":
        if "value" not in op:
            errors.append(f"{prefix}: 'replace' operation requires 'value'")
        # Note: oldValue is OPTIONAL on replace per spec
