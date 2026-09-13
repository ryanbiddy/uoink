"""Data-only preparation: copy/hash/AST-inspect text, never import a candidate."""
from pathlib import Path
import ast
import difflib
import hashlib
import json

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
HERE = BASE / "_scratch/asr-permit-facade-qualification01"
OLD = BASE / "_scratch/asr-adapter-combined-proof01/author-history209/asr-author03/adapter-preflight03"
PROPOSAL = BASE / "_scratch/asr-permit-facade-proposal01"

def put(name, value):
    data = value.encode("utf-8") if isinstance(value, str) else value
    target = HERE / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

sources = {
    "asr_loading_adapter.py": PROPOSAL / "asr_loading_adapter.py",
    "connection_cases.py": PROPOSAL / "connection_cases.py",
    "snapshot_lifecycle.py": BASE / "_scratch/asr-worker-namespace-proposal01/snapshot_lifecycle.py",
    "trusted_asr_resolver.py": BASE / "_scratch/asr-trusted-manifest-resolver-proof02/proposal/trusted_asr_resolver.py",
}
required = {
    "asr_loading_adapter.py": "2b6cbbad24264423e520bac54b7c2fb4c40ae771e5c15b08381dac1d2228a63c",
    "connection_cases.py": "0ef40eab642099f83ce35d2e70a0d0521d57ad2f7e8d467e940cb2600365630a",
    "snapshot_lifecycle.py": "a80514aac6b1e75b9b872052852fa993a23cd5273b6bed4ffb4eef7404cb69dd",
    "trusted_asr_resolver.py": "16a5a1245f649a3eb04d077b661835503f08bef0ff8822dcb545176f0cc30833",
}
for name, path in sources.items():
    raw = path.read_bytes()
    assert sha(raw) == required[name]
    ast.parse(raw)
    put(name, raw)
old_guard_raw = (OLD / "qualify_adapter.py").read_bytes()
old_runner_raw = (OLD / "run_preflight03.ps1").read_bytes()
assert sha(old_guard_raw) == "68eaeeaaa3d32d6c97102aae17e4f7490702a495b9e2cb72adf38aab438ff545"
put("historical/qualify_adapter.py", old_guard_raw)
put("historical/run_preflight03.ps1", old_runner_raw)
old_guard = old_guard_raw.decode("utf-8").replace("\r\n", "\n")
old_runner = old_runner_raw.decode("utf-8").replace("\r\n", "\n")
case_tree = ast.parse((HERE / "connection_cases.py").read_bytes())
expected = next(ast.literal_eval(node.value) for node in case_tree.body
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "EXPECTED_CASES" for t in node.targets))
assert len(expected) == 6 and len(set(expected)) == 6
put("EXPECTED-CASES.json", json.dumps(list(expected), indent=2) + "\n")

guard = old_guard[:old_guard.index("real_resolver = reviewed_module")]
guard = guard.replace('import encodings.utf_8_sig\n', 'import encodings.utf_8_sig\nimport enum\nimport math\nimport threading\n')
guard = guard.replace('INPUTS = ("asr_loading_adapter.py", "trusted_asr_resolver.py", "qualify_adapter.py")',
    'INPUTS = ("asr_loading_adapter.py", "trusted_asr_resolver.py", "snapshot_lifecycle.py", "connection_cases.py", "qualify_adapter.py")')
guard = guard.replace('EXPECTED_ADAPTER = "03294344c0806b98b6d861c17371c1038c76dc0b874b9f756bf034187e849900"',
    'EXPECTED_ADAPTER = "' + required['asr_loading_adapter.py'] + '"')
guard = guard.replace('FORBIDDEN = ', 'EXPECTED_SOURCE = ' + repr(required) + '\nEXPECTED_CASES = ' + repr(expected) + '\nCONTENT_OPEN = True\nFORBIDDEN = ')
guard = guard.replace('assert sys.flags.isolated',
    'OFFLINE = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1", "PYANNOTE_METRICS_ENABLED": "0"}\nassert all(os.environ.get(name) == value for name, value in OFFLINE.items())\nassert sys.flags.isolated')
