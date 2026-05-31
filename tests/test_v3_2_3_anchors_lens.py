"""v3.2.3 backend tests: default style-anchor seeding + hook-type lens.

Run: python tests/test_v3_2_3_anchors_lens.py
Exercises writing_studio against an in-memory SQLite that mirrors the
style_anchors schema after migrations 0014 + 0016. No server boot, no network.
"""
from __future__ import annotations

import sqlite3
import threading
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import writing_studio as ws  # noqa: E402


class FakeIndex:
    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        # style_anchors after 0014 + the 0016 is_default add.
        self._conn.executescript("""
            CREATE TABLE style_anchors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_url TEXT,
                raw_text TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                added_at TEXT NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0
            );
        """)

    def get_yoink(self, vid):
        return None


def _assert(c, m):
    if not c:
        raise AssertionError(m)


DEFAULTS = [
    {"name": f"Default {i}", "source_type": "text",
     "source_url": f"https://x.com/d{i}", "raw_text": f"sample {i}"}
    for i in range(5)
]


def test_seed_and_defaults():
    idx = FakeIndex()
    seeded = ws.seed_default_anchors(idx, DEFAULTS)
    _assert(seeded == 5, f"expected 5 seeded, got {seeded}")
    # idempotent: table non-empty -> no-op
    _assert(ws.seed_default_anchors(idx, DEFAULTS) == 0, "re-seed should no-op")

    defaults = ws.list_default_anchors(idx)
    _assert(len(defaults) == 5, f"expected 5 defaults listed, got {len(defaults)}")
    for d in defaults:
        _assert(d["default"] is True, "default flag should be True")
        _assert(d["active"] == 0, "seeded defaults must be inactive")
    print("ok  seed: 5 inactive defaults, idempotent, list_default_anchors")


def test_seed_upgrade_path():
    # Upgrading user already has a custom anchor; defaults must still seed
    # alongside it (regression from Codex Windows review of #90).
    idx = FakeIndex()
    ws.add_style_anchor(idx, name="my custom voice", source_type="text",
                        source_value="hello")
    seeded = ws.seed_default_anchors(idx, DEFAULTS)
    _assert(seeded == 5, f"expected 5 defaults seeded over existing anchor, got {seeded}")
    _assert(len(ws.list_default_anchors(idx)) == 5, "5 defaults present")
    _assert(ws.style_anchor_count(idx) == 6, "1 custom + 5 defaults = 6 total")
    _assert(ws.active_style_anchor_count(idx) == 1, "only the custom anchor is active")
    # Idempotent per-default: re-seeding inserts nothing and preserves an
    # activated default's state.
    deflist = ws.list_default_anchors(idx)
    ws.update_style_anchor(idx, deflist[0]["id"], active=True)
    _assert(ws.seed_default_anchors(idx, DEFAULTS) == 0, "re-seed should no-op")
    again = {d["id"]: d for d in ws.list_default_anchors(idx)}
    _assert(again[deflist[0]["id"]]["active"] == 1, "activated default kept active")
    print("ok  seed upgrade path: defaults seed over existing anchors, idempotent")


def test_cap_counts_active_not_total():
    idx = FakeIndex()
    ws.seed_default_anchors(idx, DEFAULTS)  # 5 inactive defaults
    _assert(ws.active_style_anchor_count(idx) == 0, "inactive defaults: active count 0")
    _assert(ws.style_anchor_count(idx) == 5, "total count 5")
    # With 5 inactive defaults, a user can still add (cap is on active, not total)
    a = ws.add_style_anchor(idx, name="mine", source_type="text",
                            source_value="hello")
    _assert(a.get("default") is False, "user anchor is not a default")
    _assert(ws.active_style_anchor_count(idx) == 1, "new user anchor is active")
    print("ok  cap counts active (inactive defaults don't block adds)")


