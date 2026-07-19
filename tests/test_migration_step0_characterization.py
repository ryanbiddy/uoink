"""Golden HTTP contracts for migration Step 0.

These tests freeze the observable workspace/assembly, script, and writing
payloads before those surfaces move. The fixture metadata contains the exact
regeneration and check command for that fixture.

Run:
    pytest tests/test_migration_step0_characterization.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import regenerate_migration_step0_fixtures as regenerate


@pytest.mark.parametrize("name", list(regenerate.FIXTURES))
def test_characterization_fixture_is_current(name):
    path = regenerate.FIXTURES[name]["path"]
    expected = json.loads(path.read_text(encoding="utf-8"))
    actual = regenerate.generate_fixture(name)
    assert actual == expected

    metadata = expected["_fixture"]
    command = (
        "python tests/regenerate_migration_step0_fixtures.py "
        f"--fixture {name}"
    )
    assert metadata["regenerate"] == command
    assert metadata["check"] == command.replace(
        " --fixture", " --check --fixture")
    assert metadata["data"] == "synthetic"
    assert metadata["network"] == "loopback only"


def test_fixture_paths_are_repo_relative_and_json():
    root = Path(__file__).resolve().parent.parent
    for config in regenerate.FIXTURES.values():
        assert config["path"].is_relative_to(root)
        assert config["path"].suffix == ".json"
