"""Preserve source/evidence, write the inert adapter derivative; never import it."""
from pathlib import Path
import ast
import difflib
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = ROOT / "asr-production-adapter-proposal01/asr_loading_adapter.py"
PROOF = ROOT / "asr-adapter-combined-proof01"
QUALIFIED = PROOF / "author-history209/asr-author03/adapter-preflight03/qualify_adapter.py"
sha = lambda raw: hashlib.sha256(raw).hexdigest()
assert sha(SOURCE.read_bytes()) == "03294344c0806b98b6d861c17371c1038c76dc0b874b9f756bf034187e849900"
seal_raw = (PROOF / "SHA256.json").read_bytes()
assert sha(seal_raw) == "0e75c738cdf7725d49730db08043ffee1d0882e6658a49e05583bef9b9bf60e5"
seal = json.loads(seal_raw)
BEFORE = HERE / "original58"
BEFORE.mkdir(exist_ok=False)
originals = {"asr_loading_adapter.py": SOURCE, "qualify_adapter.py": QUALIFIED,
             "RESULTS.json": PROOF / "RESULTS.json", "COMBINED-SHA256.json": PROOF / "SHA256.json"}
rows = []
for name, path in originals.items():
    raw = path.read_bytes()
    (BEFORE / name).write_bytes(raw)
    rows.append({"copy": "original58/" + name, "source": str(path), "bytes": len(raw), "sha256": sha(raw)})
old = SOURCE.read_text(encoding="utf-8")
new = old
needle = 'import trusted_asr_resolver as resolver\n'
assert new.count(needle) == 1
new = new.replace(needle, needle + 'from snapshot_lifecycle import OwnedRuntimeFactory, OwnedSession, OperationFacade\n')
needle = '\n\n@dataclass(frozen=True)\nclass AcquisitionPlan:'
assert new.count(needle) == 1
new = new.replace(needle, '''

@dataclass(frozen=True)
class _OwnedASRStart:
    # This controller-local record carries the selected admission and policy
    # into fixed worker startup. It grants no real model or serialized permit.
    policy: RuntimeProfile
    usage: str
    binding: resolver.LocalBinding


@dataclass(frozen=True)
class AcquisitionPlan:''')
start = new.index('@contextmanager\ndef _model_session(')
end = new.index('\n\ndef whisperx_session(', start)
replacement = '''@contextmanager
def _model_session(choice, caller_root, *, usage, root_kind, consent_given):
    with _leased_admission(choice, caller_root, root_kind=root_kind, consent_given=consent_given) as (authority, lease, admission):
        profile = _runtime_profile(authority, usage)
        factory = RUNTIME_FACTORY
        _require(type(factory) is OwnedRuntimeFactory and factory._lifecycle is SNAPSHOT_LIFECYCLE,
                 "Concrete runtime factory must own the active snapshot lifecycle")
        # The exact returned permit binds this factory to this lease's local
        # record. A generation string or a second lease cannot substitute.
        permit = lease.begin_native_session()
        runtime = None
        try:
            # Recheck before worker startup; no native/model constructor runs
            # in the controller. The fixed worker must enforce this binding,
            # selected usage and VAD policy before its own construction path.
            binding = resolver.bind_for_constructor(admission)
            _require(type(binding) is resolver.LocalBinding and binding.choice == choice
                     and binding.revision == permit.record.key.revision
                     and binding.manifest_sha256 == authority.manifest_approval.manifest_sha256
                     and binding.model_path == admission.snapshot
                     and binding.local_files_only is True and binding.constructor_called is False
                     and binding.real_runtime_approved is False, "Exact local startup binding required")
            startup = _OwnedASRStart(profile, usage, binding)
            runtime = factory.open_owned_session(startup, permit)
            _require(type(runtime) is OwnedSession and runtime._record is permit.record
                     and runtime._manager is SNAPSHOT_LIFECYCLE, "Exact owned session required")
            operations = runtime.operations()
            _require(type(operations) is OperationFacade and operations._session is runtime,
                     "Exact revocable operation facade required")
            # Callers submit owned TranscribeRequest tickets and consume only
            # passive segments inside this context. Retained facades/streams
            # refuse further work after the session is revoked.
            yield operations
        finally:
            if runtime is None or runtime.close_and_join() is not True:
                raise NativeCleanupUnconfirmed("Native cleanup unconfirmed; snapshot lease must remain quarantined")
            lease.confirm_native_closed()
'''
new = new[:start] + replacement + new[end:]
new = new.replace('"""Unintegrated ASR adapter proposal. Real authority and services stay absent.',
                  '"""Unintegrated owned-facade ASR adapter. Real authority/services stay absent.')
new = new.replace('No runtime/package/model module is imported by this adapter.',
                  'Only the pure-Python lifecycle is added; no native/model package is imported.')
ast.parse(new, filename="asr_loading_adapter.py")
(HERE / "asr_loading_adapter.py").write_bytes(new.encode())
(HERE / "adapter-permit-facade.diff").write_text("".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
    fromfile="original58/asr_loading_adapter.py", tofile="proposed/asr_loading_adapter.py")), encoding="utf-8", newline="\n")
qualified_ast = ast.parse(QUALIFIED.read_bytes())
original_ast = ast.parse((ROOT / "asr-production-adapter-proposal01/qualify_adapter.py").read_bytes())
def body_map(tree):
    return {node.name: ast.dump(node, include_attributes=False) for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name)
                    and decorator.func.id == "case" for decorator in node.decorator_list)}
assert body_map(qualified_ast) == body_map(original_ast)
assert body_map(qualified_ast)
assert len(json.loads((PROOF / "RESULTS.json").read_bytes())["case_ids"]) == 58
assert sha(QUALIFIED.read_bytes()) == sha((BEFORE / "qualify_adapter.py").read_bytes())
(HERE / "ORIGINAL58-BINDINGS.json").write_text(json.dumps({"preserved_files": rows,
    "qualified_assertion_bodies_match_original": True, "original_distinct_case_count": 58,
    "decorated_function_definitions_compared": len(body_map(qualified_ast)),
    "new_candidate_tested": False, "new_adapter_sha256": sha(new.encode())}, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"source_only": True, "new_adapter_sha256": sha(new.encode()),
                  "qualified58_harness_sha256": sha(QUALIFIED.read_bytes()), "candidate_executions": 0}, indent=2))
