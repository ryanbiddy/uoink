"""Independent expected-byte verifier; never import builder or wheel members."""
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tomllib

RECIPE_SHA256 = "a30b6ca4b87b9317d8232a284434c069b91ff0fe6d1874e903de1bfafb947581"
VERSION = "3.8.6+uoink.owned1"
DIST = "whisperx-3.8.6+uoink.owned1.dist-info"
NAME = "whisperx-3.8.6+uoink.owned1-py3-none-any.whl"
RECORD_NAME = DIST + "/RECORD"
SOURCE_NAMES = (
    "SubtitlesProcessor.py", "__init__.py", "__main__.py", "_uoink_owned.py",
    "alignment.py", "asr.py", "audio.py", "conjunctions.py", "diarize.py",
    "log_utils.py", "schema.py", "transcribe.py", "utils.py", "vads/__init__.py",
    "vads/pyannote.py", "vads/silero.py", "vads/vad.py",
)
EXPECTED = {"whisperx/" + n for n in SOURCE_NAMES} | {
    DIST + "/" + n for n in ("LICENSE", "UOINK-NOTICE.txt", "METADATA", "WHEEL")}


def check(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_bytes(wheel, recipe_raw, sources):
    check(type(wheel) is bytes and len(wheel) <= 1048576, "Wheel byte/type bound")
    check(type(recipe_raw) is bytes and sha(recipe_raw) == RECIPE_SHA256, "Recipe identity")
    recipe = json.loads(recipe_raw)
    rows = recipe["fixed_members"]
    check(len(rows) == 21 and {r["member"] for r in rows} == EXPECTED, "Exact member set")
    check(set(sources) == {r["input"] for r in rows} | {"after/pyproject.toml", "after/README-UOINK.md"},
          "Exact source membership")
    check(all(type(b) is bytes and len(b) <= 262144 for b in sources.values())
          and sum(map(len, sources.values())) <= 1048576, "Source byte bounds")
    payloads = {}
    for row in rows:
        raw = sources[row["input"]]
        check(len(raw) == row["bytes"] and sha(raw) == row["sha256"], "Source binding: " + row["member"])
        raw.decode("utf-8", "strict")
        check(b"\0" not in raw, "Text contains NUL")
        payloads[row["member"]] = raw
    check(sha(sources["after/pyproject.toml"]) == recipe["input_pyproject_sha256"], "Pyproject binding")
    check(sha(sources["after/README-UOINK.md"]) == recipe["input_readme_sha256"], "README binding")
    project_doc = tomllib.loads(sources["after/pyproject.toml"].decode("utf-8"))
    project = project_doc["project"]
    header, body = payloads[DIST + "/METADATA"].split(b"\n\n", 1)
    check(body == sources["after/README-UOINK.md"], "Metadata body")
    fields = {}
    for line in header.decode("utf-8").split("\n"):
        check(": " in line and not line.startswith((" ", "\t")), "Metadata header grammar")
        key, value = line.split(": ", 1)
        fields.setdefault(key, []).append(value)
    expected = {
        "Metadata-Version": ["2.1"], "Name": ["whisperx"], "Version": [VERSION],
        "Summary": [project["description"]], "Author": [project["authors"][0]["name"]],
        "License": [project["license"]["text"]], "Requires-Python": [">=3.10, <3.14"],
        "Project-URL": ["Repository, " + project["urls"]["repository"]],
        "Description-Content-Type": ["text/markdown"], "Provides-Extra": ["dev"],
        "Requires-Dist": project["dependencies"] + ['pytest; extra == "dev"'],
    }
    check(fields == expected and project["name"] == "whisperx" and project["version"] == VERSION
          and project["requires-python"] == ">=3.10, <3.14" and "scripts" not in project,
          "Exact metadata/project agreement")
    codec = [d for d in project["dependencies"] if d.startswith("torchcodec==")]
    check(len(codec) == 1 and project_doc["tool"]["uv"]["override-dependencies"] == codec,
          "Duplicated TorchCodec declaration")
    # Independent RECORD formatting: permitted member names need no CSV quoting.
    lines = []
    for name in sorted(payloads):
        check(not any(c in name for c in ',"\r\n\\') and name.isascii(), "Member grammar")
        raw = payloads[name]
        encoded = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode("ascii").rstrip("=")
        lines.append(name + ",sha256=" + encoded + "," + str(len(raw)) + "\n")
    lines.append(RECORD_NAME + ",,\n")
    payloads[RECORD_NAME] = "".join(lines).encode("utf-8")
    # Independent byte layout, not ZipFile parsing or the builder's serializer.
    # Equality covers headers, CRCs, attributes, ordering, extents and all bytes;
    # it rejects prefix/trailing data, duplicate members, descriptors and extras.
    local = bytearray()
    central = bytearray()
    for name in sorted(payloads):
        raw = payloads[name]
        encoded = name.encode("ascii")
        size = len(raw)
        crc = binascii.crc32(raw) & 0xFFFFFFFF
        offset = len(local)
        local += struct.pack("<4s5H3L2H", b"PK\x03\x04", 20, 0, 0, 0, 33,
                             crc, size, size, len(encoded), 0) + encoded + raw
        central += struct.pack("<4s6H3L5H2L", b"PK\x01\x02", 788, 20, 0, 0, 0, 33,
                               crc, size, size, len(encoded), 0, 0, 0, 0, 2175008768, offset) + encoded
    ending = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 22, 22, len(central), len(local), 0)
    check(wheel == bytes(local + central) + ending, "Wheel differs from exact independent layout")
    return {"sha256": sha(wheel), "bytes": len(wheel), "members": 22, "record_rows": 22,
            "all_payloads_verified": True, "complete_byte_layout_verified": True}


