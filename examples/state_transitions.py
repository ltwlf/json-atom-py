"""State transitions — track agent or workflow state changes as deltas.

Useful for AI agent loops, workflow engines, or any system where
you need to record exactly what changed between steps.

Run: uv run python examples/state_transitions.py
"""

import copy

from json_delta import apply_delta, diff_delta

# An AI agent's state evolving over multiple steps
states = [
    # Step 0: initial state
    {
        "task": "Research competitors",
        "status": "in_progress",
        "findings": [],
        "confidence": 0.0,
    },
    # Step 1: first finding
    {
        "task": "Research competitors",
        "status": "in_progress",
        "findings": [{"company": "Acme", "strength": "pricing"}],
        "confidence": 0.3,
    },
    # Step 2: second finding + confidence update
    {
        "task": "Research competitors",
        "status": "in_progress",
        "findings": [
            {"company": "Acme", "strength": "pricing"},
            {"company": "Globex", "strength": "technology"},
        ],
        "confidence": 0.7,
    },
    # Step 3: task complete
    {
        "task": "Research competitors",
        "status": "completed",
        "findings": [
            {"company": "Acme", "strength": "pricing"},
            {"company": "Globex", "strength": "technology"},
        ],
        "confidence": 1.0,
        "summary": "Two main competitors identified.",
    },
]

# Compute deltas between consecutive states
print("=== State Transition Log ===")
total_ops = 0
for i in range(1, len(states)):
    delta = diff_delta(states[i - 1], states[i], array_keys={"findings": "company"})
    total_ops += len(delta.operations)

    print(f"\nStep {i - 1} -> {i}  ({len(delta.operations)} ops)")
    for op in delta:
        print(f"  {op.op:>7s}  {op.describe()}  =  {op.value if op.value is not None else '(removed)'}")
        if op.filter_values:
            print(f"           key: {op.filter_values}")

    adds = delta.filter(lambda o: o.op == "add")
    if adds.operations:
        print(f"  +{len(adds.operations)} additions")

    print(f"  affected: {delta.affected_paths}")

    result = apply_delta(copy.deepcopy(states[i - 1]), delta)
    assert result == states[i], f"Transition {i - 1}->{i} failed"

print(f"\nTotal: {len(states) - 1} transitions, {total_ops} operations")
print("Round-trip: all transitions verified ✓")
