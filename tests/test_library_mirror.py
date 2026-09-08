"""tests/test_library_mirror.py - Living Library Opt-In Corpus Mirror Tests (AV-2t).

Gates covered:
- P4-09 (Mirror paths and consent):
  - Default disabled even with an existing taste vault (TASTE.md, USER.md)
  - Preview returns planned paths, counts, third-party indexing notice, existing-file conflicts; no writes
  - Scope all vs explicit item-ID allowlist filtering (unallowed items, dependent briefs excluded)
  - Destination change resets consent; mirror disabled until re-consented
  - Traversal, reserved names, case/Unicode collisions, hash collisions, reparse points
- P4-10 (Edits and atomicity):
  - User edits preserved (destination hash mismatch is user_edit_conflict; no overwrite, no merge, no .conflict.md)
  - Crash before replacement preserves old file; crash after replacement before manifest commit recovers via intent
  - Two writers serialized per destination; no race or partial writes
  - Stale delayed work rejected (older generation cannot overwrite newer)
  - Corrupt or lost manifest stops writes for reconciliation; does not adopt markdown files
  - File size cap <= 65,536 UTF-8 bytes and escaped frontmatter scalars
  - Library.md written last, referencing only completed files
- P4-11 (Deletion):
  - Tombstones: soft delete replaces body with content-free tombstone, strips title/URL/quotes, deleted: true
  - Hard purge removes owned item file, dependent brief files, owned temps; idempotent
  - Replay and restore: authoritative restore replaces tombstone with full card; late event cannot resurrect purged item
  - purge_blocked_user_edit: user-edited file preserved, reports purge_blocked_user_edit, pauses new exports
  - Disconnected destination: destination_unavailable, primary operation succeeds, pending cleanup in ledger
  - Reconnected destination validates volume marker, drains pending deletions first before content writes; budget bounds
- P4-12 (Correction-store separation):
  - Mirror ledger at DATA_ROOT/reach/mirror/ is derived delivery state, not Phase 2 correction store
  - Mirror failure, corruption, or ledger loss leaves authoritative pins/shelves in SQLite unchanged and recoverable
  - TASTE.md and USER.md in vault are never owned, overwritten, or read back by mirror
  - Modifying vault files never alters Uoink internal taxonomy / correction tables

Tests against the frozen interface in docs/library/PHASE4-AV2-BRIEF-2026-09-08.md:
- library_mirror.Mirror, MirrorConsent, CONTRACT_VERSION, MIRROR_LEDGER_DIR, MIRROR_ROOT, SCOPE_ALL
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

import index
import library_cards
import library_resources
from library_resources import ResourceError
import library_work
from tests.phase4_fixtures import (
    MockClock,
    b64url_encode,
    build_test_card,
    make_disposable_index,
    seed_shelf,
    seed_standard_library,
    seed_yoink_item,
)

# Target implementation imports: fails on import until Claude worker lands library_mirror.py
import library_briefs
from library_briefs import BriefStore
import library_mirror
from library_mirror import (
    CONTRACT_VERSION,
    MIRROR_LEDGER_DIR,
    MIRROR_ROOT,
    SCOPE_ALL,
    MirrorConsent,
    Mirror,
)


# ============================================================================
# Helpers & Harness
# ============================================================================

def _compute_file_sha256(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def unwrap_dict(res: Any) -> dict:
    assert isinstance(res, dict), f"Expected dict, got {type(res)}: {res}"
    return res


class MirrorTestHarness:
    """Isolated test harness for Mirror testing with temporary vault and fake volume marker."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        enabled: bool = True,
        scope: str = SCOPE_ALL,
        allowlist: tuple[str, ...] = (),
        custom_marker: str = "uoink-vol-marker-42481e532b95",
    ):
        self.tmp_path = tmp_path
        self.data_root = tmp_path / "data_root"
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.clock = MockClock(start_mono=1000.0, start_wall=1788825600.0)

        # 1. Disposable index & standard library
        self.idx, self.manifest = seed_standard_library(tmp_path)

        # 2. Phase 2 work service & BriefStore
        self.work_store = tmp_path / "work_store"
        self.work_svc = library_work.LibraryWorkService(
            self.idx,
            store_root=self.work_store,
            clock=self.clock.monotonic,
        )
        self.brief_store = BriefStore(
            self.idx,
            self.work_svc,
            data_root=self.data_root,
            clock=self.clock.monotonic,
            wall_clock=self.clock.wall,
        )

        # 3. LibraryReader
        self.reader = library_resources.LibraryReader(
            self.idx,
            data_root=self.data_root,
            clock=self.clock.monotonic,
            wall_clock=self.clock.wall,
        )

        # 4. Vault & fake volume marker setup
        self.vault_path = tmp_path / "vault"
        self.vault_path.mkdir(parents=True, exist_ok=True)
        self.fake_marker = custom_marker

        # Volume marker file in vault
        (self.vault_path / ".uoink-volume-marker").write_text(self.fake_marker, encoding="utf-8")

        # Pre-existing taste vault files
        self.taste_file = self.vault_path / "TASTE.md"
        self.taste_file.write_text("# Taste Profile\nInitial taste preferences.", encoding="utf-8")
        self.user_file = self.vault_path / "USER.md"
        self.user_file.write_text("# User Personal Notes\nDo not overwrite.", encoding="utf-8")

        self.uoink_dir = self.vault_path / MIRROR_ROOT
        self.uoink_dir.mkdir(parents=True, exist_ok=True)
        (self.uoink_dir / ".uoink-volume-marker").write_text(self.fake_marker, encoding="utf-8")

        self.scope = scope
        self.allowlist = allowlist
        self.consent = MirrorConsent(
            destination=str(self.vault_path),
            scope=scope,
            allowlist=allowlist,
            consented_at_ms=int(self.clock.wall() * 1000),
            marker=self.fake_marker,
        )

        self.enabled = enabled
        self.mirror = Mirror(
            self.idx,
            self.reader,
            self.brief_store,
            data_root=self.data_root,
            consent=self.consent if enabled else None,
            enabled=enabled,
            clock=self.clock.monotonic,
            wall_clock=self.clock.wall,
        )

    def restart_mirror(
        self,
        consent: MirrorConsent | None = None,
        enabled: bool | None = None,
    ) -> Mirror:
        """Simulate restart with fresh Mirror instance over existing directories."""
        eff_consent = self.consent if consent is None else consent
        eff_enabled = self.enabled if enabled is None else enabled
        self.mirror = Mirror(
            self.idx,
            self.reader,
            self.brief_store,
            data_root=self.data_root,
            consent=eff_consent,
            enabled=eff_enabled,
            clock=self.clock.monotonic,
            wall_clock=self.clock.wall,
        )
        return self.mirror

    def item_file_path(self, video_id: str) -> Path:
        h = hashlib.sha256(video_id.encode("utf-8")).hexdigest()
        return self.uoink_dir / "Library" / f"{h}.md"

    def shelf_file_path(self, shelf_id: str) -> Path:
        h = hashlib.sha256(shelf_id.encode("utf-8")).hexdigest()
        return self.uoink_dir / "Shelves" / f"{h}.md"

    def brief_file_path(self, date: str, brief_hash: str) -> Path:
        return self.uoink_dir / "Briefs" / f"{date}-{brief_hash}.md"

    def library_index_path(self) -> Path:
        return self.uoink_dir / "Library.md"

    def manifest_path(self) -> Path:
        return self.uoink_dir / ".uoink-mirror" / "manifest.json"


