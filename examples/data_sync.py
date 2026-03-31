"""Client-server sync — send deltas instead of full documents.

Computes a delta on the client and applies it on the server.
Only the changes are transmitted, reducing payload size.

Run: uv run python examples/data_sync.py
"""

import copy
import json

from json_atom import Delta, apply_delta, diff_delta, validate_delta

# Server holds the current team directory
server_state = {
    "users": [
        {"id": "u1", "name": "Alice Chen", "role": "viewer", "department": "Engineering"},
        {"id": "u2", "name": "Bob Martinez", "role": "viewer", "department": "Engineering"},
        {"id": "u3", "name": "Carol Park", "role": "admin", "department": "Security"},
        {"id": "u4", "name": "Dan Wilson", "role": "viewer", "department": "Marketing"},
        {"id": "u5", "name": "Eva Santos", "role": "viewer", "department": "Design"},
    ]
}

# Client makes local changes: promote Alice, add a new hire
client_state = copy.deepcopy(server_state)
client_state["users"][0]["role"] = "admin"
client_state["users"].append(
    {"id": "u6", "name": "Frank Okafor", "role": "viewer", "department": "Engineering"}
)

# Compute delta (what the client sends instead of the full document)
delta = diff_delta(server_state, client_state, array_identity_keys={"users": "id"})

# Payload comparison
full_size = len(json.dumps(client_state))
delta_size = len(json.dumps(delta))
print("=== Sync Payload ===")
print(f"Full document: {full_size}B")
print(f"Delta payload: {delta_size}B ({delta_size * 100 // full_size}% of full)")

# Typed iteration
print(f"\n=== Delta ({len(delta.operations)} operations) ===")
for op in delta:
    print(f"  {op.op:>7s}  {op.describe()}")
    if op.filter_values:
        print(f"           key: {op.filter_values}")

print(f"\nAffected: {delta.affected_paths}")

# Server receives JSON, reconstructs typed Delta, validates and applies
payload = json.dumps(delta)
received = Delta.from_dict(json.loads(payload))

validation = validate_delta(received)
assert validation.valid, f"Invalid delta: {validation.errors}"

server_state = apply_delta(server_state, received)

print("\n=== Server state after sync ===")
for user in server_state["users"]:
    print(f"  {user['id']}: {user['name']} ({user['role']}, {user['department']})")

assert server_state == client_state
print(f"\n{delta.summary()}")
print("Round-trip: compute → serialize → validate → apply ✓")
