"""Prepare exact documentary-control delta; no case or candidate execution."""
from pathlib import Path
import ast
import difflib
import hashlib
import json

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch")
OLD = BASE / "controller-handshake-contracts01"
HERE = BASE / "controller-handshake-contracts02"
LAUNCHER = "run_handshake01.ps1"
OLD_LAUNCHER_SHA = "b3fe96646c4f1601c5a8af5da08ed905ceab5cfbd47b6cb34d8905cd8dd41488"


def read(path):
    with path.open("rb") as stream:
        raw = stream.read(1048577)
    assert len(raw) <= 1048576
    return raw


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(name, raw):
    with (HERE / name).open("xb") as stream:
        stream.write(raw if isinstance(raw, bytes) else raw.encode())


def replace(text, old, new):
    assert text.count(old) == 1
    return text.replace(old, new)


previous = json.loads(read(OLD / "INPUTS.json"))
assert previous["input_sha256"][LAUNCHER] == OLD_LAUNCHER_SHA
for name, expected in previous["input_sha256"].items():
    raw = read(OLD / name)
    assert sha(raw) == expected
    if name == LAUNCHER:
        save("run_handshake01-before-controls.ps1", raw)
    else:
        if name.endswith(".py"):
            ast.parse(raw)
        save(name, raw)
original = read(OLD / LAUNCHER).decode()
launcher = replace(original, str(OLD), str(HERE))
launcher = replace(launcher, "$taskAdmission=Get-Content", "$taskAdmissionHash=(Get-FileHash -LiteralPath $taskAdmissionPath -Algorithm SHA256).Hash.ToLowerInvariant()\n$taskAdmission=Get-Content")
launcher = replace(launcher, "$taskExpectedCases=Get-Content", "$taskRecords += [ordered]@{name='ROOT-ADMISSION.json';source=$taskAdmissionPath;sha256=$taskAdmissionHash}\n$taskExpectedCases=Get-Content")
launcher = replace(launcher, "Copy-Item -LiteralPath $taskAdmissionPath -Destination (Join-Path $taskRun 'ROOT-ADMISSION.json') -ErrorAction Stop\n", "")
save(LAUNCHER, launcher)
save("launcher-control.diff", "".join(difflib.unified_diff(original.splitlines(True), launcher.splitlines(True), fromfile="proposal01/" + LAUNCHER, tofile="proposal02/" + LAUNCHER)))
hashes = {name: sha(read(HERE / name)) for name in previous["input_sha256"]}
template = json.loads(read(OLD / "ADMISSION-TEMPLATE.json"))
assert template["root_reviewed"] is False
template["input_sha256"] = hashes
save("ADMISSION-TEMPLATE.json", json.dumps(template, indent=2) + "\n")
save("INPUTS.json", json.dumps({"schema": "uoink.handshake-control-repair-inputs.v1", "input_sha256": hashes,
    "prior_launcher_sha256": OLD_LAUNCHER_SHA, "case_source_harness_bytes_unchanged": True,
    "source_and_control_after_records": 7, "candidate_executed": False}, indent=2) + "\n")
print(json.dumps({"inputs": hashes, "control_after_records": 7, "candidate_executed": False}))
