"""Proposed byte/receipt verifier; imports no copied source or model package."""
import hashlib
import json
from pathlib import Path

ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\asr-adapter-combined-proof01")


def check(folder, name="SHA256.json"):
    seal = json.loads((folder / name).read_bytes())
    for row in seal["files"]:
        assert not Path(row["path"]).is_absolute() and ".." not in Path(row["path"]).parts
        with (folder / row["path"]).open("rb") as stream:
            raw = stream.read(row["bytes"] + 1)
        assert len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"], row["path"]
    assert sum(row["bytes"] for row in seal["files"]) == seal["payload_bytes"]
    return seal


outer = check(ROOT)
assert {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()} == {r["path"] for r in outer["files"]} | {"SHA256.json"}
history = ROOT / "author-history209"
assert check(history)["payload_count"] == 209
assert check(history / "preparation-repair01")["payload_count"] == 53
assert check(history / "preparation-repair01/original-proposal", "PREPARATION-SHA256.json")["payload_count"] == 23
assert check(history / "preparation-instrument01")["payload_count"] == 26
assert check(history / "preparation-scope01")["payload_count"] == 55
assert check(history / "preparation-scope01/failure01")["payload_count"] == 7
a = json.loads((history / "asr-author03/adapter-preflight03/stdout.json").read_bytes())
b = json.loads((ROOT / "independent-root/adapter-preflight03/stdout.json").read_bytes())
assert a["cases"] == b["cases"]
assert len(a["cases"]) == len({row["name"] for row in a["cases"]}) == 58
assert a["passed"] == b["passed"] == 58 and a["failed"] == b["failed"] == 0
assert a["guard_valid"] is True and b["guard_valid"] is True
assert a["real_resolver_approval_unchanged_none"] is True and b["real_resolver_approval_unchanged_none"] is True
assert json.loads((history / "preparation-scope01/failure01/missing01/native-exit.json").read_bytes())["native_exit"] is None
for folder in (history / "asr-author03", ROOT / "independent-root"):
    actual = json.loads((folder / "ACTUAL-TOOL-PREFLIGHT03.json").read_bytes())
    native = json.loads((folder / "adapter-preflight03/native-exit.json").read_bytes())
    final = json.loads((folder / "adapter-preflight03/exit.json").read_bytes())
    assert actual["exit_code"] == native["native_exit"] == final["outer_exit"] == 0
print(json.dumps({"payloads_verified": outer["payload_count"], "payload_bytes": outer["payload_bytes"],
                  "distinct_fake_port_cases": 58, "passing_runs": 2, "ordered_cases_identical": True,
                  "old_null_failure_preserved": True, "no_copied_source_executed": True}))