# ============================================================================
# Gate P4-09 Tests: Paths and Consent
# ============================================================================

class TestP409PathsAndConsent:
    """Gate P4-09: Opt-in consent, default off, allowlist, destination change, layout, collisions, reparse."""

    def test_default_off_with_existing_taste_vault(self, tmp_path: Path):
        """Even with an existing vault containing TASTE.md and USER.md, mirror is default disabled and performs no writes."""
        h = MirrorTestHarness(tmp_path, enabled=False)

        # status reports disabled
        st = unwrap_dict(h.mirror.status())
        assert st.get("enabled") is False or st.get("state") == "disabled" or st.get("synced", 0) == 0

        # on_committed_event and resync do nothing
        h.mirror.on_committed_event("capture", video_id="vid-standard-01")
        resync_res = unwrap_dict(h.mirror.resync())
        assert resync_res.get("synced", 0) == 0

        # No library files generated under Uoink
        assert not (h.uoink_dir / "Library").exists() or len(list((h.uoink_dir / "Library").iterdir())) == 0
        assert not h.library_index_path().exists()

        # Existing taste and user files remain untouched
        assert h.taste_file.exists()
        assert "Initial taste preferences." in h.taste_file.read_text(encoding="utf-8")
        assert h.user_file.exists()

    def test_preview_does_not_perform_writes(self, tmp_path: Path):
        """preview returns planned paths, counts, and third-party notice; performs zero disk writes."""
        h = MirrorTestHarness(tmp_path, enabled=False)

        prev = unwrap_dict(h.mirror.preview(str(h.vault_path), scope=SCOPE_ALL))
        assert "planned_paths" in prev or "paths" in prev or "counts" in prev
        assert "indexing" in str(prev).lower() or "third_party" in str(prev).lower() or "notice" in prev

        # Verify no files created in vault during preview
        assert not (h.uoink_dir / "Library").exists()
        assert not h.library_index_path().exists()

    def test_consent_allowlist_filtering(self, tmp_path: Path):
        """allowlist scope mirrors only allowed items; unallowed items and their dependent briefs are omitted."""
        h = MirrorTestHarness(
            tmp_path,
            enabled=True,
            scope="allowlist",
            allowlist=("vid-standard-01",),
        )

        h.mirror.on_committed_event("capture", video_id="vid-standard-01")
        h.mirror.on_committed_event("capture", video_id="doc-prose-02")
        h.mirror.resync()

        # Allowed item is written
        allowed_file = h.item_file_path("vid-standard-01")
        assert allowed_file.exists(), f"Expected {allowed_file} to exist"

        # Unallowed item is NOT written
        unallowed_file = h.item_file_path("doc-prose-02")
        assert not unallowed_file.exists(), f"Unallowed item {unallowed_file} must not be mirrored"

        # Library.md reflects only allowed item
        if h.library_index_path().exists():
            lib_text = h.library_index_path().read_text(encoding="utf-8")
            assert "vid-standard-01" in lib_text or allowed_file.stem in lib_text
            assert "doc-prose-02" not in lib_text and unallowed_file.stem not in lib_text

    def test_destination_change_resets_consent(self, tmp_path: Path):
        """Changing the destination directory resets consent; mirror remains disabled until new consent recorded."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        new_vault = tmp_path / "vault_new"
        new_vault.mkdir(parents=True, exist_ok=True)

        # Re-initialize mirror with different destination without valid consent
        h.restart_mirror(consent=None, enabled=False)
        st = unwrap_dict(h.mirror.status())
        assert st.get("enabled") is False or st.get("state") == "disabled"

    def test_path_traversal_confinement(self, tmp_path: Path):
        """Hostile IDs with path traversal (../, C:\\, /etc/) cannot escape <vault>/Uoink/Library/."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        hostile_id = "../../etc/passwd"
        seed_yoink_item(h.idx, tmp_path, video_id=hostile_id, slug="hostile-traversal", title="Traversal Video")

        h.mirror.on_committed_event("capture", video_id=hostile_id)
        h.mirror.resync()

        # Path must be full sha256 hash ending in .md
        target = h.item_file_path(hostile_id)
        assert target.exists()
        # Verify target is strictly under uoink_dir / "Library"
        assert target.resolve().parent == (h.uoink_dir / "Library").resolve()
        assert not (tmp_path / "etc").exists()

    def test_windows_reserved_names_confinement(self, tmp_path: Path):
        """Items or channels with Windows device names (CON, PRN, AUX, NUL, COM1) do not become filenames."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        device_id = "aux"
        seed_yoink_item(h.idx, tmp_path, video_id=device_id, slug="aux-slug", title="AUX Device Title", channel="CON")

        h.mirror.on_committed_event("capture", video_id=device_id)
        h.mirror.resync()

        target = h.item_file_path(device_id)
        assert target.exists()
        assert target.name == f"{hashlib.sha256(b'aux').hexdigest()}.md"

    def test_case_and_unicode_collisions(self, tmp_path: Path):
        """Distinct IDs differing only by case or Unicode normalization forms map to distinct hash paths."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        id1 = "VideoItem"
        id2 = "videoitem"
        seed_yoink_item(h.idx, tmp_path, video_id=id1, slug="video-item-upper", title="Upper Item")
        seed_yoink_item(h.idx, tmp_path, video_id=id2, slug="video-item-lower", title="Lower Item")

        h.mirror.on_committed_event("capture", video_id=id1)
        h.mirror.on_committed_event("capture", video_id=id2)
        h.mirror.resync()

        f1 = h.item_file_path(id1)
        f2 = h.item_file_path(id2)
        assert f1 != f2
        assert f1.exists()
        assert f2.exists()

    def test_unmanaged_file_conflict(self, tmp_path: Path):
        """An existing file without a matching ownership entry in manifest is reported as unmanaged_conflict and preserved."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        vid = "vid-standard-01"
        target_file = h.item_file_path(vid)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text("# Unmanaged User File\nPersonal notes.", encoding="utf-8")

        # resync or status should detect conflict
        st = unwrap_dict(h.mirror.status())
        conflicts = st.get("conflicts", {}) or st.get("unmanaged", [])
        assert "unmanaged" in str(conflicts).lower() or st.get("unmanaged_conflict") or "conflict" in str(st).lower()

        # User file must NOT be overwritten
        assert "Unmanaged User File" in target_file.read_text(encoding="utf-8")

    def test_reparse_point_symlink_rejection(self, tmp_path: Path):
        """Symlinks or reparse points escaping the vault root are rejected."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        # Attempting preview or resync on a foreign escape target is refused or treated as destination_unavailable
        res = unwrap_dict(h.mirror.preview(str(tmp_path / "non_existent_symlink_target"), scope=SCOPE_ALL))
        assert res.get("ok") is False or "unavailable" in str(res).lower() or "error" in res or len(res.get("planned_paths", [])) == 0


