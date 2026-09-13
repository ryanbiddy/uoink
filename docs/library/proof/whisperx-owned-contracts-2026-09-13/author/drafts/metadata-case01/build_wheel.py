"""Proposed exact-text wheel builder. No source/package code is imported."""
import base64
import csv
from email.parser import BytesParser
from email.policy import compat32
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tomllib
import zipfile

RECIPE_SHA256 = "0e07485c7607a9462b4e56d910347983dcb2e03e673091092d99022d0e198747"
VERSION = "3.8.6+uoink.owned1"
DIST = "whisperx-" + VERSION + ".dist-info"
WHEEL_NAME = "whisperx-" + VERSION + "-py3-none-any.whl"
PYTHON_FILES = (
    "SubtitlesProcessor.py", "__init__.py", "__main__.py", "_uoink_owned.py",
    "alignment.py", "asr.py", "audio.py", "conjunctions.py", "diarize.py",
    "log_utils.py", "schema.py", "transcribe.py", "utils.py",
    "vads/__init__.py", "vads/pyannote.py", "vads/silero.py", "vads/vad.py",
)
MEMBERS = {"whisperx/" + name for name in PYTHON_FILES} | {
    DIST + "/" + name for name in ("LICENSE", "UOINK-NOTICE.txt", "METADATA", "WHEEL")
}
RECORD = DIST + "/RECORD"


