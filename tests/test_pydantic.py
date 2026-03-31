"""Tests for Pydantic v2 integration — Operation and Delta as native Pydantic fields."""

from __future__ import annotations

import json
from typing import Any

import pytest

pydantic = pytest.importorskip("pydantic", minversion="2.0")

from pydantic import BaseModel  # noqa: E402

from json_atom.models import Delta, Operation  # noqa: E402


class OperationModel(BaseModel):
    operation: Operation


class DeltaModel(BaseModel):
    delta: Delta


class MixedModel(BaseModel):
    op: Operation
    delta: Delta
    label: str = ""


# ---------------------------------------------------------------------------
# Operation in Pydantic
# ---------------------------------------------------------------------------


class TestOperationInPydantic:
    def test_from_operation_instance(self) -> None:
        op = Operation.add("$.name", "Alice")
        m = OperationModel(operation=op)
        assert isinstance(m.operation, Operation)
        assert m.operation.op == "add"
        assert m.operation.path == "$.name"

    def test_from_raw_dict(self) -> None:
        m = OperationModel(operation={"op": "replace", "path": "$.x", "value": 42})
        assert isinstance(m.operation, Operation)
        assert m.operation.op == "replace"
        assert m.operation.value == 42

    def test_model_dump_returns_plain_dict(self) -> None:
        op = Operation.add("$.name", "Alice")
        m = OperationModel(operation=op)
        dumped = m.model_dump()
        assert isinstance(dumped["operation"], dict)
        assert not isinstance(dumped["operation"], Operation)
        assert dumped["operation"]["op"] == "add"

    def test_model_dump_json_roundtrip(self) -> None:
        op = Operation.replace("$.x", 42, old_value=1)
        m = OperationModel(operation=op)
        json_str = m.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["operation"]["op"] == "replace"
        assert parsed["operation"]["value"] == 42
        assert parsed["operation"]["oldValue"] == 1

    def test_validation_rejects_non_dict(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            OperationModel(operation="not a dict")  # type: ignore[arg-type]

    def test_operation_with_extensions(self) -> None:
        m = OperationModel(
            operation={"op": "add", "path": "$.x", "value": 1, "x_editor": "admin"}
        )
        assert m.operation.x_editor == "admin"
        dumped = m.model_dump()
        assert dumped["operation"]["x_editor"] == "admin"


# ---------------------------------------------------------------------------
# Delta in Pydantic
# ---------------------------------------------------------------------------


class TestDeltaInPydantic:
    def test_from_delta_instance(self) -> None:
        delta = Delta.create(Operation.add("$.name", "Alice"))
        m = DeltaModel(delta=delta)
        assert isinstance(m.delta, Delta)
        assert len(m.delta.operations) == 1

    def test_from_raw_dict(self) -> None:
        raw: dict[str, Any] = {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "add", "path": "$.name", "value": "Alice"}],
        }
        m = DeltaModel(delta=raw)
        assert isinstance(m.delta, Delta)
        assert isinstance(m.delta.operations[0], Operation)

    def test_model_dump_returns_plain_dicts(self) -> None:
        delta = Delta.create(
            Operation.add("$.name", "Alice"),
            Operation.replace("$.age", 31, old_value=30),
        )
        m = DeltaModel(delta=delta)
        dumped = m.model_dump()
        assert isinstance(dumped["delta"], dict)
        assert not isinstance(dumped["delta"], Delta)
        # Nested operations should also be plain dicts
        for op in dumped["delta"]["operations"]:
            assert isinstance(op, dict)
            assert not isinstance(op, Operation)

    def test_model_dump_json_roundtrip(self) -> None:
        delta = Delta.create(
            Operation.add("$.name", "Alice"),
            Operation.replace("$.age", 31, old_value=30),
        )
        m = DeltaModel(delta=delta)
        json_str = m.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["delta"]["format"] == "json-atom"
        assert len(parsed["delta"]["operations"]) == 2

    def test_validation_rejects_non_dict(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            DeltaModel(delta="not a dict")  # type: ignore[arg-type]

    def test_delta_with_extensions(self) -> None:
        raw: dict[str, Any] = {
            "format": "json-atom",
            "version": 1,
            "operations": [],
            "x_agent": "test",
        }
        m = DeltaModel(delta=raw)
        assert m.delta.x_agent == "test"


# ---------------------------------------------------------------------------
# Round-trips
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_operation_validate_dump_validate(self) -> None:
        op = Operation.add("$.name", "Alice")
        m1 = OperationModel(operation=op)
        dumped = m1.model_dump()
        m2 = OperationModel.model_validate(dumped)
        assert m2.operation.op == "add"
        assert m2.operation.path == "$.name"

    def test_delta_validate_dump_validate(self) -> None:
        delta = Delta.create(Operation.replace("$.x", 2, old_value=1))
        m1 = DeltaModel(delta=delta)
        dumped = m1.model_dump()
        m2 = DeltaModel.model_validate(dumped)
        assert isinstance(m2.delta, Delta)
        assert m2.delta.operations[0].op == "replace"

    def test_json_roundtrip(self) -> None:
        delta = Delta.create(Operation.add("$.x", 1))
        m1 = DeltaModel(delta=delta)
        json_str = m1.model_dump_json()
        m2 = DeltaModel.model_validate_json(json_str)
        assert isinstance(m2.delta, Delta)
        assert m2.delta.operations[0].value == 1

    def test_mixed_model_roundtrip(self) -> None:
        op = Operation.replace("$.x", 2, old_value=1)
        delta = Delta.create(op)
        m1 = MixedModel(op=op, delta=delta, label="test")
        dumped = m1.model_dump()
        m2 = MixedModel.model_validate(dumped)
        assert m2.op.op == "replace"
        assert len(m2.delta.operations) == 1
        assert m2.label == "test"


# ---------------------------------------------------------------------------
# No config needed
# ---------------------------------------------------------------------------


class TestNoArbitraryTypesNeeded:
    def test_no_config_needed(self) -> None:
        """Verify models work without arbitrary_types_allowed."""

        class StrictModel(BaseModel):
            operation: Operation
            delta: Delta

        op = Operation.add("$.x", 1)
        delta = Delta.create(op)
        m = StrictModel(operation=op, delta=delta)
        assert m.operation.op == "add"
        assert len(m.delta.operations) == 1
