"""JSON Atom Path parsing, building, and filter literal handling.

Implements the path grammar from the JSON Atom v0 specification (Section 5).
See also: ABNF grammar (Appendix C), reference parser (Appendix D).
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Any

from json_atom.errors import PathError
from json_atom.models import (
    IndexSegment,
    KeyFilterSegment,
    PropertySegment,
    RootSegment,
    ValueFilterSegment,
)

# Regex for valid dot-notation property names (spec Section 5.1):
# property-name = (ALPHA / "_") *(ALPHA / DIGIT / "_")
_PROPERTY_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Regex for nested dot-notation paths: each segment is a valid property name.
# Supports nested member-access in filters per RFC 9535 (e.g. @.a.b==val).
_NESTED_PATH_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*$")

# Regex for JSON number literals (spec Section 5.1 / Appendix C):
# number-literal = ["-"] ("0" / DIGIT1 *DIGIT) ["." 1*DIGIT] [("e" / "E") ["+" / "-"] 1*DIGIT]
_NUMBER_RE = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$")


# ---------------------------------------------------------------------------
# Filter literal formatting and parsing
# ---------------------------------------------------------------------------


def format_filter_literal(value: Any) -> str:
    """Format a Python value as a canonical JSON Atom filter literal string.

    Handles: str, int, float, bool, None.
    Raises PathError for non-JSON or non-finite values.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PathError(f"Non-finite float is not a valid JSON value: {value}")
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    raise PathError(f"Cannot format as filter literal: {type(value).__name__}")


def parse_filter_literal(s: str) -> Any:
    """Parse a filter literal string into a typed Python value.

    Supports: 'string', number, true, false, null.
    Raises PathError for invalid literals.
    """
    if not s:
        raise PathError("Empty filter literal")

    # String literal: 'value'
    if s.startswith("'") and s.endswith("'") and len(s) >= 2:
        inner = s[1:-1]
        return inner.replace("''", "'")

    # Boolean literals
    if s == "true":
        return True
    if s == "false":
        return False

    # Null literal
    if s == "null":
        return None

    # Number literal — must match JSON number format exactly
    if not _NUMBER_RE.match(s):
        raise PathError(f"Invalid filter literal: {s!r}")

    if "." in s or "e" in s or "E" in s:
        return float(s)
    return int(s)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_quoted_string(s: str, start: int) -> tuple[str, int]:
    """Extract a single-quoted string starting at index `start` (after the opening quote).

    Returns (unescaped_string, index_of_closing_quote).
    Doubled single quotes ('') are unescaped to a single quote.
    """
    result: list[str] = []
    i = start
    while i < len(s):
        if s[i] == "'":
            if i + 1 < len(s) and s[i + 1] == "'":
                result.append("'")  # escaped quote
                i += 2
            else:
                return ("".join(result), i)  # closing quote
        else:
            result.append(s[i])
            i += 1
    raise PathError("Unterminated quoted string")


def _find_filter_close(path: str, start: int) -> int:
    """Find the closing ')]' of a filter expression, skipping quoted strings.

    `start` should point to the character after '[?('.
    Returns the index of ')' in ')]'.
    """
    i = start
    while i < len(path):
        if path[i] == "'":
            # Skip quoted string — find the matching close quote
            i += 1  # past opening quote
            while i < len(path):
                if path[i] == "'":
                    if i + 1 < len(path) and path[i + 1] == "'":
                        i += 2  # escaped quote
                    else:
                        i += 1  # closing quote
                        break
                else:
                    i += 1
            else:
                raise PathError("Unterminated string in filter expression")
        elif path[i] == ")" and i + 1 < len(path) and path[i + 1] == "]":
            return i
        else:
            i += 1
    raise PathError("Unterminated filter expression — missing ')]'")


