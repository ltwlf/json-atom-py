"""Undo/redo — reversible configuration editing.

A deployment config editor backed by JSON Delta. Each change
is a reversible delta, enabling multi-step undo and redo.

Run: uv run python examples/undo_redo.py
"""

import copy
from typing import Any

from json_delta import Delta, apply_delta, diff_delta, invert_delta


class ConfigEditor:
    """Tracks configuration changes with full undo/redo support."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = copy.deepcopy(config)
        self.undo_stack: list[Delta] = []
        self.redo_stack: list[Delta] = []

    def update(self, new_config: dict[str, Any]) -> None:
        """Apply a change and push it onto the undo stack."""
        delta = diff_delta(self.config, new_config, reversible=True)
        if not delta.operations:
            return
        self.undo_stack.append(delta)
        self.redo_stack.clear()
        self.config = apply_delta(self.config, delta)

    def undo(self) -> bool:
        """Undo the last change. Returns False if nothing to undo."""
        if not self.undo_stack:
            return False
        delta = self.undo_stack.pop()
        self.config = apply_delta(self.config, invert_delta(delta))
        self.redo_stack.append(delta)
        return True

    def redo(self) -> bool:
        """Redo the last undone change. Returns False if nothing to redo."""
        if not self.redo_stack:
            return False
        delta = self.redo_stack.pop()
        self.config = apply_delta(self.config, delta)
        self.undo_stack.append(delta)
        return True


# Editing a service deployment configuration
initial = {
    "service": "payment-api",
    "replicas": 2,
    "env": "staging",
    "memory": "512Mi",
}
editor = ConfigEditor(initial)
print(f"Initial:    {editor.config}")

# Change 1: scale up for load test
editor.update({**editor.config, "replicas": 5, "memory": "1Gi"})
print(f"Scaled up:  {editor.config}")

# Change 2: promote to production
editor.update({**editor.config, "env": "production"})
print(f"Promoted:   {editor.config}")

# Show undo stack
print(f"\n=== Undo stack ({len(editor.undo_stack)} deltas) ===")
for i, delta in enumerate(editor.undo_stack):
    print(f"  [{i}] {len(delta.operations)} ops — {delta.affected_paths}")
    print(f"       {delta.summary()}")

# Undo the production promotion
editor.undo()
print(f"\nAfter undo: {editor.config}")
assert editor.config["env"] == "staging"

# Undo the scale-up too
editor.undo()
print(f"After undo: {editor.config}")
assert editor.config == initial

# Redo the scale-up
editor.redo()
print(f"After redo: {editor.config}")
assert editor.config["replicas"] == 5

print("\nOperations: 2 changes, 2 undos, 1 redo")
print("Round-trip: undo ✓  redo ✓  state restored ✓")