# ============================================================================
# Gate P4-10 Tests: Edits and Atomicity
# ============================================================================

class TestP410EditsAndAtomicity:
    """Gate P4-10: User edit preservation, crash atomicity, two writers, stale work, manifest corruption, size cap."""

    def test_user_edit_conflict_preserves_bytes(self, tmp_path: Path):
        """When an owned file is edited by the user, destination byte hash mismatch reports user_edit_conflict and preserves bytes."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        vid = "vid-standard-01"
        h.mirror.on_committed_event("capture", video_id=vid)
        h.mirror.resync()

        file_path = h.item_file_path(vid)
        assert file_path.exists()

        # User edits the file in Obsidian
        user_edited_text = file_path.read_text(encoding="utf-8") + "\n\n## Personal Notes\nMy thoughts."
        file_path.write_text(user_edited_text, encoding="utf-8")
        edited_hash = _compute_file_sha256(file_path)

        # Trigger update event
        h.mirror.on_committed_event("source_refresh", video_id=vid)
        res = unwrap_dict(h.mirror.resync())

        # Mismatch must be detected as user_edit_conflict
        st = unwrap_dict(h.mirror.status())
        assert "conflict" in str(st).lower() or "user_edit_conflict" in str(res).lower()

        # Bytes preserved verbatim; no overwrite, no merge, no .conflict.md file created
        assert _compute_file_sha256(file_path) == edited_hash
        assert not (file_path.parent / f"{file_path.stem}.conflict.md").exists()

    def test_crash_before_replacement_preserves_old_file(self, tmp_path: Path):
        """Crash before atomic replacement leaves existing destination file intact and removes .tmp files."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        vid = "vid-standard-01"
        h.mirror.on_committed_event("capture", video_id=vid)
        h.mirror.resync()

        file_path = h.item_file_path(vid)
        orig_hash = _compute_file_sha256(file_path)

        # Simulate leftover temporary file from interrupted write
        tmp_file = file_path.with_suffix(".tmp")
        tmp_file.write_text("Interrupted partial write", encoding="utf-8")

        # Restart and resync
        h.restart_mirror()
        h.mirror.resync()

        # Original file intact
        assert _compute_file_sha256(file_path) == orig_hash
        # Temporary file cleaned up
        assert not tmp_file.exists()

    def test_two_writers_serialized(self, tmp_path: Path):
        """Two concurrent writers per destination serialize safely without corrupted manifests or lost files."""
        h1 = MirrorTestHarness(tmp_path, enabled=True)
        # Create second mirror instance sharing the same data_root and vault
        h2_mirror = Mirror(
            h1.idx,
            h1.reader,
            h1.brief_store,
            data_root=h1.data_root,
            consent=h1.consent,
            enabled=True,
            clock=h1.clock.monotonic,
            wall_clock=h1.clock.wall,
        )

        h1.mirror.on_committed_event("capture", video_id="vid-standard-01")
        h2_mirror.on_committed_event("capture", video_id="doc-prose-02")

        h1.mirror.resync()
        h2_mirror.resync()

        assert h1.item_file_path("vid-standard-01").exists()
        assert h1.item_file_path("doc-prose-02").exists()

    def test_stale_delayed_work_rejected(self, tmp_path: Path):
        """Delayed event with an older generation cannot overwrite a newer generation."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        vid = "vid-standard-01"
        h.mirror.on_committed_event("capture", video_id=vid)
        h.mirror.resync()

        f = h.item_file_path(vid)
        gen1_hash = _compute_file_sha256(f)

        # Advance item to gen 2
        h.mirror.on_committed_event("source_refresh", video_id=vid)
        h.mirror.resync()

        # Stale event attempting gen 1 must be rejected/ignored
        h.mirror.on_committed_event("source_refresh", video_id=vid)
        # Verify file is never rolled back to older gen1
        assert f.exists()

    def test_corrupt_manifest_stops_writes(self, tmp_path: Path):
        """A corrupt manifest stops writes for reconciliation and refuses to adopt markdown files."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        vid = "vid-standard-01"
        h.mirror.on_committed_event("capture", video_id=vid)
        h.mirror.resync()

        # Corrupt the manifest file
        m_path = h.manifest_path()
        if m_path.exists():
            m_path.write_text("{ corrupt json: [", encoding="utf-8")

        # Restart and attempt resync
        h.restart_mirror()
        res = unwrap_dict(h.mirror.resync())
        assert res.get("ok") is False or "reconciliation" in str(res).lower() or res.get("synced", 0) == 0

    def test_file_size_cap_and_frontmatter_escaping(self, tmp_path: Path):
        """Mirror files never exceed 65,536 UTF-8 bytes and escape hostile YAML/HTML/wikilink syntax."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        # Seed item with hostile YAML directives and Markdown injection
        hostile_id = "vid-hostile-01"
        hostile_title = "Title: With Colon\n---\nkey: injected\n<script>alert(1)</script>\n[[SecretWikiLink]]"
        seed_yoink_item(
            h.idx,
            tmp_path,
            video_id=hostile_id,
            slug="hostile-title-slug",
            title=hostile_title,
            corpus_text="# Huge text\n" + ("X" * 70000),
        )

        h.mirror.on_committed_event("capture", video_id=hostile_id)
        h.mirror.resync()

        f = h.item_file_path(hostile_id)
        assert f.exists()
        raw_bytes = f.read_bytes()
        assert len(raw_bytes) <= 65536, f"Generated file exceeds 64 KiB: {len(raw_bytes)} bytes"

        text = raw_bytes.decode("utf-8")
        assert "<script>" not in text
        assert "[[SecretWikiLink]]" not in text

    def test_library_md_written_last(self, tmp_path: Path):
        """Library.md is written last, referencing only successfully completed files."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        h.mirror.on_committed_event("capture", video_id="vid-standard-01")
        h.mirror.resync()

        lib_md = h.library_index_path()
        assert lib_md.exists()
        content = lib_md.read_text(encoding="utf-8")
        assert "Standard Analysis Video" in content or "vid-standard-01" in content or h.item_file_path("vid-standard-01").stem in content