def _parse_filter(inner: str) -> KeyFilterSegment | ValueFilterSegment:
    """Parse filter content after '@': e.g. '.id==42', \"['a.b']==42\", or '==value'.

    `inner` is the text between '@' and ')' (exclusive).
    """
    if inner.startswith("."):
        # Key filter with dot property: .key==val or .a.b==val (nested per RFC 9535)
        eq_pos = inner.find("==")
        if eq_pos == -1:
            raise PathError(f"Invalid filter expression: missing '==' in @{inner}")
        key = inner[1:eq_pos]
        if not key or not _NESTED_PATH_RE.match(key):
            raise PathError(f"Invalid property name in filter: {key!r}")
        literal_str = inner[eq_pos + 2 :]
        return KeyFilterSegment(property=key, value=parse_filter_literal(literal_str))

    if inner.startswith("['"):
        # Key filter with bracket property: ['dotted.key']==val
        key, close_quote_idx = _extract_quoted_string(inner, 2)  # after ['
        # After the closing quote, expect ']==' then the literal
        rest = inner[close_quote_idx + 1 :]  # from ']' onwards
        if not rest.startswith("]=="):
            raise PathError("Invalid bracket filter syntax: expected ']==' after quoted key")
        literal_str = rest[3:]  # skip ']==
        return KeyFilterSegment(property=key, value=parse_filter_literal(literal_str), literal_key=True)

    if inner.startswith("=="):
        # Value filter: ==val
        literal_str = inner[2:]
        return ValueFilterSegment(value=parse_filter_literal(literal_str))

    raise PathError(f"Invalid filter expression: @{inner}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_path(
    path: str,
) -> list[RootSegment | PropertySegment | IndexSegment | KeyFilterSegment | ValueFilterSegment]:
    """Parse a JSON Atom Path string into a list of typed segments.

    Follows the grammar from spec Section 5.1 (Appendix C ABNF).
    Accepts both canonical and non-canonical forms (spec Section 5.5).

    Raises PathError for malformed paths.
    """
    if not path:
        raise PathError("Empty path")
    if not path.startswith("$"):
        raise PathError(f"Path must start with '$': {path!r}")

    segments: list[RootSegment | PropertySegment | IndexSegment | KeyFilterSegment | ValueFilterSegment] = []
    i = 1  # skip '$'

    # Root-only path
    if i >= len(path):
        return segments

    while i < len(path):
        if path[i] == ".":
            # Dot property: .name
            i += 1
            if i >= len(path):
                raise PathError(f"Empty property name after '.' at position {i} in: {path!r}")

            # Spec grammar: property-name = (ALPHA / "_") *(ALPHA / DIGIT / "_")
            # First character must be alpha or underscore (not a digit)
            first_char = path[i]
            if not (first_char.isalpha() or first_char == "_"):
                raise PathError(
                    f"Invalid property name character {first_char!r} after '.' at position {i} in: {path!r}. "
                    f"Property names must start with a letter or underscore."
                )

            start = i
            while i < len(path) and (path[i].isalnum() or path[i] == "_"):
                i += 1
            name = path[start:i]
            segments.append(PropertySegment(name=name))

        elif path[i] == "[":
            if i + 1 >= len(path):
                raise PathError(f"Unexpected end of path after '[' at position {i} in: {path!r}")

            next_char = path[i + 1]

            if next_char == "?":
                # Filter: [?(@...)]
                if i + 3 >= len(path) or path[i + 2] != "(":
                    raise PathError(f"Invalid filter syntax at position {i} in: {path!r}")
                if path[i + 3] != "@":
                    raise PathError(f"Filter must start with '@' at position {i + 3} in: {path!r}")

                # Find closing ')]'
                content_start = i + 4  # after '[?(@'
                close_paren = _find_filter_close(path, content_start)
                inner = path[content_start:close_paren]
                segments.append(_parse_filter(inner))
                i = close_paren + 2  # skip ')]'

            elif next_char == "'":
                # Bracket property: ['key']
                key, close_quote_idx = _extract_quoted_string(path, i + 2)  # after ['
                # Expect ']' after closing quote
                expected_bracket = close_quote_idx + 1
                if expected_bracket >= len(path) or path[expected_bracket] != "]":
                    raise PathError(f"Expected ']' after quoted property at position {expected_bracket} in: {path!r}")
                segments.append(PropertySegment(name=key))
                i = expected_bracket + 1

            elif next_char.isdigit():
                # Array index: [0], [12], etc.
                close_bracket = path.find("]", i + 1)
                if close_bracket == -1:
                    raise PathError(f"Unterminated array index at position {i} in: {path!r}")
                index_str = path[i + 1 : close_bracket]

                # Validate: no leading zeros (spec Appendix G.1)
                if len(index_str) > 1 and index_str[0] == "0":
                    raise PathError(f"Leading zeros in array index: [{index_str}] in: {path!r}")

                segments.append(IndexSegment(index=int(index_str)))
                i = close_bracket + 1

            else:
                raise PathError(f"Unexpected character {next_char!r} after '[' at position {i + 1} in: {path!r}")

        else:
            raise PathError(f"Unexpected character {path[i]!r} at position {i} in: {path!r}")

    return segments