guard = guard.replace('{"trusted_asr_resolver", "asr_loading_adapter"}', '{"trusted_asr_resolver", "asr_loading_adapter", "snapshot_lifecycle", "connection_cases"}')
guard = guard.replace('allowed = isinstance(path, (str, bytes, os.PathLike))', 'allowed = CONTENT_OPEN and isinstance(path, (str, bytes, os.PathLike))')
guard = guard.replace('RAW = {name: (HERE / name).read_bytes() for name in INPUTS}', 'RAW = {name: (HERE / name).read_bytes() for name in INPUTS}\nCONTENT_OPEN = False')
guard = guard.replace('assert HASHES["trusted_asr_resolver.py"] == EXPECTED_RESOLVER',
    'assert HASHES["trusted_asr_resolver.py"] == EXPECTED_RESOLVER\nassert all(HASHES[name] == digest for name, digest in EXPECTED_SOURCE.items())')
traps = old_guard[old_guard.index('def metadata_trap'):old_guard.index('@contextlib.contextmanager')]
traps = traps.replace('# All three exact input byte strings have already been read. Deny metadata as\n# well as content reads so accidentally reaching the real resolver cannot probe.',
    '# The five reviewed source strings are loaded and content reads are closed.\n# Install metadata traps before candidate compilation and module execution.')
traps = traps.replace('(os, ("stat", "lstat", "fstat", "scandir", "listdir")))',
    '(os, ("stat", "lstat", "fstat", "scandir", "listdir")),\n                     (os.path, ("realpath",)))')
traps = traps.replace('("Path" if owner is Path else "os")', '("Path" if owner is Path else "os" if owner is os else "os.path")')
guard += traps
guard += '''real_resolver = reviewed_module("trusted_asr_resolver")
lifecycle = reviewed_module("snapshot_lifecycle")
adapter = reviewed_module("asr_loading_adapter")
connection_cases = reviewed_module("connection_cases")
assert real_resolver.REAL_APPROVAL is None
ORIGINAL_REAL_FUNCTIONS = (real_resolver.load_manifest, real_resolver.admit_snapshot, real_resolver.bind_for_constructor)
ORIGINAL_RELEASE = adapter._release
GLOBAL_NAMES = ("RELEASE_AUTHORITY", "RUNTIME_PROFILE", "SNAPSHOT_LIFECYCLE", "RUNTIME_FACTORY", "ACQUISITION_SERVICE")
assert all(getattr(adapter, name) is None for name in GLOBAL_NAMES)
assert connection_cases.EXPECTED_CASES == EXPECTED_CASES
CASES = connection_cases.define_cases(adapter, lifecycle, real_resolver)
assert tuple(name for name, _ in CASES) == EXPECTED_CASES

'''
tail = old_guard[old_guard.index('assert len(CASES) == 58'):]
tail = tail.replace('len(CASES) == 58', 'len(CASES) == 6')
tail = tail.replace('assert all(getattr(adapter, field) is None for field in GLOBAL_NAMES)',
    'assert all(getattr(adapter, field) is None for field in GLOBAL_NAMES)\n        assert adapter._release is ORIGINAL_RELEASE')
tail = tail.replace('== 11 and not metadata_trap_mismatches', '== 12 and not metadata_trap_mismatches')
tail = tail.replace('guard_valid = ', 'release_restored = adapter._release is ORIGINAL_RELEASE\ncontent_reads_closed = CONTENT_OPEN is False\nordered_membership = tuple(row["name"] for row in results) == EXPECTED_CASES\nguard_valid = content_reads_closed and release_restored and ordered_membership and ')
tail = tail.replace('"passed": passed, "failed": failed,', '"passed": passed, "failed": failed, "skipped": 0,')
tail = tail.replace('"metadata_trap_mismatches": metadata_trap_mismatches,',
    '"metadata_trap_mismatches": metadata_trap_mismatches,\n          "content_reads_closed": content_reads_closed, "adapter_release_restored": release_restored,\n          "ordered_membership_matches": ordered_membership, "offline_flags": OFFLINE,')
tail = tail.replace('Only pinned stdlib proposal modules and dummy ports; no asset fixtures or runtime factory',
    'Six connected cases with actual pure-Python lifecycle and dummy kernel; no assets or native worker')
guard += tail
ast.parse(guard)
put('qualify_adapter.py', guard)
put('guard-from-qualified58.diff', ''.join(difflib.unified_diff(old_guard.splitlines(True),guard.splitlines(True),fromfile='historical/qualify_adapter.py',tofile='qualify_adapter.py')))