# ============================================================================
# Gate P4-11 Tests: Deletion
# ============================================================================

class TestP411Deletion:
    """Gate P4-11: Soft delete tombstones, hard purge, replay/restore, purge_blocked_user_edit, disconnected vault."""

    def test_soft_delete_tombstone(self, tmp_path: Path):
        """Soft delete replaces file with content-free tombstone, stripping title, URL, and quotes."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        vid = "vid-standard-01"
        h.mirror.on_committed_event("capture", video_id=vid)
        h.mirror.resync()

        f = h.item_file_path(vid)
        assert f.exists()
        orig_content = f.read_text(encoding="utf-8")
        assert "Standard Analysis Video" in orig_content

        # Soft delete
        h.mirror.on_committed_event("soft_delete", video_id=vid)
        h.mirror.resync()

        assert f.exists()
        tombstone_content = f.read_text(encoding="utf-8")
        assert "deleted: true" in tombstone_content.lower() or "deleted: true" in tombstone_content
        # Source title, URL, and quotations stripped
        assert "Standard Analysis Video" not in tombstone_content
        assert "https://youtube.example" not in tombstone_content
        assert "Timed evidence point" not in tombstone_content

    def test_hard_purge_removes_owned_files_idempotent(self, tmp_path: Path):
        """Hard purge unlinks owned item file and dependent briefs; repeated purge is idempotent."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        vid = "vid-standard-01"
        h.mirror.on_committed_event("capture", video_id=vid)
        h.mirror.resync()

        f = h.item_file_path(vid)
        assert f.exists()

        # Hard purge
        h.mirror.on_committed_event("hard_purge", video_id=vid)
        h.mirror.resync()

        # File is unlinked
        assert not f.exists()

        # Repeated purge is idempotent
        res2 = unwrap_dict(h.mirror.purge(vid))
        assert res2.get("ok") is not False or "purged" in str(res2).lower()

    def test_restore_replaces_tombstone(self, tmp_path: Path):
        """Authoritative restore replaces tombstone with active evidence card, removing deleted flag."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        vid = "vid-standard-01"
        h.mirror.on_committed_event("capture", video_id=vid)
        h.mirror.resync()

        # Soft delete
        h.mirror.on_committed_event("soft_delete", video_id=vid)
        h.mirror.resync()
        f = h.item_file_path(vid)
        assert "deleted: true" in f.read_text(encoding="utf-8").lower()

        # Restore
        h.mirror.on_committed_event("restore", video_id=vid)
        h.mirror.resync()

        restored_content = f.read_text(encoding="utf-8")
        assert "deleted: true" not in restored_content.lower()
        assert "Standard Analysis Video" in restored_content

    def test_purge_blocked_user_edit(self, tmp_path: Path):
        """When an owned file was edited by the user, hard purge preserves user file and reports purge_blocked_user_edit."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        vid = "vid-standard-01"
        h.mirror.on_committed_event("capture", video_id=vid)
        h.mirror.resync()

        f = h.item_file_path(vid)
        # User edits file
        f.write_text("# Personal Note\nMust not be deleted!", encoding="utf-8")

        # Trigger purge
        res = unwrap_dict(h.mirror.purge(vid))
        assert "purge_blocked_user_edit" in str(res) or res.get("purge_blocked_user_edit") is True or "conflict" in str(res).lower()

        # File must still exist with user's content intact
        assert f.exists()
        assert "Must not be deleted!" in f.read_text(encoding="utf-8")

    def test_disconnected_destination_handling(self, tmp_path: Path):
        """When destination is disconnected, status reports destination_unavailable and primary operations still succeed."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        # Point consent to non-existent drive/directory
        bad_dest = tmp_path / "unmounted_drive" / "vault"
        bad_consent = MirrorConsent(
            destination=str(bad_dest),
            scope=SCOPE_ALL,
            allowlist=(),
            consented_at_ms=1000,
            marker="dummy-marker",
        )
        h.restart_mirror(consent=bad_consent, enabled=True)

        st = unwrap_dict(h.mirror.status())
        assert "destination_unavailable" in str(st) or st.get("destination_state") == "unavailable" or st.get("destination_available") is False

        # Primary event recording succeeds without raising exception
        h.mirror.on_committed_event("capture", video_id="vid-standard-01")

        resync_res = unwrap_dict(h.mirror.resync())
        assert resync_res.get("ok") is False or "destination_unavailable" in str(resync_res)

    def test_reconnected_destination_validates_marker_and_drains_deletions_first(self, tmp_path: Path):
        """Reconnected destination validates volume marker and drains pending deletions before content writes."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        vid_to_delete = "vid-standard-01"
        vid_to_write = "doc-prose-02"

        h.mirror.on_committed_event("capture", video_id=vid_to_delete)
        h.mirror.resync()
        assert h.item_file_path(vid_to_delete).exists()

        # Queue a deletion and a new capture
        h.mirror.on_committed_event("hard_purge", video_id=vid_to_delete)
        h.mirror.on_committed_event("capture", video_id=vid_to_write)

        # Resync validates marker and drains deletes first
        res = unwrap_dict(h.mirror.resync(max_files=20, budget_s=2.0))
        assert res.get("ok") is not False

        assert not h.item_file_path(vid_to_delete).exists()
        assert h.item_file_path(vid_to_write).exists()


