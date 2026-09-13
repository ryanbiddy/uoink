"""Read-only documentary verifier. Never execute/extract archived source."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile
import zlib

MAX_FILES = 1024
MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 8 * 1024 * 1024
PREP_SHA = "f0e7b975f089ab176b9db97a234e6cc2d42ae717594d454f35223aebfc2d0e93"
AUTHOR_SHA = "5fe7c83b25895b7fd43a021b04c7ed129e0d468fccd63dfd36676a2d26468c84"


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def relpath(value):
    need(type(value) is str and value and "\\" not in value and ":" not in value, "Noncanonical proof path")
    path = PurePosixPath(value)
    need(bool(path.parts) and not path.is_absolute() and str(path) == value and all(p not in (".", "..") for p in path.parts), "Escaping proof path")
    return value


def bounded(path):
    item = path.lstat()
    need(stat.S_ISREG(item.st_mode) and not getattr(item, "st_file_attributes", 0) & 0x400, "Nonregular/reparse evidence")
    need(0 <= item.st_size <= MAX_FILE, "Evidence file bound")
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read(MAX_FILE + 1)
        after = os.fstat(stream.fileno())
    fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
    need(tuple(getattr(before, k) for k in fields) == tuple(getattr(after, k) for k in fields), "Evidence changed during read")
    need(stat.S_ISREG(before.st_mode) and len(raw) == before.st_size <= MAX_FILE, "Evidence read bound/type")
    return raw


def inventory(root):
    found = set()
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            item = (Path(directory) / name).lstat()
            need(stat.S_ISDIR(item.st_mode) and not getattr(item, "st_file_attributes", 0) & 0x400, "Linked evidence directory")
        for name in files:
            found.add(relpath((Path(directory) / name).relative_to(root).as_posix()))
            need(len(found) <= MAX_FILES, "Evidence file-count bound")
    return found


def check_original(raw, prefix, virtual, count, digest):
    need(sha(raw) == digest, "Original manifest changed")
    manifest = decode(raw)
    need(manifest["payload_count"] == count == len(manifest["files"]), "Original seal count")
    names, total = set(), 0
    for entry in manifest["files"]:
        name = prefix + "/" + relpath(entry["path"])
        need(name not in names and name in virtual, "Missing/duplicate original payload")
        names.add(name)
        body = virtual[name]
        need(len(body) == entry["bytes"] and sha(body) == entry["sha256"], "Original payload changed")
        total += len(body)
    need(total == manifest["payload_bytes"], "Original payload byte total")
    return names


def check_runs(virtual):
    observed = []
    for label, elapsed in (("author-run", 5.7517623), ("root-run", 5.657456)):
        def record(name):
            return decode(virtual[label + "/" + name])
        result, outer, tool = record("result.json"), record("exit.json"), record("actual-outer-tool-result.json")
        need((result["repaired_passed"], result["repaired_failed"], result["original_diagnostic_count"], result["original_diagnostics_matched"]) == (12, 0, 4, 4), "Run count mismatch")
        need(result["elapsed_seconds"] == elapsed and result["qualification_exit"] == 0, "Run elapsed/exit mismatch")
        need(result["inputs_unchanged"] is True and result["actual_d1_invoked"] is False and result["original_wrapper_qualified"] is False, "Run scope/status mismatch")
        need(outer["native_qualifier_exit"] == outer["outer_exit"] == tool["exit_code"] == 0, "Actual native/outer mismatch")
        need(outer["inputs_unchanged"] is True and outer["result_valid"] is True and outer["stderr_bytes"] == 0, "Outer validation refused")
        need(not virtual[label + "/qualifier-stderr.log"] and virtual[label + "/native-exit.txt"].strip() == b"0", "Raw qualifier exit/stderr")
        expected_names = [f"repaired-{pref}-{code}" for pref in ("false", "true") for code in range(4)]
        expected_names += [f"repaired-postcheck-{code}" for code in range(4)] + [f"original-true-{code}" for code in range(4)]
        need([case["name"] for case in result["cases"]] == expected_names, "Ordered case membership differs")
        for case in result["cases"]:
            name = case["name"]
            prefix = "cases/" + name + "/"
            caller = record(prefix + "caller-observation.json")
            process = record(prefix + "actual-process-exit.json")
            child = record(prefix + "outer-d1-real-01/stdout.log")
            requested = case["requested_native_exit"]
            need(case["expectations_matched"] is True and case["timed_out"] is False, "Unexpected case failure")
            need(caller["last_native_exit"] == requested == child["requested_exit"], "Native exit evidence differs")
            need(caller["caller_process_exit"] == process["actual_caller_process_exit"] == case["actual_caller_process_exit"], "Caller process exit differs")
            need(process["timed_out"] is False and process["process_error_type"] is None, "Process error/timeout")
            need(child["scope"] == "uoink-d1-wrapper-fixture-v1" and child["d1_source_executed"] is False and child["startup_binding_asserted"] is True, "Wrong child scope")
            need(not virtual[label + "/" + prefix + "process-stderr.log"] and not virtual[label + "/" + prefix + "outer-d1-real-01/stderr.log"], "Unexpected case stderr")
            receipt_path = label + "/" + prefix + "outer-d1-real-01/actual-exit.json"
            if name.startswith("repaired-"):
                need(case["diagnostic_only"] is False, "Repair mislabeled diagnostic")
                need(virtual[label + "/" + prefix + "outer-d1-real-01/raw-exit.txt"] == f"{requested}\n".encode("ascii"), "Raw durable native exit differs")
                need(decode(virtual[receipt_path])["actual_outer_exit"] == requested, "Native JSON exit differs")
                if "postcheck" in name:
                    need(caller["caller_process_exit"] == 91 and caller["exception_message"] == "INTENTIONAL_D1_WRAPPER_POSTCHECK_FAILURE", "Late failure incorrectly labeled")
                else:
                    need(caller["caller_process_exit"] == requested and caller["disposition"] == "wrapper_returned", "Propagation differs")
            else:
                need(case["diagnostic_only"] is True, "Original diagnostic added to passes")
                if requested:
                    need(receipt_path not in virtual and caller["caller_process_exit"] == 91 and caller["exception_type"].endswith("NativeCommandExitException"), "Original defect was not retained")
                else:
                    need(decode(virtual[receipt_path])["actual_outer_exit"] == caller["caller_process_exit"] == 0, "Original control differs")
        after, plan = record("after.json"), record("plan.json")
        need(len(after) == len(plan["inputs"]) == 13, "Input record count differs")
        need({entry["name"] for entry in after} == {entry["name"] for entry in plan["inputs"]}, "Input membership differs")
        for item in after:
            body = virtual[label + "/" + relpath(item["name"])]
            need(sha(body) == item["before_sha256"] == item["copy_after_sha256"] == item["source_after_sha256"], "Input identity changed")
        observed.append(result)
    need(observed[0]["cases"] == observed[1]["cases"], "Root/author ordered case records differ")
    bindings = decode(virtual["root-copy/COPY-BINDINGS.json"])
    need(len(bindings) == 12 and len({row["name"] for row in bindings}) == 12, "Root copy membership")
    for row in bindings:
        name = relpath(row["name"])
        original, copied = virtual["preparation/" + name], virtual["root-copy/" + name]
        need(sha(original) == row["source_sha256"] and sha(copied) == row["copy_sha256"], "Root copy hash mismatch")
        if name == "run_preflight01.ps1":
            before = br"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\vad-d1-dormant-invocation-repair01"
            after = br"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\astra-d1-wrapper-qualification01"
            need(original.count(before) == 1 and original.replace(before, after) == copied and row["only_change"] == "fixed root proposal path", "Root launcher delta exceeded path change")
        else:
            need(original == copied and row["only_change"] is None, "Unexpected root copy change")
    return {"author_repaired_passed": 12, "root_repaired_passed": 12, "each_original_diagnostic_count": 4,
            "ordered_case_records_equal": True, "each_input_count": 13, "root_copy_bindings_verified": 12,
            "all_qualification_native_outer_exits": 0, "test_or_d1_program_executed_by_verifier": False}


def verify(root):
    root = Path(root)
    manifest_raw = bounded(root / "SHA256.json")
    manifest = decode(manifest_raw)
    need(len(manifest["files"]) == manifest["payload_count"] <= MAX_FILES, "Root manifest count")
    disk, total = {}, 0
    for item in manifest["files"]:
        name = relpath(item["path"])
        need(name not in disk and name != "SHA256.json", "Duplicate/self manifest member")
        raw = bounded(root / name)
        need(len(raw) == item["bytes"] and sha(raw) == item["sha256"], "Root payload mismatch: " + name)
        disk[name] = raw
        total += len(raw)
        need(total <= MAX_TOTAL, "Root aggregate byte bound")
    need(total == manifest["payload_bytes"] and inventory(root) == set(disk) | {"SHA256.json"}, "Root exact membership/total differs")
    archive = {}
    with zipfile.ZipFile(io.BytesIO(disk["case-trees.zip"])) as zipped:
        infos = zipped.infolist()
        need(len(infos) == 370 and [i.filename for i in infos] == sorted(i.filename for i in infos), "Exact sorted case archive membership")
        archive_total = 0
        for info in infos:
            name = relpath(info.filename)
            need(name not in archive and not info.is_dir() and info.compress_type == zipfile.ZIP_STORED, "Duplicate/unsupported ZIP member")
            need(info.date_time == (1980, 1, 1, 0, 0, 0) and info.create_system == 3 and info.external_attr == (0o100644 << 16), "ZIP deterministic metadata differs")
            need(not info.extra and not info.comment and 0 <= info.file_size <= 128 * 1024, "ZIP metadata/member bound")
            body = zipped.read(info)
            need(len(body) == info.file_size and zlib.crc32(body) & 0xFFFFFFFF == info.CRC, "ZIP size/CRC differs")
            archive[name] = body
            archive_total += len(body)
            need(archive_total <= MAX_TOTAL, "ZIP aggregate bound")
    mapping = decode(disk["SOURCE-MAP.json"])
    need(mapping["source_file_count"] == len(mapping["files"]) == 460, "Source map count")
    virtual, source_names, zip_names = {}, set(), set()
    for item in mapping["files"]:
        logical = relpath(item["logical_path"])
        need(logical not in virtual and item["source"] not in source_names, "Duplicate mapped source")
        source_names.add(item["source"])
        if item["storage"] == "zip":
            need(item["member"] == logical and logical in archive, "Missing mapped archive member")
            zip_names.add(logical)
            raw = archive[logical]
        else:
            need(item["storage"] == "file" and item["destination"] == logical and logical in disk, "Missing mapped disk payload")
            raw = disk[logical]
        need(len(raw) == item["bytes"] and sha(raw) == item["sha256"], "Mapped byte/hash differs")
        virtual[logical] = raw
    need(zip_names == set(archive), "Unmapped archive members")
    zip_index = decode(disk["ZIP-MEMBERS.json"])
    indexed = {item["member"]: item for item in zip_index["members"]}
    need(len(indexed) == len(zip_index["members"]) == 370 and set(indexed) == set(archive), "Archive index membership")
    for item in mapping["files"]:
        if item["storage"] == "zip":
            need(indexed[item["member"]] == {key: item[key] for key in ("member", "source", "bytes", "sha256")}, "Archive/source map disagreement")
    check_original(virtual["preparation/original-SHA256.json"], "preparation", virtual, 26, PREP_SHA)
    check_original(virtual["author-run/original-RUN-SHA256.json"], "author-run", virtual, 209, AUTHOR_SHA)
    need(sha(virtual["root-preparation/prepare_astra_d1_wrapper_qualification01.py"]) == "abc5d3fa14ca7d5973fd0e9d174acd0b4a6ee38af8a07c20eb4db0c20cffa211", "Root preparer changed")
    summary = check_runs(virtual)
    summary.update(payload_count=len(disk), payload_bytes=total, source_files=460, archive_members=370,
                   preparation_payloads_verified=26, author_run_payloads_verified=209,
                   proof_manifest_sha256=sha(manifest_raw))
    return summary


if __name__ == "__main__":
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, "Use isolated no-site/no-bytecode Python")
    need(os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db", "Required startup string binding")
    need(len(sys.argv) == 2, "Usage: python -I -S -B verify_proof.py PROOF_DIRECTORY")
    print(json.dumps(verify(Path(sys.argv[1])), indent=2))