def read_owned(path, limit):
    for p in reversed((path,) + tuple(path.parents)):
        value = p.lstat()
        check(not stat.S_ISLNK(value.st_mode) and not getattr(value, "st_file_attributes", 0) & 0x400,
              "Linked/reparse input")
        check(stat.S_ISREG(value.st_mode) if p == path else stat.S_ISDIR(value.st_mode), "Input kind")
    before = path.stat()
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    after = path.stat()
    fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
    check(all(getattr(before, f) == getattr(after, f) for f in fields), "Input changed during read")
    check(len(raw) <= limit, "Read byte bound")
    return raw


def main():
    check(sys.argv[1:] == ["build01"], "Unbriefed verification label")
    check(sys.version_info[:2] == (3, 13) and sys.flags.isolated and sys.flags.no_site
          and sys.flags.dont_write_bytecode, "Isolated Python 3.13 required")
    check(os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db",
          "Startup binding absent")
    base = Path(__file__).resolve().parent
    inputs = base / "inputs"
    run = base / "runs" / "build01"
    try:
        recipe_raw = read_owned(inputs / "WHEEL-RECIPE.json", 262144)
        check(sha(recipe_raw) == RECIPE_SHA256, "Recipe identity before path use")
        recipe = json.loads(recipe_raw)
        names = {r["input"] for r in recipe["fixed_members"]} | {
            "after/pyproject.toml", "after/README-UOINK.md"}
        sources = {n: read_owned(inputs / n, 262144) for n in names}
        wheel = read_owned(run / NAME, 1048576)
        result = verify_bytes(wheel, recipe_raw, sources)
        hashes = {n: sha(b) for n, b in sources.items()}
        hashes["WHEEL-RECIPE.json"] = sha(recipe_raw)
        # Read-only identity recheck; generated wheel is not installed/imported.
        check(all(sha(read_owned(inputs / n, 262144)) == d for n, d in hashes.items()),
              "Input changed after verification")
        result.update(exit=0, input_hashes=hashes, inputs_unchanged=True)
    except Exception as error:
        result = {"exit": 1, "error_type": type(error).__name__, "error": str(error)}
    with (run / "independent-verification.json").open("xb") as stream:
        stream.write((json.dumps(result, indent=2) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps(result))
    return result["exit"]


if __name__ == "__main__":
    raise SystemExit(main())
