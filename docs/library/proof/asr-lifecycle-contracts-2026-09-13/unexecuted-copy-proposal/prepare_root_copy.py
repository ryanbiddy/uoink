"""Root-reviewed data-only copy preparation; no tests or candidate imports."""
import hashlib
import json
from pathlib import Path

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch")
SOURCE = BASE / "asr-windows-lifecycle-proposal02"
DEST = BASE / "astra-lifecycle-state01"
PINS = {
    "snapshot_lifecycle.py": "a80514aac6b1e75b9b872052852fa993a23cd5273b6bed4ffb4eef7404cb69dd",
    "qualify_lifecycle.py": "563539d579a6584029f6596d6cba5de375976b6ada02535108cc195cb4fc3de7",
    "EXPECTED-CASES.json": "a03a8da9270ec47ec796e19a3b6795f9861cea65b6e577fc21a617bffe8d6228",
    "run_lifecycle02.ps1": "d31b87ae38c0345eef4952999d7691af08aa2855cde5e04a6efd14ee029da375",
}
old_path = str(SOURCE).encode("ascii")
new_path = str(DEST).encode("ascii")
raw = {}
for name, expected in PINS.items():
    data = (SOURCE / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Qualified source changed: " + name)
    raw[name] = data
if raw["run_lifecycle02.ps1"].count(old_path) != 1:
    raise ValueError("Expected one absolute launcher proposal path")
if DEST.exists():
    raise ValueError("Fresh independent copy directory required")
DEST.mkdir()
rows = []
output_pins = {}
for name, data in raw.items():
    result = data.replace(old_path, new_path) if name == "run_lifecycle02.ps1" else data
    with (DEST / name).open("xb") as stream:
        stream.write(result)
    expected = hashlib.sha256(result).hexdigest()
    if hashlib.sha256((DEST / name).read_bytes()).hexdigest() != expected:
        raise ValueError("Copied bytes changed")
    if hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() != PINS[name]:
        raise ValueError("Author input changed during copy")
    output_pins[name] = expected
    rows.append({"name": name, "source_sha256": PINS[name], "copy_sha256": expected,
                 "source_bytes": len(data), "copy_bytes": len(result),
                 "change": "one absolute proposal path substitution" if name.endswith(".ps1") else "none"})
cases = json.loads(raw["EXPECTED-CASES.json"])["ordered_cases"]
if len(cases) != 46 or len(set(cases)) != 46:
    raise ValueError("Case binding refused")
bindings = {"schema": "uoink.lifecycle-independent-copy.v1", "source": str(SOURCE), "destination": str(DEST),
            "inputs": rows, "case_count": 46, "executed_cases": 0, "source_after_unchanged": True}
(DEST / "COPY-BINDINGS.json").write_text(json.dumps(bindings, indent=2) + "\n", encoding="utf-8")
admission = {"schema": "uoink.lifecycle-root-admission.v1", "root_reviewed": False,
             "scope": "lifecycle-fake-ports-46-only", "label": "lcs02", "input_sha256": output_pins,
             "expected_cases": cases, "real_kernel_or_model_execution": False, "registry_api_calls": False}
(DEST / "ROOT-ADMISSION-TEMPLATE.json").write_text(json.dumps(admission, indent=2) + "\n", encoding="utf-8")
print(json.dumps(bindings, indent=2))
