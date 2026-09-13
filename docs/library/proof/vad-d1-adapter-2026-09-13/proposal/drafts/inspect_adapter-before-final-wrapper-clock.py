"""D1 static inspection proposal. The real entry is closed pending owner approval.

Only the version and two fixed buffers are interpreted. No conversion/model calls.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

import buffer_basis
import fixed_converter as archive
from zip_bounds import Refusal, require

ORIGINAL_SHA256 = "0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea"
ORIGINAL_SIZE = 17719103
KNOWN_INVENTORY_SHA256 = "73ef1afe29719273272b4c27e0139a6d00393408455ec68f659bc53608c3fdcc"
MAX_INPUT = 32 * 1024 * 1024
MAX_RECEIPT = 16 * 1024
EXPECTED_VERSION = b"3\n"  # Source-derived expectation, not an observed real value.
EXPECTED_NAMES = tuple(sorted(("archive/data.pkl", "archive/version", *("archive/data/" + str(i) for i in range(129)))))
SELECTED = (("archive/data/4", 500), ("archive/data/5", 500), ("archive/version", 2))
ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
REAL_INPUT = ROOT / "installer/staging/python/Lib/site-packages/whisperx/assets/pytorch_model.bin"
REAL_OUTPUT_ROOT = ROOT / "_scratch/vad-buffer-version-approved-output"
D1_OWNER_APPROVAL = None


@dataclass(frozen=True)
class InspectionProfile:
    purpose: str
    profile_id: str
    archive_sha256: str
    archive_size: int
    members: tuple  # sorted (name, advertised bytes, CRC32) triples, no objects.

    @property
    def expected_member_names(self):
        return tuple(row[0] for row in self.members)

    @property
    def archive_version(self):
        return EXPECTED_VERSION


@dataclass(frozen=True)
class InspectionApproval:
    profile: InspectionProfile
    owner_decision_sha256: str


def _profile(profile):
    require(archive.REAL_PROFILE is None, "D1 cannot share an active conversion profile")
    require(type(profile) is InspectionProfile, "Explicit D1 inspection profile required")
    require(type(profile.purpose) is str and type(profile.profile_id) is str
            and re.fullmatch(r"[a-z0-9-]{1,64}", profile.profile_id), "D1 profile field refused")
    require(type(profile.archive_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", profile.archive_sha256), "D1 artifact digest refused")
    require(type(profile.archive_size) is int and 22 <= profile.archive_size <= MAX_INPUT, "D1 artifact size bound")
    require(type(profile.members) is tuple and len(profile.members) == 131, "D1 exact 131-member inventory required")
    total = 0
    for row in profile.members:
        require(type(row) is tuple and len(row) == 3, "D1 inventory record type")
        name, size, crc = row
        require(type(name) is str and name in EXPECTED_NAMES, "D1 inventory name refused")
        require(type(size) is int and 0 <= size <= MAX_INPUT and type(crc) is int and 0 <= crc <= 0xFFFFFFFF, "D1 inventory size/CRC type or bound")
        total += size
    require(profile.expected_member_names == EXPECTED_NAMES and total <= MAX_INPUT, "D1 exact ordered inventory or total bound")
    sizes = {name: size for name, size, _ in profile.members}
    require(all(sizes[name] == size for name, size in SELECTED), "D1 selected member lengths must be 500/500/2")
    if profile.purpose == "synthetic":
        require(profile.archive_sha256 != ORIGINAL_SHA256, "Synthetic D1 profile cannot authorize original artifact")
    else:
        require(profile.purpose == "real" and type(D1_OWNER_APPROVAL) is InspectionApproval
                and D1_OWNER_APPROVAL.profile is profile, "D1 real owner approval is absent")
        decision = D1_OWNER_APPROVAL.owner_decision_sha256
        require(type(decision) is str and re.fullmatch(r"[0-9a-f]{64}", decision), "D1 owner decision digest refused")
        require(profile.archive_sha256 == ORIGINAL_SHA256 and profile.archive_size == ORIGINAL_SIZE, "D1 real artifact identity is fixed")
        encoded = json.dumps(profile.members, ensure_ascii=True, separators=(",", ":")).encode("ascii")
        require(hashlib.sha256(encoded).hexdigest() == KNOWN_INVENTORY_SHA256, "D1 real inventory differs from fixed observed inventory")


def _base():
    return {"scope": "D1 static version and two fixed buffers only",
            "status": "pending", "version_expected_hex": EXPECTED_VERSION.hex(),
            "version_expected_is_source_prediction": True,
            "model_or_tensor_constructed": False, "pickle_interpreted": False,
            "other_storage_values_interpreted": False, "conversion_performed": False,
            "conversion_profile_activated": False, "release_approved": False,
            "historical_writer_authenticated": False}


def _inspect(raw, profile, started, facts):
    _profile(profile)
    require(type(raw) is bytes and 22 <= len(raw) <= MAX_INPUT, "D1 immutable snapshot or size bound")
    require(len(raw) == profile.archive_size, "D1 snapshot size differs from pinned profile")
    digest = hashlib.sha256(raw).hexdigest()
    require(digest == profile.archive_sha256, "D1 snapshot SHA256 differs from pinned profile")
    archive.clock_check(started)
    facts["input"] = {"bytes": len(raw), "sha256": digest, "profile_id": profile.profile_id,
                      "synthetic": profile.purpose == "synthetic"}
    # This unchanged structural parser accepts the names/version view of our D1
    # profile. It neither calls conversion's _profile nor assumes scalar endian.
    members = archive.inspect_stored_zip(raw, profile, started)
    for name, size, crc in profile.members:
        start, end, observed_crc, _ = members[name]
        require(end - start == size and observed_crc == crc, "D1 member size/CRC differs from exact inventory")
    archive.clock_check(started)
    facts["zip"] = {"members": len(members), "all_member_crc_verified": True,
                    "exact_inventory_verified": True}
    selected = {}
    selected_report = []
    for name, size in SELECTED:
        start, end, _, _ = members[name]
        require(end - start == size, "D1 selected payload length mismatch")
        payload = raw[start:end]
        selected[name] = payload
        selected_report.append({"name": name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    facts["selected_members"] = selected_report
    facts["version_actual_hex"] = selected["archive/version"].hex()
    facts["interpreted_payload_bytes"] = 1002
    archive.clock_check(started)
    result = buffer_basis.compare_buffers(selected["archive/data/4"], selected["archive/data/5"])
    archive.clock_check(started)
    facts["buffer_basis"] = result
    facts["status"] = "static_inspection_complete_unqualified"


def _encode(facts, started):
    facts["elapsed_seconds"] = round(time.monotonic() - started, 6)
    encoded = (json.dumps(facts, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("ascii")
    require(len(encoded) <= MAX_RECEIPT, "D1 receipt byte bound exceeded")
    archive.clock_check(started)  # Includes serialization before success returns.
    return encoded


def inspect_snapshot(raw, profile):
    """Return (bounded JSON bytes, actual inspection exit) without filesystem I/O."""
    started, facts, exit_code = time.monotonic(), _base(), 0
    try:
        _inspect(raw, profile, started, facts)
    except (Refusal, buffer_basis.BasisRefusal) as error:
        facts["status"], facts["reason"], exit_code = "refused", str(error)[:180], 2
    except Exception as error:
        facts["status"], facts["error_class"], exit_code = "error", type(error).__name__[:80], 1
    try:
        return _encode(facts, started), exit_code
    except (Refusal, ValueError, TypeError):
        fallback = b'{"status":"refused","reason":"receipt limit or deadline","conversion_profile_activated":false}\n'
        return (fallback if len(fallback) <= MAX_RECEIPT else b""), 2


def inspect_reviewed_real_file(output_name):
    """Dormant exact-path wrapper. Approval guard precedes all real path access."""
    require(type(D1_OWNER_APPROVAL) is InspectionApproval, "D1 real inspection awaits owner approval")
    started = time.monotonic()
    profile = D1_OWNER_APPROVAL.profile
    require(type(profile) is InspectionProfile and profile.purpose == "real", "D1 wrapper requires a real inspection profile")
    _profile(profile)
    require(type(output_name) is str and re.fullmatch(r"[a-z0-9-]{1,64}\.json", output_name), "D1 output basename refused")
    source = archive.contained_unlinked(REAL_INPUT, ROOT, must_exist=True)
    destination = archive.contained_unlinked(REAL_OUTPUT_ROOT / output_name, REAL_OUTPUT_ROOT, must_exist=False)
    with source.open("rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size == ORIGINAL_SIZE, "D1 regular input file or exact size mismatch")
        snapshot = stream.read(MAX_INPUT + 1)
        after = os.fstat(stream.fileno())
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), "D1 input changed during snapshot")
    archive.clock_check(started)
    receipt, exit_code = inspect_snapshot(snapshot, profile)
    archive.clock_check(started)
    # Private quiescent roots are required. A short/late write is unaccepted;
    # the outer/native exit is required alongside any resulting receipt file.
    with destination.open("xb") as stream:
        require(stream.write(receipt) == len(receipt), "D1 short receipt write")
        stream.flush()
        os.fsync(stream.fileno())
    archive.clock_check(started)
    return {"inspection_exit": exit_code, "receipt_bytes": len(receipt),
            "receipt_sha256": hashlib.sha256(receipt).hexdigest(),
            "whole_file_elapsed_seconds": round(time.monotonic() - started, 6),
            "conversion_profile_activated": False, "release_approved": False}