def describe_path(path: str) -> str:
    """Generate a human-readable description of a JSON Atom path.

    Parses the path into typed segments and formats each readably.

    Examples::

        "$"                              → "(root)"
        "$.user.name"                    → "user > name"
        "$.items[?(@.id=='1')].name"     → "items[id='1'] > name"
        "$.items[0].name"                → "items[0] > name"
        "$.tags[?(@=='urgent')]"         → "tags[='urgent']"
        "$['a.b'].value"                 → "a.b > value"

    Raises:
        PathError: If the path is malformed.
    """
    segments = parse_path(path)

    if not segments:
        return "(root)"

    parts: list[str] = []
    for seg in segments:
        if isinstance(seg, RootSegment):
            continue
        elif isinstance(seg, PropertySegment):
            parts.append(seg.name)
        elif isinstance(seg, IndexSegment):
            if parts:
                parts[-1] = f"{parts[-1]}[{seg.index}]"
            else:
                parts.append(f"[{seg.index}]")
        elif isinstance(seg, KeyFilterSegment):
            literal = format_filter_literal(seg.value)
            if parts:
                parts[-1] = f"{parts[-1]}[{seg.property}={literal}]"
            else:
                parts.append(f"[{seg.property}={literal}]")
        elif isinstance(seg, ValueFilterSegment):
            literal = format_filter_literal(seg.value)
            if parts:
                parts[-1] = f"{parts[-1]}[={literal}]"
            else:
                parts.append(f"[={literal}]")

    return " > ".join(parts) if parts else "(root)"


def resolve_path(path: str, document: Any) -> str:
    """Resolve a JSON Atom path to an RFC 6901 JSON Pointer.

    Walks the path segments against the document, resolving filter expressions
    to positional indices. Property and index segments pass through directly.

    Args:
        path: A JSON Atom path string (e.g., ``"$.items[?(@.id=='1')].name"``).
        document: The document to resolve against.

    Returns:
        An RFC 6901 JSON Pointer (e.g., ``"/items/0/name"``).
        Returns ``""`` for the root path ``"$"``.

    Raises:
        PathError: If the path is malformed or a filter matches zero or
            multiple elements.
    """
    segments = parse_path(path)

    if not segments:
        return ""

    pointer_parts: list[str] = []
    current: Any = document

    for seg in segments:
        if isinstance(seg, RootSegment):
            continue
        elif isinstance(seg, PropertySegment):
            pointer_parts.append(_escape_json_pointer(seg.name))
            current = current.get(seg.name) if isinstance(current, dict) else None
        elif isinstance(seg, IndexSegment):
            pointer_parts.append(str(seg.index))
            current = current[seg.index] if isinstance(current, list) and seg.index < len(current) else None
        elif isinstance(seg, KeyFilterSegment):
            idx = _resolve_key_filter(current, seg)
            pointer_parts.append(str(idx))
            current = current[idx]
        elif isinstance(seg, ValueFilterSegment):
            idx = _resolve_value_filter(current, seg)
            pointer_parts.append(str(idx))
            current = current[idx]

    return "/" + "/".join(pointer_parts) if pointer_parts else ""


def _escape_json_pointer(segment: str) -> str:
    """Escape a string for use in a JSON Pointer (RFC 6901 §3).

    ``~`` → ``~0``, ``/`` → ``~1``.
    """
    return segment.replace("~", "~0").replace("/", "~1")


