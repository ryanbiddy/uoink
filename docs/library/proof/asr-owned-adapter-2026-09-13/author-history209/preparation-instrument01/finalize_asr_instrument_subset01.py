"""Text-only static binding checks and preparation seal. No generated execution."""
import ast
import base64
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\asr-production-adapter-instrument-check01")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(name, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + "\n").encode()
    with (ROOT / name).open("xb") as stream:
        stream.write(raw)


bindings = json.loads((ROOT / "PREPARATION-BINDINGS.json").read_bytes())
block = (ROOT / "native-block.ps1.txt").read_bytes()
post = (ROOT / "postchecks.ps1.txt").read_bytes()
assert sha(block) == bindings["native_block_sha256"]
assert sha(post) == bindings["postchecks_sha256"]
for name in ("wrapper-missing01.ps1", "wrapper-success01.ps1"):
    raw = (ROOT / name).read_bytes()
    wrapped = raw.split(b"# BEGIN EXACT NATIVE RECEIPT BLOCK\n", 1)[1].split(b"# END EXACT NATIVE RECEIPT BLOCK\n", 1)[0]
    actual_post = raw[raw.index(b"$taskAfter=@()"):raw.rindex(b"\n}\nInvoke-InertWrapper\n")]
    assert wrapped == block and actual_post == post
    assert raw.index(b"$PSNativeCommandUseErrorActionPreference=$true") < raw.index(b"function Invoke-InertWrapper")
assert sha(base64.b64decode("SU5FUlQgV1JBUFBFUiBQT1NUQ0hFQ0sgVEVYVCBPTkxZCg==")) == bindings["synthetic_text_sha256"]
for name in ("qualify_guards.py", "child-one.py", "child-zero.py"):
    ast.parse((ROOT / name).read_bytes())
write("STATIC-VERIFICATION.json", {
    "both_native_blocks_byte_identical": True, "both_postchecks_byte_identical": True,
    "inherited_true_setup_before_function": True, "generated_text_hash_matches_expected": True,
    "python_syntax_parsed_only": ["qualify_guards.py", "child-one.py", "child-zero.py"],
    "generated_executions": 0, "asr_cases_executed": 0})
failed = (ROOT / "drafts/prepare_asr_instrument_subset01.before-string-repair.py").read_text()
fixed = (ROOT / "prepare_asr_instrument_subset01.py").read_text()
write("preparer-string-repair.patch.txt", "".join(difflib.unified_diff(failed.splitlines(True), fixed.splitlines(True),
      fromfile="before/prepare_asr_instrument_subset01.py", tofile="after/prepare_asr_instrument_subset01.py")).encode())
write("PREPARATION-TOOL-OUTCOMES.json", {
    "failed_source_preparer": {"chunk_id": "750254", "actual_exit_code": 1, "wall_time_seconds": 0.0862317,
        "error": "SyntaxError: (unicode error) 'unicodeescape' codec can't decode bytes in position 228-229: truncated \\UXXXXXXXX escape",
        "generated_code_executed": False},
    "repaired_source_preparer": {"chunk_id": "4656e1", "actual_exit_code": 0, "wall_time_seconds": 0.0942106,
        "generated_code_executed": False},
    "rejected_patch_submission": {"error": "apply_patch verification failed: invalid hunk at line 25, 'ativepowershellpwsh.exe'' is not a valid hunk header",
        "effect": "Submission rejected before file changes; resubmitted using a JavaScript raw string",
        "qualification_failure": False},
    "prior_repair_static_verifier": {"chunk_id": "9ddf43", "actual_exit_code": 0, "wall_time_seconds": 0.1296311,
        "payloads_verified": 53, "original_payloads_verified": 23, "qualification_cases_executed": 0}})
startup = [
    r"Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC|OPENAI|GEMINI|GOOGLE_API|GROK|XAI)_' } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }",
    r"$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'",
    "$env:TORCH_DEVICE_BACKEND_AUTOLOAD='0'"]
commands = []
for name, expected in (("wrapper-missing01.ps1", 1), ("wrapper-success01.ps1", 0)):
    commands.append({"script": name, "sha256": sha((ROOT / name).read_bytes()),
                     "powershell_setup_before_invocation": startup,
                     "invocation": "& '" + str(ROOT / name) + "'", "expected_actual_tool_exit": expected})
commands.append({"script": "qualify_guards.py", "sha256": sha((ROOT / "qualify_guards.py").read_bytes()),
                 "powershell_setup_before_invocation": startup,
                 "invocation": "& 'C:\\Python314\\python.exe' -I -S -B '" + str(ROOT / "qualify_guards.py") + "'",
                 "expected_actual_tool_exit": 0, "expected_case_ids": ["complete", "replaced", "removed", "missing_registry_entry"]})
write("COMMAND-BINDINGS.json", {"cwd": r"E:\AI\projects\uoink\checkouts\Yoink-library",
      "observed_powershell": r"C:\Users\hello\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe",
      "observed_powershell_version": "7.6.5", "commands_in_order": commands,
      "admission": "Root exact-source review and separate execution decision required",
      "other_matrix_scenarios": "Planned and unmeasured", "optional_controller_executed": False})
write("finalize_asr_instrument_subset01.py", Path(__file__).read_bytes())
rows = []
for path in sorted(ROOT.rglob("*")):
    if path.is_file():
        raw = path.read_bytes()
        rows.append({"path": path.relative_to(ROOT).as_posix(), "bytes": len(raw), "sha256": sha(raw)})
assert not any(row["path"] == "SHA256.json" for row in rows)
write("SHA256.json", {"schema": "uoink.asr-instrument-subset-preparation.v1", "date": "2026-09-13",
      "payload_count": len(rows), "payload_bytes": sum(row["bytes"] for row in rows),
      "qualification_executed": False, "planned_wrapper_outcomes": 2, "planned_guard_checks": 4,
      "asr_cases_executed": 0, "files": rows})
print(json.dumps({"payload_count": len(rows), "payload_bytes": sum(row["bytes"] for row in rows),
                  "manifest_sha256": sha((ROOT / "SHA256.json").read_bytes()), "qualification_executed": False}))
