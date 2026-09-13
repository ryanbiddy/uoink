"""Generate inert instrument scripts as text; no generated code execution."""
import ast
import hashlib
import json
from pathlib import Path

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
OLD = BASE / "_scratch/asr-production-adapter-qualification-repair01"
OUT = BASE / "_scratch/asr-production-adapter-instrument-check01"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(name, raw):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw if isinstance(raw, bytes) else raw.encode())


seal_raw = (OLD / "SHA256.json").read_bytes()
assert sha(seal_raw) == "34e4a40216547273f5813fa55dbf7affbc369173c68fd8e4e3e5c7b442a2817e"
old_seal = json.loads(seal_raw)
for row in old_seal["files"]:
    raw = (OLD / row["path"]).read_bytes()
    assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]
runner_raw = (OLD / "run_preflight02.ps1").read_bytes()
harness_raw = (OLD / "qualify_adapter.py").read_bytes()
runner = runner_raw.decode()
harness = harness_raw.decode()
write("sources/run_preflight02.ps1", runner_raw)
write("sources/qualify_adapter.py", harness_raw)
block = runner.split("# BEGIN EXACT NATIVE RECEIPT BLOCK\n", 1)[1].split("# END EXACT NATIVE RECEIPT BLOCK", 1)[0]
assert block.encode() == (OLD / "NATIVE-RECEIPT-BLOCK.ps1.txt").read_bytes()
post = runner[runner.index("$taskAfter=@()"):]
write("native-block.ps1.txt", block)
write("postchecks.ps1.txt", post)
installation = harness[harness.index("def metadata_trap("):harness.index("@contextlib.contextmanager")]
final = harness[harness.index("metadata_trap_mismatches ="):harness.index("result = {\"schema\":")]
write("trap-installation.py.txt", installation)
write("trap-final.py.txt", final)
text_bytes = b"INERT WRAPPER POSTCHECK TEXT ONLY\n"
text_hash = sha(text_bytes)

child_start = r'''"""Inert wrapper receipt source. No ASR cases or package imports."""
import json
import os
import sys
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
assert os.environ.get("TORCH_DEVICE_BACKEND_AUTOLOAD") == "0"
HEAVY = {"torch", "torchaudio", "torchvision", "torchcodec", "whisperx", "faster_whisper", "ctranslate2", "transformers", "tokenizers", "pyannote", "onnxruntime", "numpy"}
assert not HEAVY.intersection(name.split(".")[0] for name in sys.modules)
def audit(event, args):
    if event in ("open", "import") or event.startswith(("os.", "socket.", "subprocess.", "ctypes.", "winreg.")):
        raise AssertionError("Inert wrapper child boundary refused " + event)
sys.addaudithook(audit)
'''
write("child-one.py", child_start + 'print("Intentional inert child failure; no ASR qualification")\nsys.exit(1)\n')
receipt = {"schema": "uoink.inert-asr-adapter-qualification.v1", "passed": 58, "failed": 0,
           "cases": [{"name": f"fabricated-parser-row-{i:02d}", "passed": True} for i in range(58)],
           "input_sha256": {"instrument.txt": text_hash}, "qualification_exit": 0,
           "startup_binding_asserted": True, "torch_backend_autoload_disabled_before_startup": True,
           "real_resolver_approval_unchanged_none": True, "real_resolver_functions_unchanged": True,
           "adapter_globals_restored": True, "guard_valid": True, "metadata_traps_installed": True,
           "metadata_trap_count": 11, "metadata_trap_mismatches": [], "guard_denials": [], "heavy_roots_loaded": [],
           "scope": "Fabricated parser input only; zero ASR cases executed"}
write("child-zero.py", child_start + "print(" + repr(json.dumps(receipt)) + ")\nsys.exit(0)\n")

for label, child, missing in (("missing01", "child-one.py", True), ("success01", "child-zero.py", False)):
    prefix = f'''$ErrorActionPreference='Stop'
# The function inherits true from this enclosing scope before the exact block.
$PSNativeCommandUseErrorActionPreference=$true
function Invoke-InertWrapper {{
    $taskRun=Join-Path $PSScriptRoot 'runs\\instrument01\\{label}'
    if(Test-Path -LiteralPath $taskRun){{throw 'Fresh instrument case required'}}
    New-Item -ItemType Directory -Path $taskRun -ErrorAction Stop | Out-Null
    $taskPython='C:\\Python314\\python.exe'
    $taskStdout=Join-Path $taskRun 'stdout.json'
    $taskStderr=Join-Path $taskRun 'stderr.log'
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot '{child}') -Destination (Join-Path $taskRun 'qualify_adapter.py') -ErrorAction Stop
    $taskExpected=@{{'instrument.txt'='{text_hash}'}}
    $taskRecords=@([ordered]@{{name='instrument.txt';source=(Join-Path $taskRun 'source.txt');sha256='{text_hash}'}})
    [ordered]@{{label='{label}';inherited_native_error_preference=$PSNativeCommandUseErrorActionPreference;missing_postcheck_expected=${str(missing).lower()};asr_cases_executed=0}} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRun 'setup.json') -Encoding utf8
    if($PSNativeCommandUseErrorActionPreference -cne $true){{throw 'True inherited preference required'}}
'''
    if not missing:
        prefix += "    [IO.File]::WriteAllBytes((Join-Path $taskRun 'source.txt'),[Convert]::FromBase64String('SU5FUlQgV1JBUFBFUiBQT1NUQ0hFQ0sgVEVYVCBPTkxZCg=='))\n"
        prefix += "    Copy-Item -LiteralPath (Join-Path $taskRun 'source.txt') -Destination (Join-Path $taskRun 'instrument.txt') -ErrorAction Stop\n"
    content = prefix + "# BEGIN EXACT NATIVE RECEIPT BLOCK\n" + block + "# END EXACT NATIVE RECEIPT BLOCK\n" + post + "\n}\nInvoke-InertWrapper\n"
    write("wrapper-" + label + ".ps1", content)

write("PREPARATION-BINDINGS.json", json.dumps({"date": "2026-09-13", "prior_seal_sha256": sha(seal_raw),
      "prior_53_payloads_verified": True, "runner_sha256": sha(runner_raw), "harness_sha256": sha(harness_raw),
      "native_block_sha256": sha(block.encode()), "postchecks_sha256": sha(post.encode()),
      "trap_installation_sha256": sha(installation.encode()), "trap_final_sha256": sha(final.encode()),
      "synthetic_text_sha256": text_hash, "planned_wrapper_outcomes": 2, "planned_guard_checks": 4,
      "asr_cases_executed": 0, "any_generated_code_executed": False}, indent=2) + "\n")
write(".gitattributes", "* -text\n")
write("prepare_asr_instrument_subset01.py", Path(__file__).read_bytes())
for name in ("child-one.py", "child-zero.py"):
    ast.parse((OUT / name).read_bytes())
print(json.dumps({"generated": str(OUT), "native_block_sha256": sha(block.encode()),
                  "postchecks_sha256": sha(post.encode()), "executed_cases": 0}))