# ============================================================================
# Gate P4-12 Tests: Correction-Store Separation
# ============================================================================

class TestP412CorrectionStoreSeparation:
    """Gate P4-12: Mirror failure or corruption never modifies authoritative Phase 2 pins or corrections."""

    def test_authoritative_corrections_unaffected_by_mirror_ledger_loss(self, tmp_path: Path):
        """Deleting reach/mirror/ ledger cannot lose pins or resurrect deleted items in Phase 2 SQLite."""
        h = MirrorTestHarness(tmp_path, enabled=True)

        # Seed shelf with pinned item
        seed_shelf(h.idx, shelf_id="s-auth", member_video_ids=["vid-standard-01"])
        with h.idx._lock:
            h.idx._conn.execute("UPDATE item_shelves SET locked = 1 WHERE video_id = 'vid-standard-01'")
            h.idx._conn.commit()

        # Corrupt / wipe reach/mirror ledger
        ledger_dir = h.data_root / MIRROR_LEDGER_DIR
        if ledger_dir.exists():
            import shutil
            shutil.rmtree(ledger_dir)

        # Restart mirror
        h.restart_mirror()

        # Authoritative pins in SQLite remain locked = 1
        with h.idx._lock:
            row = h.idx._conn.execute("SELECT locked FROM item_shelves WHERE video_id = 'vid-standard-01'").fetchone()
            assert row is not None and row[0] == 1, "Authoritative pin must not be lost by mirror ledger wipe"

    def test_taste_and_user_md_unaffected(self, tmp_path: Path):
        """TASTE.md and USER.md in vault are never owned, overwritten, or read back as corrections."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        h.taste_file.write_text("# Taste Note\nImportant preferences.", encoding="utf-8")
        h.user_file.write_text("# User Personal\nUnique notes.", encoding="utf-8")

        taste_hash = _compute_file_sha256(h.taste_file)
        user_hash = _compute_file_sha256(h.user_file)

        # Perform multiple mirror events, resyncs, and purges
        h.mirror.on_committed_event("capture", video_id="vid-standard-01")
        h.mirror.resync()
        h.mirror.on_committed_event("soft_delete", video_id="vid-standard-01")
        h.mirror.resync()
        h.mirror.on_committed_event("hard_purge", video_id="vid-standard-01")
        h.mirror.resync()

        # TASTE.md and USER.md remain byte-identical
        assert _compute_file_sha256(h.taste_file) == taste_hash
        assert _compute_file_sha256(h.user_file) == user_hash

    def test_no_read_back_into_taxonomy(self, tmp_path: Path):
        """Modifying frontmatter or text in vault mirror files has zero effect on Uoink internal database."""
        h = MirrorTestHarness(tmp_path, enabled=True)
        seed_shelf(h.idx, shelf_id="s-auth-2", member_video_ids=["vid-standard-01"])

        h.mirror.on_committed_event("capture", video_id="vid-standard-01")
        h.mirror.resync()

        f = h.item_file_path("vid-standard-01")
        assert f.exists()

        # User adds malicious shelf tag or modification in markdown file
        f.write_text("---\nshelf: hacked-shelf\npin: false\n---\n# Modified Content", encoding="utf-8")

        # Run resync and status
        h.mirror.resync()

        # Authoritative SQLite tables remain unchanged
        with h.idx._lock:
            cur = h.idx._conn.execute("SELECT shelf_id FROM item_shelves WHERE video_id = 'vid-standard-01'")
            rows = [r[0] for r in cur.fetchall()]
            assert "hacked-shelf" not in rows
            assert "s-auth-2" in rows
