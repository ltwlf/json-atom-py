"""Run every shared spec fixture, including all five operation types."""

import copy
import json
from pathlib import Path

import pytest

from json_atom import apply_delta, revert_delta, validate_delta
from json_atom._utils import json_equal

FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("*.json"))


@pytest.mark.parametrize("path", FIXTURES, ids=lambda path: path.stem)
def test_spec_conformance(path):
    fixture = json.loads(path.read_text())
    delta = fixture["delta"]
    assert validate_delta(delta).valid
    assert json_equal(apply_delta(copy.deepcopy(fixture["source"]), delta), fixture["target"])
    if fixture["level"] == 2:
        assert json_equal(revert_delta(copy.deepcopy(fixture["target"]), delta), fixture["source"])
