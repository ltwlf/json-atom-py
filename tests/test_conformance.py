"""Conformance tests against the official JSON Atom fixture suite.

Level 1: apply(source, delta) == target
Level 2: apply(target, inverse(delta)) == source
"""

from json_atom.apply import apply_delta
from json_atom.invert import invert_delta

from tests.conftest import deep_clone, load_fixture


class TestLevel1Apply:
    """Level 1 conformance: apply(source, delta) == target."""

    def test_basic_replace(self) -> None:
        fixture = load_fixture("basic-replace")
        source = deep_clone(fixture["source"])
        result = apply_delta(source, fixture["delta"])
        assert result == fixture["target"]

    def test_keyed_array_update(self) -> None:
        fixture = load_fixture("keyed-array-update")
        source = deep_clone(fixture["source"])
        result = apply_delta(source, fixture["delta"])
        assert result == fixture["target"]


class TestLevel2Reversible:
    """Level 2 conformance: apply(target, inverse(delta)) == source."""

    def test_basic_replace(self) -> None:
        fixture = load_fixture("basic-replace")
        assert fixture["level"] >= 2
        inverse = invert_delta(fixture["delta"])
        target = deep_clone(fixture["target"])
        recovered = apply_delta(target, inverse)
        assert recovered == fixture["source"]

    def test_keyed_array_update(self) -> None:
        fixture = load_fixture("keyed-array-update")
        assert fixture["level"] >= 2
        inverse = invert_delta(fixture["delta"])
        target = deep_clone(fixture["target"])
        recovered = apply_delta(target, inverse)
        assert recovered == fixture["source"]


class TestRoundTrip:
    """Full round-trip: apply then revert recovers source."""

    def test_basic_replace_round_trip(self) -> None:
        fixture = load_fixture("basic-replace")
        source = deep_clone(fixture["source"])
        target = apply_delta(deep_clone(fixture["source"]), fixture["delta"])
        assert target == fixture["target"]

        inverse = invert_delta(fixture["delta"])
        recovered = apply_delta(target, inverse)
        assert recovered == source

    def test_keyed_array_update_round_trip(self) -> None:
        fixture = load_fixture("keyed-array-update")
        source = deep_clone(fixture["source"])
        target = apply_delta(deep_clone(fixture["source"]), fixture["delta"])
        assert target == fixture["target"]

        inverse = invert_delta(fixture["delta"])
        recovered = apply_delta(target, inverse)
        assert recovered == source
