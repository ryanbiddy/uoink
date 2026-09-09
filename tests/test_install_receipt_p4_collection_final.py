"""Declared negative sessions and incomplete deletion evidence cannot earn credit."""
import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/install_receipt"))
from p4_collect_evidence import packet_scenario_records
from p4_execute_checks import deletion_evidence_ok


def test_only_declared_negative_scenarios_leave_packet_scope(tmp_path):
    names = ["originalinstalleda-1", "originalinstalledb-2", "originalinstalledunavail-3",
             "originalinstalledtransport-4", "originalinstalled-partial-5",
             "originalinstalledtransport-malformed"]
    paths = [tmp_path / name / "events.jsonl" for name in names]
    full, negative = packet_scenario_records(paths)
    assert full == [paths[0], paths[1], paths[4], paths[5]]
    assert negative == [paths[2], paths[3]]


def test_deletion_counts_and_keys_are_not_owned_file_evidence():
    assert not deletion_evidence_ok({"owned": 2, "temp": 2, "pending": 2,
                                     "conflict": [], "deletion_pending": 1})


@pytest.mark.parametrize("change", [
    {"content_free_tombstone": False}, {"soft_delete_committed": False},
    {"purge_committed": False}, {"owned_paths": [{"absent": False}]},
    {"owned_paths": []}, {"unaccounted_pending_keys": ["item:unexplained"]},
    {"remaining_temp_paths": ["Library/owned.tmp"]},
    {"user_edit_preserved": False}, {"unmanaged_preserved": False},
])
def test_each_missing_deletion_obligation_refuses_acceptance(change):
    complete = {"soft_delete_committed": True, "content_free_tombstone": True,
                "purge_committed": True, "owned_paths": [{"absent": True}],
                "unaccounted_pending_keys": [], "remaining_temp_paths": [],
                "user_edit_preserved": True, "unmanaged_preserved": True}
    assert deletion_evidence_ok(complete)
    incomplete = copy.deepcopy(complete)
    incomplete.update(change)
    assert not deletion_evidence_ok(incomplete)