def test_cap_enforced_on_active():
    idx = FakeIndex()
    for i in range(ws.STYLE_ANCHOR_CAP):
        ws.add_style_anchor(idx, name=f"a{i}", source_type="text",
                            source_value="x")
    try:
        ws.add_style_anchor(idx, name="overflow", source_type="text",
                            source_value="x")
    except ValueError as e:
        _assert(getattr(e, "http_status", None) == 422, "cap should be 422")
        print("ok  cap enforced at 10 active -> 422")
        return
    raise AssertionError("expected cap ValueError")


def test_activate_respects_cap():
    idx = FakeIndex()
    # Fill all 10 active slots.
    ids = [ws.add_style_anchor(idx, name=f"a{i}", source_type="text",
                               source_value="x")["id"]
           for i in range(ws.STYLE_ANCHOR_CAP)]
    # Deactivate one, leaving 9 active + 1 inactive.
    ws.update_style_anchor(idx, ids[0], active=False)
    _assert(ws.active_style_anchor_count(idx) == 9, "should be 9 active")
    # Seed an inactive default; activating it would make 10 -> allowed.
    # Re-activating the deactivated one back to 10 is allowed.
    ws.update_style_anchor(idx, ids[0], active=True)
    _assert(ws.active_style_anchor_count(idx) == 10, "back to 10 active")
    # Build a "10 active + 1 inactive" state without seeding (seed no-ops on a
    # non-empty table): add 10, deactivate one, add a replacement -> 10 active
    # plus one inactive left over. Activating the leftover must 422.
    extra = FakeIndex()
    eids = [ws.add_style_anchor(extra, name=f"b{i}", source_type="text",
                                source_value="x")["id"]
            for i in range(ws.STYLE_ANCHOR_CAP)]
    ws.update_style_anchor(extra, eids[0], active=False)   # 9 active, eids[0] off
    ws.add_style_anchor(extra, name="replacement", source_type="text",
                        source_value="x")                   # back to 10 active
    _assert(ws.active_style_anchor_count(extra) == 10, "should be 10 active")
    try:
        ws.update_style_anchor(extra, eids[0], active=True)
    except ValueError as e:
        _assert(getattr(e, "http_status", None) == 422,
                "activate past cap should be 422")
        # Renaming an already-active anchor must NOT trip the cap.
        ws.update_style_anchor(extra, eids[1], name="renamed")
        print("ok  activate respects cap (422); rename of active anchor ok")
        return
    raise AssertionError("expected ValueError activating past cap")


def test_hook_lens():
    _assert(ws.normalize_hook_lens(None) is None, "None -> None")
    _assert(ws.normalize_hook_lens("") is None, "empty -> None")
    _assert(ws.normalize_hook_lens("curiosity_gap") == "curiosity_gap", "valid passes")
    _assert(ws.normalize_hook_lens("frame_shift") == "frame_shift", "valid passes 2")
    try:
        ws.normalize_hook_lens("not_a_real_hook")
    except ValueError as e:
        _assert(getattr(e, "http_status", None) == 400, "bad lens -> 400")
    else:
        raise AssertionError("expected ValueError for bad lens")
    _assert(len(ws.HOOK_LENS_TYPES) == 9, "expected 9 lens types")
    g = ws.hook_lens_grounding("stakes")
    _assert(g["type"] == "stakes" and g["directive"], "lens grounding shape")
    _assert(ws.hook_lens_grounding(None) is None, "no lens -> None grounding")
    print("ok  hook lens: validate / 9 types / grounding shape")


def test_grounding_includes_lens():
    idx = FakeIndex()
    g = ws.assemble_grounding(idx, "", hook_type_lens="curiosity_gap")
    _assert(g["hook_lens"]["type"] == "curiosity_gap", "grounding carries lens")
    g2 = ws.assemble_grounding(idx, "")
    _assert(g2["hook_lens"] is None, "no lens -> None in grounding")
    print("ok  assemble_grounding threads hook_lens")


def main():
    test_seed_and_defaults()
    test_seed_upgrade_path()
    test_cap_counts_active_not_total()
    test_cap_enforced_on_active()
    test_activate_respects_cap()
    test_hook_lens()
    test_grounding_includes_lens()
    print("\nALL v3.2.3 ANCHOR + LENS TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