new_expected = dict(required, **{'qualify_adapter.py': sha(guard.encode())})
runner = old_runner.replace("_scratch\\asr-native-exit-scope-repair01\\candidate", "_scratch\\asr-permit-facade-qualification01").replace('adapter-preflight03', 'connected01')
runner = runner.replace('$taskExpected=@{', '$taskExpected=@{', 1)
start = runner.index('$taskExpected=@{')
end = runner.index('$taskRecords=@()')
block = '$taskExpected=@{\n' + ''.join("    '"+name+"'='"+digest+"'\n" for name,digest in new_expected.items()) + '}\n'
block += '$taskExpectedCases=@(\n' + ',\n'.join("    '"+name+"'" for name in expected) + '\n)\n'
files = list(new_expected) + ['BRIEF.md','PROTOCOL.md','EXPECTED-CASES.json','SOURCE-BINDINGS.json','run_connected01.ps1','ROOT-ADMISSION.md']
block += '$taskFiles=@(\n' + ',\n'.join("    @('"+name+"',(Join-Path $taskProposal '"+name+"'))" for name in files) + '\n)\n'
runner = runner[:start] + block + runner[end:]
runner = runner.replace("$env:TORCH_DEVICE_BACKEND_AUTOLOAD='0'", "$env:TORCH_DEVICE_BACKEND_AUTOLOAD='0'\n$env:HF_HUB_OFFLINE='1'\n$env:TRANSFORMERS_OFFLINE='1'\n$env:HF_DATASETS_OFFLINE='1'\n$env:PYANNOTE_METRICS_ENABLED='0'")
runner = runner.replace('planned_case_count=58', 'planned_case_count=6;expected_case_ids=$taskExpectedCases')
runner = runner.replace(' -eq 58', ' -eq 6').replace('metadata_trap_count -eq 11', 'metadata_trap_count -eq 12')
runner = runner.replace('    $taskResult=Get-Content', "    if((Get-Item -LiteralPath $taskStdout).Length -gt 65536){throw 'Bounded result text exceeded'}\n    $taskResult=Get-Content")
runner = runner.replace('    $taskCountExit=1', '''    $taskMembership=(@($taskResult.cases.name).Count -eq $taskExpectedCases.Count)
    if($taskMembership){for($taskI=0;$taskI -lt $taskExpectedCases.Count;$taskI++){if($taskResult.cases[$taskI].name -cne $taskExpectedCases[$taskI]){$taskMembership=$false}}}
    $taskCountExit=1''')
runner = runner.replace("        $taskResult.schema -ceq", "        $taskMembership -and $taskResult.skipped -eq 0 -and\n        $taskResult.content_reads_closed -ceq $true -and $taskResult.adapter_release_restored -ceq $true -and\n        $taskResult.ordered_membership_matches -ceq $true -and\n        $taskResult.offline_flags.HF_HUB_OFFLINE -ceq '1' -and $taskResult.offline_flags.TRANSFORMERS_OFFLINE -ceq '1' -and\n        $taskResult.offline_flags.HF_DATASETS_OFFLINE -ceq '1' -and $taskResult.offline_flags.PYANNOTE_METRICS_ENABLED -ceq '0' -and\n        $taskResult.schema -ceq")
native_start = '# BEGIN EXACT NATIVE RECEIPT BLOCK'
native_end = '# END EXACT NATIVE RECEIPT BLOCK'
assert old_runner.split(native_start)[1].split(native_end)[0] == runner.split(native_start)[1].split(native_end)[0]
put('run_connected01.ps1', runner)
put('runner-from-qualified58.diff', ''.join(difflib.unified_diff(old_runner.splitlines(True),runner.splitlines(True),fromfile='historical/run_preflight03.ps1',tofile='run_connected01.ps1')))
bindings = {'schema':'uoink.asr-permit-facade-preparation.v1','executions':0,
    'sources':[{'name':name,'source':str(path),'sha256':required[name],'bytes':(HERE/name).stat().st_size} for name,path in sources.items()],
    'instrument_sha256':sha(guard.encode()),'launcher_sha256':sha(runner.encode()),
    'historical_guard_sha256':sha(old_guard_raw),'historical_runner_sha256':sha(old_runner_raw),
    'expected_case_ids':list(expected),'historical_58_claimed_for_new_interface':False,
    'native_exit_marked_block_unchanged':True}
put('SOURCE-BINDINGS.json', json.dumps(bindings,indent=2)+'\n')
print(json.dumps(bindings,indent=2))
