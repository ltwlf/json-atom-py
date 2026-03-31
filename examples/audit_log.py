"""Audit log — complete change history with point-in-time recovery.

Records every edit as a reversible delta with extension metadata (who, when).
The full audit trail enables compliance reporting, replay, and revert.

Run: uv run python examples/audit_log.py
"""

import copy
from datetime import UTC, datetime
from typing import Any

from json_atom import Delta, Operation, apply_delta, diff_delta, revert_delta

# Initial document
initial = {"title": "Q4 Report", "status": "draft", "author": "Alice"}
document = copy.deepcopy(initial)

# Audit log stores every delta with extension metadata
audit_log: list[Delta] = []


def edit(doc: dict[str, Any], new_state: dict[str, Any], editor: str) -> dict[str, Any]:
    """Apply an edit and record the delta with extension metadata."""
    delta = diff_delta(doc, new_state, reversible=True)

    # Extension properties — preserved through serialize/deserialize
    delta["x_editor"] = editor
    delta["x_timestamp"] = datetime.now(UTC).isoformat()

    audit_log.append(delta)
    apply_delta(doc, delta)
    return doc


# Document workflow: draft → review → final
document = edit(document, {**document, "status": "review"}, "Alice")
document = edit(document, {**document, "title": "Q4 Financial Report"}, "Bob")
document = edit(document, {**document, "status": "final", "approved": True}, "Alice")

print("=== Current Document ===")
print(document)

# Audit trail — extension attributes via __getattr__ (spec Section 11)
total_ops = sum(len(d.operations) for d in audit_log)
print(f"\n=== Audit Trail ({len(audit_log)} edits, {total_ops} ops) ===")
for i, delta in enumerate(audit_log):
    editor = delta.x_editor  # extension attribute access
    ops_desc = ", ".join(f"{op.op} {op.describe()}" for op in delta)
    print(f"  [{i}] {editor}: {ops_desc}")
    print(f"       affected: {delta.affected_paths}")
    print(f"       extensions: {delta.extensions}")

# Replay: rebuild from scratch using the audit log
replayed = copy.deepcopy(initial)
for delta in audit_log:
    replayed = apply_delta(replayed, delta)
assert replayed == document, "Replay should reproduce the current document"

# Revert: undo the last edit
document = revert_delta(document, audit_log[-1])
assert document == {"title": "Q4 Financial Report", "status": "review", "author": "Alice"}

print("\n=== After reverting last edit ===")
print(document)

# Build a delta manually with Operation factories and extensions
manual_delta = Delta.create(
    Operation.replace("$.status", "final", old_value="review"),
    Operation.add("$.approved", True, x_reason="manager sign-off"),
    x_editor="Alice",
    x_timestamp=datetime.now(UTC).isoformat(),
)

approve_op = manual_delta.operations[1]
assert approve_op.x_reason == "manager sign-off"
print(f"\nManual delta: {manual_delta.summary()}")

print("\nRound-trip: replay ✓  revert ✓  extensions preserved ✓")
