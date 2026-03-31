"""Shared test helpers and fixtures for json-atom tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    """Load a conformance fixture by name (without extension)."""
    path = FIXTURES_DIR / f"{name}.json"
    with open(path) as f:
        return json.load(f)  # type: ignore[no-any-return]


def deep_clone(obj: Any) -> Any:
    """Deep-copy a JSON-compatible value."""
    return copy.deepcopy(obj)