class Refusal(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Refusal(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate recipe key")
        result[key] = value
    return result


def checked_recipe(raw):
    require(type(raw) is bytes and len(raw) <= 262144, "Recipe byte bound")
    require(digest(raw) == RECIPE_SHA256, "Recipe identity mismatch")
    recipe = json.loads(raw, object_pairs_hook=no_duplicates)
    require(recipe["version"] == VERSION and recipe["output_name"] == WHEEL_NAME,
            "Version/output mismatch")
    rows = recipe["fixed_members"]
    require(len(rows) == 21 and {r["member"] for r in rows} == MEMBERS,
            "Exact fixed membership required")
    require(recipe["generated_record"]["member"] == RECORD and recipe["member_count"] == 22,
            "RECORD membership mismatch")
    return recipe


def validate_snapshot(recipe_raw, files):
    recipe = checked_recipe(recipe_raw)
    expected = {r["input"] for r in recipe["fixed_members"]} | {
        "after/pyproject.toml", "after/README-UOINK.md"}
    require(type(files) is dict and set(files) == expected, "Exact input set required")
    require(all(type(value) is bytes and len(value) <= 262144 for value in files.values()),
            "Text input byte/type bound")
    require(sum(map(len, files.values())) <= 1048576, "Aggregate input bound")
    for raw in files.values():
        require(b"\0" not in raw, "NUL in text input")
        raw.decode("utf-8", "strict")
    for row in recipe["fixed_members"]:
        raw = files[row["input"]]
        require(len(raw) == row["bytes"] and digest(raw) == row["sha256"],
                "Fixed text payload mismatch: " + row["member"])
    for name, field in (("after/pyproject.toml", "input_pyproject_sha256"),
                        ("after/README-UOINK.md", "input_readme_sha256")):
        require(digest(files[name]) == recipe[field], "Metadata input identity mismatch")
    project_doc = tomllib.loads(files["after/pyproject.toml"].decode("utf-8"))
    project = project_doc["project"]
    metadata_raw = files["recipe-inputs/METADATA"]
    header, body = metadata_raw.split(b"\n\n", 1)
    require(b"\r" not in header and body == files["after/README-UOINK.md"],
            "Metadata description mismatch")
    metadata = BytesParser(policy=compat32).parsebytes(metadata_raw)
    require(not metadata.defects, "Metadata parse defects")
    for field in metadata.keys():
        require(field in {"Metadata-Version", "Name", "Version", "Summary", "Author", "License",
                          "Project-URL", "Requires-Python", "Description-Content-Type",
                          "Requires-Dist", "Provides-Extra"}, "Unexpected metadata header")
        if field != "Requires-Dist":
            require(len(metadata.get_all(field)) == 1, "Duplicate metadata header")
    expected_headers = {
        "Metadata-Version": "2.1", "Name": project["name"], "Version": project["version"],
        "Summary": project["description"], "Author": project["authors"][0]["name"],
        "License": project["license"]["text"], "Requires-Python": project["requires-python"],
        "Description-Content-Type": "text/markdown", "Provides-Extra": "dev",
        "Project-URL": "Repository, https://github.com/m-bain/whisperX",
    }
    for name, value in expected_headers.items():
        require(metadata[name] == value, "Metadata/pyproject disagreement: " + name)
    require(project["name"] == "whisperx" and project["version"] == VERSION
            and project["requires-python"] == ">=3.10, <3.14", "Package identity mismatch")
    require(project["readme"] == "README-UOINK.md" and "scripts" not in project,
            "Unexpected readme/entry points")
    require(project["optional-dependencies"] == {"dev": ["pytest"]}, "Extra dependency mismatch")
    require(metadata.get_all("Requires-Dist") == project["dependencies"] + ['pytest; extra == "dev"'],
            "Exact dependency agreement required")
    codec = [d for d in project["dependencies"] if d.startswith("torchcodec==")]
    require(len(codec) == 1 and project_doc["tool"]["uv"]["override-dependencies"] == codec,
            "TorchCodec override disagreement")
    require(files["after/LICENSE"].startswith(b"BSD 2-Clause License\n"), "License mismatch")
    require(VERSION.encode() in files["after/UOINK-NOTICE.txt"], "Notice identity mismatch")
    require(b"_RUNTIME = None\n" in files["after/whisperx/_uoink_owned.py"], "Runtime gate changed")
    return {row["member"]: files[row["input"]] for row in recipe["fixed_members"]}


def build_bytes(recipe_raw, files):
    payloads = validate_snapshot(recipe_raw, files)
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name in sorted(payloads):
        raw = payloads[name]
        encoded = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode("ascii")
        writer.writerow((name, "sha256=" + encoded, str(len(raw))))
    writer.writerow((RECORD, "", ""))
    payloads[RECORD] = record.getvalue().encode("utf-8")
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.create_version = info.extract_version = 20
            info.external_attr = 2175008768
            info.internal_attr = 0
            info.compress_type = zipfile.ZIP_STORED
            info.extra = info.comment = b""
            archive.writestr(info, payloads[name])
    result = target.getvalue()
    require(len(result) <= 1048576, "Wheel byte bound")
    return result


def read_text(root, relative):
    parts = PurePosixPath(relative)
    require(not parts.is_absolute() and str(parts) == relative and not set(parts.parts) & {".", ".."},
            "Noncanonical input name")
    path = root.joinpath(*parts.parts)
    # This bounds an owned quiescent source directory; it is not a Windows
    # handle lease for a future model/runtime consumer.
    for component in reversed((path,) + tuple(path.parents)):
        info = component.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "Linked/reparse source path")
        require(stat.S_ISREG(info.st_mode) if component == path else stat.S_ISDIR(info.st_mode),
                "Unexpected source path type")
    before = path.stat()
    with path.open("rb") as stream:
        raw = stream.read(262145)
    after = path.stat()
    fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
    require(tuple(getattr(before, f) for f in fields) == tuple(getattr(after, f) for f in fields),
            "Source changed during read")
    require(len(raw) <= 262144, "Text read bound")
    return raw


def snapshot(root):
    recipe_raw = read_text(root, "WHEEL-RECIPE.json")
    recipe = checked_recipe(recipe_raw)
    names = {r["input"] for r in recipe["fixed_members"]} | {
        "after/pyproject.toml", "after/README-UOINK.md"}
    files = {name: read_text(root, name) for name in sorted(names)}
    return recipe_raw, files


def write_new(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def main():
    require(sys.argv[1:] == ["build01"], "Unbriefed build label")
    require(sys.version_info[:2] == (3, 13) and sys.flags.isolated and sys.flags.no_site
            and sys.flags.dont_write_bytecode, "Isolated Python 3.13 required")
    require(os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db",
            "Missing startup binding")
    base = Path(__file__).resolve().parent
    run = base / "runs" / "build01"
    run.mkdir(parents=True, exist_ok=False)
    try:
        recipe, files = snapshot(base / "inputs")
        hashes = {name: digest(raw) for name, raw in files.items()}
        hashes["WHEEL-RECIPE.json"] = digest(recipe)
        write_new(run / "inputs-before.json", (json.dumps(hashes, indent=2) + "\n").encode())
        wheel = build_bytes(recipe, files)
        write_new(run / WHEEL_NAME, wheel)
        after_recipe, after_files = snapshot(base / "inputs")
        after = {name: digest(raw) for name, raw in after_files.items()}
        after["WHEEL-RECIPE.json"] = digest(after_recipe)
        write_new(run / "inputs-after.json", (json.dumps(after, indent=2) + "\n").encode())
        require(after == hashes, "Inputs changed after build")
        result = {"exit": 0, "sha256": digest(wheel), "bytes": len(wheel), "members": 22,
                  "inputs_unchanged": True, "package_imported_or_installed": False}
    except Exception as error:
        result = {"exit": 1, "error_type": type(error).__name__, "error": str(error)}
    write_new(run / "result.json", (json.dumps(result, indent=2) + "\n").encode())
    print(json.dumps(result))
    return result["exit"]


if __name__ == "__main__":
    raise SystemExit(main())
