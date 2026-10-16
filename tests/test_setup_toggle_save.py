"""Setup page: Hook Type and Smart Screenshot Picker save where they are changed.

Before the fix, the Hook Type toggle, the Smart Screenshot Picker toggle and
the clipboard screenshot count were only sent by the Comment Intelligence
section's "Save settings" button, so changing them in their own sections and
leaving the page lost the change silently.

Runs tests/js/setup_toggle_save_test.mjs, which loads the REAL extension
scripts (lib/extract.js, lib/ui.js and setup.js) into a fake browser built on
node:vm, over a DOM holding every id setup.html declares, boots the page
against a stubbed helper (/health, /settings) that, like server.py, keeps only
the settings fields it knows and answers ok to the rest, and changes the
controls:

  hook_type  -- toggling Hook Type sends one authed POST /settings carrying
                just {hook_type_enabled} (never a typed-but-unsaved API key)
                and shows "Saved" in the Hook Type section.
  screenshot -- the picker toggle and the screenshot count each save on
                change, each with its own status line; the count is sent as
                the clamped integer and the field shows what was saved.
  failure    -- a helper error or an unreachable helper shows "Save failed"
                in the section and puts the control back to the helper's
                value; a stale failure never undoes a newer change; an ok
                answer that does not carry the change shows "Not saved".
  overlap    -- saves made while an earlier one is unanswered reach the helper
                in the order they were made, with either answer order: the
                page never shows "Saved" for a value the helper does not
                keep, a slow Comment Intelligence save never resets a control
                changed after it, and the picker and the count never report
                each other's result. A field edited again after its save was
                made (the screenshot count, the vault path, Hook Type, the
                key box, typing included) keeps that edit when the save fails
                or an answer, reload or pending restore lands; once the helper
                stored the edit, the field shows later answers again (a vault
                path saved from another tab is not written back over).
  ci_save    -- the Comment Intelligence toggle saves on change with its own
                Saved / Save failed line (never the typed key); the "Save
                settings" button still saves the toggle and the typed key,
                leaves Hook Type, the picker and the count (and a toggle save
                still out) to their own saves, and sends nothing when there
                is nothing to save.
  section_status -- the Claim verification toggle and the Obsidian vault path
                (saved with the rest of their sections) show Saving..., then
                Saved or "Save failed" in their own section, for a stored, a
                refused and an unreachable save; Obsidian mirroring and the
                evidence sources, which the helper answers ok to but drops,
                show "Not saved" naming the setting, never "Saved"; a section
                whose save failed reads Saved once a later save from another
                section stores its change; one section never reports another
                save's failure for a value already stored, and an older stored
                save never calls a newer change Saved.
  read_timeout -- a settings read on load that the helper never answers is
                given up on after a bounded wait, so a Hook Type change queued
                behind it is still sent and reports Saved, and the read's late
                answer does not reset it. After that timeout no save sends a
                control still at its HTML default (a saved vault path and
                Comment Intelligence survive a Claim verification change),
                and the first answered save (Hook Type, Clear key or Claim
                verification) fills those controls in. Settings a failed save
                kept on this device are carried by the next save, are not
                replaced by the helper's old values, and leave the pending
                record only once the helper stores them. After a failed read,
                no answer replaces a vault path or screenshot count being
                typed (focused or not); a focused field not yet edited is
                filled in.

No network: fetch and chrome.* are stubs inside the harness.
"""
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "tests" / "js" / "setup_toggle_save_test.mjs"

GROUPS = [
    "hook_type",
    "screenshot",
    "failure",
    "overlap",
    "ci_save",
    "section_status",
    "read_timeout",
]


@pytest.mark.parametrize("group", GROUPS)
def test_setup_toggle_save(group):
    assert HARNESS.exists(), f"missing harness: {HARNESS}"
    proc = subprocess.run(
        ["node", str(HARNESS), group],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    output = f"{proc.stdout}\n{proc.stderr}"
    assert proc.returncode == 0, f"{group} harness failed:\n{output}"
    assert "FAIL" not in output, output
    # Guard against a group that silently ran nothing.
    marker = f"group {group}: "
    assert marker in proc.stdout, output
    count = int(proc.stdout.split(marker, 1)[1].split(" ", 1)[0])
    assert count >= 3, output