def _resolve_key_filter(arr: Any, seg: KeyFilterSegment) -> int:
    """Find exactly one element matching a key filter. Returns its index."""
    if not isinstance(arr, list):
        raise PathError(f"Cannot apply key filter on {type(arr).__name__}: expected array")

    from json_atom._utils import json_equal

    _sentinel = object()

    def _resolve(obj: Any, key: str) -> Any:
        if seg.literal_key or "." not in key:
            return obj.get(key, _sentinel) if isinstance(obj, dict) else _sentinel
        cur = obj
        for s in key.split("."):
            if not isinstance(cur, dict) or s not in cur:
                return _sentinel
            cur = cur[s]
        return cur

    matches: list[int] = []
    for idx, elem in enumerate(arr):
        resolved = _resolve(elem, seg.property)
        if resolved is not _sentinel and json_equal(resolved, seg.value):
            matches.append(idx)

    if len(matches) == 0:
        literal = format_filter_literal(seg.value)
        raise PathError(f"Key filter [?(@.{seg.property}=={literal})] matched zero elements")
    if len(matches) > 1:
        literal = format_filter_literal(seg.value)
        raise PathError(
            f"Key filter [?(@.{seg.property}=={literal})] matched {len(matches)} elements (must be exactly one)"
        )
    return matches[0]


def _resolve_value_filter(arr: Any, seg: ValueFilterSegment) -> int:
    """Find exactly one element matching a value filter. Returns its index."""
    if not isinstance(arr, list):
        raise PathError(f"Cannot apply value filter on {type(arr).__name__}: expected array")

    from json_atom._utils import json_equal

    matches: list[int] = []
    for idx, elem in enumerate(arr):
        if json_equal(elem, seg.value):
            matches.append(idx)

    if len(matches) == 0:
        literal = format_filter_literal(seg.value)
        raise PathError(f"Value filter [?(@=={literal})] matched zero elements")
    if len(matches) > 1:
        literal = format_filter_literal(seg.value)
        raise PathError(f"Value filter [?(@=={literal})] matched {len(matches)} elements (must be exactly one)")
    return matches[0]


def build_path(
    segments: Sequence[RootSegment | PropertySegment | IndexSegment | KeyFilterSegment | ValueFilterSegment],
) -> str:
    """Build a canonical JSON Atom Path string from typed segments.

    Produces canonical form per spec Section 5.5:
    - Dot notation for property names matching [a-zA-Z_][a-zA-Z0-9_]*
    - Bracket-quote notation for property names that can't use dot notation
    - Bracket notation for array indices
    - Filter expressions with typed literals
    """
    parts: list[str] = ["$"]

    for seg in segments:
        if isinstance(seg, RootSegment):
            continue  # root is always implicit in '$'
        elif isinstance(seg, PropertySegment):
            if _PROPERTY_NAME_RE.match(seg.name):
                parts.append(f".{seg.name}")
            else:
                escaped = seg.name.replace("'", "''")
                parts.append(f"['{escaped}']")
        elif isinstance(seg, IndexSegment):
            parts.append(f"[{seg.index}]")
        elif isinstance(seg, KeyFilterSegment):
            prop = seg.property
            literal = format_filter_literal(seg.value)
            if seg.literal_key:
                # Literal property name (from bracket notation) — always bracket
                escaped_prop = prop.replace("'", "''")
                parts.append(f"[?(@['{escaped_prop}']=={literal})]")
            elif _NESTED_PATH_RE.match(prop):
                # Simple identifier or nested path — dot notation
                parts.append(f"[?(@.{prop}=={literal})]")
            else:
                escaped_prop = prop.replace("'", "''")
                parts.append(f"[?(@['{escaped_prop}']=={literal})]")
        elif isinstance(seg, ValueFilterSegment):
            literal = format_filter_literal(seg.value)
            parts.append(f"[?(@=={literal})]")
        else:
            raise PathError(f"Unknown segment type: {type(seg).__name__}")

    return "".join(parts)
