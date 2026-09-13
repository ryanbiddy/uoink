"""Unexecuted inert qualification: fake ports only, no asset or runtime I/O."""
import ast
import contextlib
import dataclasses
import encodings.utf_8_sig
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

HERE = Path(__file__).parent
INPUTS = ("asr_loading_adapter.py", "trusted_asr_resolver.py", "qualify_adapter.py")
EXPECTED_ADAPTER = "03294344c0806b98b6d861c17371c1038c76dc0b874b9f756bf034187e849900"
EXPECTED_RESOLVER = "16a5a1245f649a3eb04d077b661835503f08bef0ff8822dcb545176f0cc30833"
FORBIDDEN = r"C:\Users\hello\AppData\Local\Uoink\index.db"
assert os.environ.get("IG_FORBIDDEN_LIVE") == FORBIDDEN
assert os.environ.get("TORCH_DEVICE_BACKEND_AUTOLOAD") == "0"
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
READS = {os.path.normcase(str(HERE / name)) for name in INPUTS}
ALLOWED_IMPORTS = set(sys.modules) | {"trusted_asr_resolver", "asr_loading_adapter"}
HEAVY = {"torch", "torchaudio", "torchvision", "torchcodec", "whisperx", "faster_whisper", "ctranslate2", "transformers", "tokenizers", "pyannote", "onnxruntime", "numpy"}
assert not (HEAVY & {name.split(".")[0] for name in sys.modules})
DENIED = []


def audit(event, args):
    allowed = True
    if event == "open":
        path, mode, flags = args
        allowed = isinstance(path, (str, bytes, os.PathLike))
        if allowed:
            path = os.path.normcase(os.path.abspath(os.fsdecode(path)))
            allowed = path in READS and not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
    elif event == "import":
        allowed = args[0] in ALLOWED_IMPORTS and args[0].split(".")[0] not in HEAVY
    elif event.startswith(("os.", "socket.", "subprocess.", "ctypes.", "winreg.")):
        allowed = False
    if not allowed:
        DENIED.append(event)
        raise AssertionError("Inert adapter qualification boundary refused " + event)


sys.addaudithook(audit)
RAW = {name: (HERE / name).read_bytes() for name in INPUTS}
HASHES = {name: hashlib.sha256(raw).hexdigest() for name, raw in RAW.items()}
assert HASHES["asr_loading_adapter.py"] == EXPECTED_ADAPTER
assert HASHES["trusted_asr_resolver.py"] == EXPECTED_RESOLVER


def reviewed_module(name):
    module = types.ModuleType(name)
    module.__file__ = str(HERE / (name + ".py"))
    sys.modules[name] = module
    exec(compile(RAW[name + ".py"], module.__file__, "exec"), module.__dict__)
    return module


real_resolver = reviewed_module("trusted_asr_resolver")
adapter = reviewed_module("asr_loading_adapter")
assert real_resolver.REAL_APPROVAL is None
ORIGINAL_REAL_FUNCTIONS = (real_resolver.load_manifest, real_resolver.admit_snapshot, real_resolver.bind_for_constructor)
GLOBAL_NAMES = ("RELEASE_AUTHORITY", "RUNTIME_PROFILE", "SNAPSHOT_LIFECYCLE", "RUNTIME_FACTORY", "ACQUISITION_SERVICE")
assert all(getattr(adapter, name) is None for name in GLOBAL_NAMES)
ACTUAL_ROOT = str(HERE / "inert-context-never-created")
LEGACY_ROOT = str(Path(ACTUAL_ROOT) / "models" / "whisper")
CHOICES = ("tiny", "base", "small", "medium", "large", "large-v3-turbo")


def metadata_trap(*args, **kwargs):
    DENIED.append("metadata")
    raise AssertionError("No filesystem metadata operation is permitted in this harness")


# All three exact input byte strings have already been read. Deny metadata as
# well as content reads so accidentally reaching the real resolver cannot probe.
METADATA_TRAPS = []
for owner, names in ((Path, ("stat", "lstat", "resolve", "exists", "is_file", "is_dir")),
                     (os, ("stat", "lstat", "fstat", "scandir", "listdir"))):
    for name in names:
        setattr(owner, name, metadata_trap)
        METADATA_TRAPS.append((owner, name, metadata_trap, ("Path" if owner is Path else "os") + "." + name))
METADATA_TRAPS = tuple(METADATA_TRAPS)


@contextlib.contextmanager
def patched(owner, name, value):
    before = getattr(owner, name)
    setattr(owner, name, value)
    try:
        yield
    finally:
        setattr(owner, name, before)


def raises(error_type, callback, text):
    try:
        callback()
    except error_type as exc:
        assert text in str(exc), (text, str(exc))
        return exc
    raise AssertionError("Expected " + error_type.__name__ + ": " + text)


def enter_only(context):
    with context:
        pass


class FakeLease:
    def __init__(self, rig):
        self.rig, self.held, self.pending, self.quarantined = rig, False, False, False

    def __enter__(self):
        self.held = True
        self.rig.events.append("lease.acquire")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.rig.exit_exception_types.append(exc_type)
        if self.pending:
            self.quarantined = True
            self.rig.events.append("lease.quarantine")
        else:
            self.held = False
            self.rig.events.append("lease.release")
        return False

    def begin_native_session(self):
        assert self.held and not self.pending
        self.pending = True
        self.rig.events.append("native.begin")

    def confirm_native_closed(self):
        self.rig.events.append("native.confirm")
        if self.rig.fault == "confirm":
            raise RuntimeError("confirm fault")
        self.pending = False


class FakeLifecycle:
    def __init__(self, rig):
        self.rig = rig

    def read_lease(self, store, choice, revision):
        assert store == str(Path(ACTUAL_ROOT) / "model_assets" / "asr")
        assert choice in CHOICES and revision == real_resolver.MODEL_SPECS[choice][1]
        lease = FakeLease(self.rig)
        self.rig.leases.append(lease)
        return lease


class DummyResolverPort:
    """A visibly separate test port; never assigned to the real resolver module."""
    AdmissionRefusal = real_resolver.AdmissionRefusal

    def __init__(self, rig):
        self.rig = rig
        self.REAL_APPROVAL = rig.approval  # Dummy-port identity only.

    def load_manifest(self, raw, approval):
        assert real_resolver.REAL_APPROVAL is None
        assert raw == b"DUMMY MANIFEST: NOT AN ACCEPTED REAL MANIFEST" and approval is self.REAL_APPROVAL
        self.rig.events.append("manifest")
        return self.rig.trusted

    def admit_snapshot(self, trusted, choice, store, snapshot):
        assert trusted is self.rig.trusted and self.rig.leases[-1].held
        assert choice in CHOICES
        self.rig.events.append("admit")
        self.rig.admissions += 1
        if self.rig.admissions in self.rig.admission_failures:
            raise self.AdmissionRefusal("dummy admission refused")
        self.rig.snapshot = str(snapshot)
        return types.SimpleNamespace(snapshot=str(snapshot), choice=choice)

    def bind_for_constructor(self, admission):
        assert self.rig.leases[-1].held and self.rig.leases[-1].pending
        self.rig.events.append("bind")
        if self.rig.fault == "bind":
            raise self.AdmissionRefusal("dummy rebind refused")
        return types.SimpleNamespace(model_path=admission.snapshot)


class FakeAcquisition:
    def __init__(self, rig):
        self.rig = rig

    def acquire_and_publish(self, plan, *, consent_given):
        assert consent_given is True and not any(lease.held for lease in self.rig.leases)
        self.rig.events.append("acquire")
        self.rig.plans.append(plan)
        if self.rig.fault == "acquire":
            raise RuntimeError("acquire fault")
        return r"Z:\outside-ignored-return\untrusted"


class FakeModel:
    def __init__(self, rig):
        self.rig = rig

    def segments(self):
        assert self.rig.leases[-1].held and self.rig.leases[-1].pending
        self.rig.events.append("iterate")
        if self.rig.fault == "generator":
            raise RuntimeError("generator fault")
        for value in self.rig.segment_values:
            assert self.rig.leases[-1].held and self.rig.leases[-1].pending
            yield value


class FakeRuntime:
    def __init__(self, rig):
        self.rig = rig

    def make_fixed_vad(self, contract):
        assert contract == "dummy-fixed-vad"
        self.rig.events.append("vad.fixed")
        if self.rig.fault == "vad":
            return None
        return self.rig.vad

    def verify_capture_vad_contract(self, contract):
        assert contract == "dummy-capture-vad"
        self.rig.events.append("vad.capture")
        if self.rig.fault == "capture_vad":
            raise RuntimeError("capture vad fault")

    def _model(self, path, kwargs, kind):
        assert self.rig.events[-1] == "bind"
        assert path == self.rig.snapshot and kwargs["local_files_only"] is True
        assert kwargs["device"] == "cpu" and kwargs["compute_type"] in ("int8", "float32")
        assert set(kwargs) == ({"device", "compute_type", "local_files_only", "vad_model"} if kind == "whisperx" else {"device", "compute_type", "local_files_only"})
        if kind == "whisperx":
            assert kwargs["vad_model"] is self.rig.vad
        self.rig.events.append("construct." + kind)
        self.rig.constructed.append((path, dict(kwargs)))
        if self.rig.fault == "constructor":
            raise RuntimeError("constructor fault")
        return None if self.rig.fault == "model_none" else FakeModel(self.rig)

    def whisperx_load_model(self, path, **kwargs):
        return self._model(path, kwargs, "whisperx")

    def faster_whisper_model(self, path, **kwargs):
        return self._model(path, kwargs, "faster")

    def close_and_join(self):
        self.rig.events.append("native.close")
        if self.rig.fault == "close_exception":
            raise RuntimeError("close fault")
        return {"close_false": False, "close_none": None, "close_integer": 1}.get(self.rig.fault, True)


class FakeFactory:
    def __init__(self, rig):
        self.rig = rig

    def open_owned_session(self, profile):
        assert self.rig.leases[-1].held and self.rig.leases[-1].pending
        assert os.environ.get("TORCH_DEVICE_BACKEND_AUTOLOAD") == "0"
        self.rig.events.append("runtime.open")
        if self.rig.fault == "factory":
            raise RuntimeError("factory fault")
        return FakeRuntime(self.rig)


class Rig:
    def __init__(self, *, failures=(), fault=None):
        self.events, self.leases, self.plans, self.constructed, self.exit_exception_types = [], [], [], [], []
        self.admissions, self.admission_failures, self.fault = 0, set(failures), fault
        self.segment_values, self.vad, self.snapshot = ("one", "two"), object(), None
        self.approval = real_resolver.ManifestApproval("real", "d" * 64)
        models = []
        for choice, (repo, revision, names) in real_resolver.MODEL_SPECS.items():
            models.append(real_resolver.Model(choice, repo, revision,
                tuple(real_resolver.Asset(name, 128, "a" * 64) for name in names)))
        self.trusted = types.SimpleNamespace(models=tuple(models))
        self.authority = adapter.ReleaseAuthority(b"DUMMY MANIFEST: NOT AN ACCEPTED REAL MANIFEST", self.approval, ACTUAL_ROOT, "dummy-runtime-profile")
        self.profile = adapter.RuntimeProfile("dummy-runtime-profile", "cpu", "int8", "dummy-fixed-vad", "dummy-capture-vad")
        self.resolver, self.lifecycle, self.factory, self.acquisition = DummyResolverPort(self), FakeLifecycle(self), FakeFactory(self), FakeAcquisition(self)

    def __enter__(self):
        self.stack = contextlib.ExitStack()
        for name, value in (("resolver", self.resolver), ("RELEASE_AUTHORITY", self.authority),
                            ("RUNTIME_PROFILE", self.profile), ("SNAPSHOT_LIFECYCLE", self.lifecycle),
                            ("RUNTIME_FACTORY", self.factory), ("ACQUISITION_SERVICE", self.acquisition)):
            self.stack.enter_context(patched(adapter, name, value))
        return self

    def __exit__(self, *args):
        self.stack.close()
        assert real_resolver.REAL_APPROVAL is None
        assert (real_resolver.load_manifest, real_resolver.admit_snapshot, real_resolver.bind_for_constructor) == ORIGINAL_REAL_FUNCTIONS
        assert adapter.resolver is real_resolver
        assert all(getattr(adapter, name) is None for name in GLOBAL_NAMES)


CASES = []


def case(name):
    def register(fn):
        CASES.append((name, fn))
        return fn
    return register


@case("closed_status_does_not_probe_or_claim_readiness")
def closed_status():
    status = adapter.policy_status()
    assert status["choices"] == CHOICES
    assert all(value is False for key, value in status.items() if key != "choices")


@case("source_has_only_stdlib_and_qualified_resolver_imports")
def source_boundary():
    tree = ast.parse(RAW["asr_loading_adapter.py"])
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            imports.append(node.module)
    assert set(imports) == {"contextlib", "dataclasses", "pathlib", "re", "trusted_asr_resolver"}
    assert real_resolver.REAL_APPROVAL is None


for name, operation in (
    ("ensure", lambda: adapter.ensure_assets("tiny", model_root=LEGACY_ROOT, consent_given=True)),
    ("whisperx", lambda: enter_only(adapter.whisperx_session("tiny", data_root=ACTUAL_ROOT, consent_given=True))),
    ("reliability", lambda: enter_only(adapter.faster_whisper_session("tiny", model_root=LEGACY_ROOT))),
    ("capture", lambda: enter_only(adapter.faster_whisper_session("tiny", model_root=LEGACY_ROOT, usage="capture_fallback"))),
):
    @case("closed_real_gate_" + name)
    def closed_gate(operation=operation):
        raises(adapter.AdapterUnavailable, operation, "Accepted release manifest authority is unavailable")
        assert real_resolver.REAL_APPROVAL is None


@case("creating_model_context_is_inert_until_entered")
def inert_context_creation():
    adapter.whisperx_session("tiny", data_root=ACTUAL_ROOT, consent_given=True)
    adapter.faster_whisper_session("tiny", model_root=LEGACY_ROOT)
    assert real_resolver.REAL_APPROVAL is None and not DENIED


@case("forged_adapter_authority_cannot_enable_real_resolver")
def closed_forged_authority():
    authority = adapter.ReleaseAuthority(b"not a manifest", real_resolver.ManifestApproval("real", "0" * 64), ACTUAL_ROOT, "dummy-runtime-profile")
    with patched(adapter, "RELEASE_AUTHORITY", authority):
        raises(adapter.AdapterUnavailable, lambda: adapter.ensure_assets("tiny", model_root=LEGACY_ROOT, consent_given=True), "Real manifest approval is unavailable")
    assert real_resolver.REAL_APPROVAL is None


for choice in CHOICES:
    @case("six_choice_local_only_session_" + choice)
    def choices(choice=choice):
        with Rig() as rig:
            with adapter.faster_whisper_session(choice, model_root=LEGACY_ROOT) as model:
                assert list(model.segments()) == ["one", "two"]
            assert rig.events == ["manifest", "lease.acquire", "admit", "native.begin", "runtime.open", "bind", "construct.faster", "iterate", "native.close", "native.confirm", "lease.release"]
            assert len(rig.constructed) == 1 and not rig.plans
            assert rig.constructed[0][0].endswith(real_resolver.MODEL_SPECS[choice][1])


for alias in ("large-v3", "TINY", "balanced", "../tiny"):
    @case("unsupported_alias_" + alias.replace("/", "-"))
    def alias_rejected(alias=alias):
        with Rig() as rig:
            raises(adapter.AdapterUnavailable, lambda: adapter.ensure_assets(alias, model_root=LEGACY_ROOT, consent_given=True), "Exact supported model choice")
            assert rig.events == []


for name, value in (("unc", r"\\server\share\profile"), ("relative", "profile"), ("escape", r"E:\safe\..\profile"), ("noncanonical", "E:/profile")):
    @case("root_policy_" + name)
    def root_policy(value=value):
        with Rig() as rig:
            authority = dataclasses.replace(rig.authority, data_root=value)
            with patched(adapter, "RELEASE_AUTHORITY", authority):
                raises(adapter.AdapterUnavailable, lambda: adapter.ensure_assets("tiny", model_root=LEGACY_ROOT, consent_given=True), "root")
            assert rig.events == []


@case("caller_root_cannot_select_another_profile")
def other_root():
    with Rig() as rig:
        raises(adapter.AdapterUnavailable, lambda: adapter.ensure_assets("tiny", model_root=str(HERE / "other"), consent_given=True), "Caller root differs")
        assert rig.events == []


for value in (1, "true", None):
    @case("consent_requires_boolean_" + repr(value))
    def consent_type(value=value):
        with Rig() as rig:
            raises(adapter.AdapterUnavailable, lambda: adapter.ensure_assets("tiny", model_root=LEGACY_ROOT, consent_given=value), "Boolean download consent")
            assert rig.events == []


@case("missing_assets_without_consent_cannot_acquire_or_construct")
def no_consent():
    with Rig(failures=(1,)) as rig:
        raises(adapter.AssetConsentRequired, lambda: adapter.ensure_assets("tiny", model_root=LEGACY_ROOT), "explicit download consent")
        assert rig.events == ["manifest", "lease.acquire", "admit", "lease.release"]
        assert not rig.plans and not rig.constructed


@case("ordinary_reliability_remains_no_acquisition")
def ordinary_local():
    with Rig(failures=(1,)) as rig:
        raises(adapter.AssetConsentRequired, lambda: enter_only(adapter.faster_whisper_session("tiny", model_root=LEGACY_ROOT)), "explicit download consent")
        assert not rig.plans and "runtime.open" not in rig.events


@case("missing_lifecycle_prevents_asset_or_runtime_callbacks")
def no_lifecycle():
    with Rig() as rig, patched(adapter, "SNAPSHOT_LIFECYCLE", None):
        raises(adapter.AdapterUnavailable, lambda: adapter.ensure_assets("tiny", model_root=LEGACY_ROOT), "snapshot lifecycle is unavailable")
        assert rig.events == ["manifest"]


@case("missing_acquisition_capability_has_no_fallback")
def no_acquisition_service():
    with Rig(failures=(1,)) as rig, patched(adapter, "ACQUISITION_SERVICE", None):
        raises(adapter.AdapterUnavailable, lambda: adapter.ensure_assets("tiny", model_root=LEGACY_ROOT, consent_given=True), "acquisition service is unavailable")
        assert "acquire" not in rig.events and "runtime.open" not in rig.events


@case("explicit_acquisition_uses_full_plan_and_ignores_returned_path")
def explicit_acquisition():
    with Rig(failures=(1,)) as rig:
        result = adapter.ensure_assets("large", model_root=LEGACY_ROOT, consent_given=True)
        assert rig.events == ["manifest", "lease.acquire", "admit", "lease.release", "acquire", "lease.acquire", "admit", "lease.release"]
        assert len(rig.plans) == 1 and rig.admissions == 2
        plan = rig.plans[0]
        selected = next(row for row in rig.trusted.models if row.choice == "large")
        assert (plan.choice, plan.repository, plan.revision, plan.assets) == (selected.choice, selected.repo, selected.revision, selected.assets)
        assert plan.logical_bytes == 5 * 128 and plan.manifest_sha256 == "d" * 64
        assert result["snapshot"] == plan.destination and not result["snapshot"].startswith("Z:")
        assert result["verified"] is True and result["model_constructed"] is False and result["ready_marker"] is None
        assert not rig.constructed


@case("trusted_assets_with_consent_do_not_redownload")
def no_unneeded_acquisition():
    with Rig() as rig:
        result = adapter.ensure_assets("tiny", model_root=LEGACY_ROOT, consent_given=True)
        assert result["verified"] is True and rig.admissions == 1 and not rig.plans and not rig.constructed


@case("failed_second_admission_never_retries")
def no_retry():
    with Rig(failures=(1, 2)) as rig:
        raises(real_resolver.AdmissionRefusal, lambda: adapter.ensure_assets("tiny", model_root=LEGACY_ROOT, consent_given=True), "dummy admission refused")
        assert len(rig.plans) == 1 and rig.admissions == 2 and not rig.constructed


@case("acquisition_exception_never_retries_or_imports")
def acquire_fault():
    with Rig(failures=(1,), fault="acquire") as rig:
        raises(RuntimeError, lambda: adapter.ensure_assets("tiny", model_root=LEGACY_ROOT, consent_given=True), "acquire fault")
        assert len(rig.plans) == 1 and rig.admissions == 1 and "runtime.open" not in rig.events


@case("whisperx_fixed_vad_and_rebind_order")
def whisperx_order():
    with Rig() as rig:
        with adapter.whisperx_session("base", data_root=ACTUAL_ROOT) as model:
            assert list(model.segments()) == ["one", "two"]
        assert rig.events == ["manifest", "lease.acquire", "admit", "native.begin", "runtime.open", "vad.fixed", "bind", "construct.whisperx", "iterate", "native.close", "native.confirm", "lease.release"]


@case("capture_fallback_has_separate_vad_contract")
def capture_order():
    with Rig() as rig:
        with adapter.faster_whisper_session("tiny", model_root=LEGACY_ROOT, usage="capture_fallback") as model:
            list(model.segments())
        assert rig.events.index("vad.capture") < rig.events.index("bind") < rig.events.index("construct.faster")


for name, profile_changes, usage in (
    ("profile_identity", {"profile_id": "other"}, "reliability"),
    ("gpu", {"device": "cuda"}, "reliability"),
    ("compute", {"compute_type": "float16"}, "reliability"),
    ("fixed_vad", {"whisperx_fixed_vad_contract": None}, "whisperx"),
    ("capture_vad", {"capture_vad_contract": None}, "capture_fallback"),
):
    @case("profile_gate_" + name)
    def profile_gate(profile_changes=profile_changes, usage=usage):
        with Rig() as rig, patched(adapter, "RUNTIME_PROFILE", dataclasses.replace(rig.profile, **profile_changes)):
            context = adapter.whisperx_session("tiny", data_root=ACTUAL_ROOT) if usage == "whisperx" else adapter.faster_whisper_session("tiny", model_root=LEGACY_ROOT, usage=usage)
            raises(adapter.AdapterUnavailable, lambda: enter_only(context), "")
            assert "runtime.open" not in rig.events and "native.begin" not in rig.events


@case("missing_factory_never_begins_native_session")
def missing_factory():
    with Rig() as rig, patched(adapter, "RUNTIME_FACTORY", None):
        raises(adapter.AdapterUnavailable, lambda: enter_only(adapter.faster_whisper_session("tiny", model_root=LEGACY_ROOT)), "runtime factory is unavailable")
        assert "native.begin" not in rig.events


for fault, usage, error_type, fragment in (
    ("bind", "reliability", real_resolver.AdmissionRefusal, "dummy rebind refused"),
    ("constructor", "reliability", RuntimeError, "constructor fault"),
    ("generator", "reliability", RuntimeError, "generator fault"),
    ("model_none", "reliability", adapter.AdapterUnavailable, "returned no model"),
    ("vad", "whisperx", adapter.AdapterUnavailable, "VAD injection is required"),
    ("capture_vad", "capture_fallback", RuntimeError, "capture vad fault"),
):
    @case("runtime_failure_closes_without_acquisition_" + fault)
    def runtime_fault(fault=fault, usage=usage, error_type=error_type, fragment=fragment):
        with Rig(fault=fault) as rig:
            def operation():
                context = adapter.whisperx_session("tiny", data_root=ACTUAL_ROOT, consent_given=True) if usage == "whisperx" else adapter.faster_whisper_session("tiny", model_root=LEGACY_ROOT, usage=usage)
                with context as model:
                    list(model.segments())
            raises(error_type, operation, fragment)
            assert rig.events[-3:] == ["native.close", "native.confirm", "lease.release"]
            assert not rig.plans and not any(lease.held for lease in rig.leases)


for fault, error_type, fragment in (
    ("factory", adapter.NativeCleanupUnconfirmed, "cleanup unconfirmed"),
    ("close_false", adapter.NativeCleanupUnconfirmed, "cleanup unconfirmed"),
    ("close_none", adapter.NativeCleanupUnconfirmed, "cleanup unconfirmed"),
    ("close_integer", adapter.NativeCleanupUnconfirmed, "cleanup unconfirmed"),
    ("close_exception", RuntimeError, "close fault"),
    ("confirm", RuntimeError, "confirm fault"),
):
    @case("unconfirmed_cleanup_quarantines_" + fault)
    def quarantine(fault=fault, error_type=error_type, fragment=fragment):
        with Rig(fault=fault) as rig:
            exc = raises(error_type, lambda: enter_only(adapter.faster_whisper_session("tiny", model_root=LEGACY_ROOT)), fragment)
            assert rig.events[-1] == "lease.quarantine" and rig.leases[-1].held and rig.leases[-1].pending
            assert rig.exit_exception_types[-1] is None and not rig.plans
            if fault == "factory":
                assert isinstance(exc.__context__, RuntimeError) and "factory fault" in str(exc.__context__)


@case("caller_error_with_confirmed_cleanup_propagates_and_releases")
def caller_error():
    with Rig() as rig:
        def operation():
            with adapter.faster_whisper_session("tiny", model_root=LEGACY_ROOT):
                raise LookupError("caller fault")
        raises(LookupError, operation, "caller fault")
        assert rig.events[-3:] == ["native.close", "native.confirm", "lease.release"]


@case("empty_lazy_result_is_consumed_while_lease_is_held")
def empty_result():
    with Rig() as rig:
        rig.segment_values = ()
        with adapter.faster_whisper_session("tiny", model_root=LEGACY_ROOT) as model:
            assert list(model.segments()) == []
        assert "iterate" in rig.events and rig.events[-1] == "lease.release"


@case("raw_object_reference_escape_remains_an_explicit_limitation")
def raw_reference_limit():
    with Rig() as rig:
        with adapter.faster_whisper_session("tiny", model_root=LEGACY_ROOT) as model:
            retained = model
        assert retained is model and rig.leases[-1].held is False
        # No use-after-context safety claim: this is a plain retained Python
        # reference. A real operation facade/worker still has to be implemented.


@case("private_release_seam_does_not_grant_real_approval")
def private_seam():
    with Rig() as rig:
        def release(choice, root, *, root_kind):
            assert choice == "tiny" and root == LEGACY_ROOT and root_kind == "reliability"
            selected = next(row for row in rig.trusted.models if row.choice == choice)
            store = Path(ACTUAL_ROOT) / "model_assets" / "asr"
            return rig.authority, rig.trusted, selected, store, store / choice / selected.revision
        with patched(adapter, "_release", release):
            result = adapter.ensure_assets("tiny", model_root=LEGACY_ROOT)
        assert result["verified"] is True and real_resolver.REAL_APPROVAL is None
        assert "manifest" not in rig.events and not rig.constructed


assert len(CASES) == 58
assert len({name for name, _ in CASES}) == len(CASES)
results = []
started = time.monotonic()
for name, fn in CASES:
    try:
        fn()
        assert real_resolver.REAL_APPROVAL is None and adapter.resolver is real_resolver
        assert all(getattr(adapter, field) is None for field in GLOBAL_NAMES)
        results.append({"name": name, "passed": True})
    except Exception as exc:
        results.append({"name": name, "passed": False, "exception": type(exc).__name__, "message": str(exc)})
passed = sum(result["passed"] for result in results)
failed = len(results) - passed
heavy_loaded = sorted(HEAVY & {name.split(".")[0] for name in sys.modules})
real_approval_closed = real_resolver.REAL_APPROVAL is None
real_functions_unchanged = (real_resolver.load_manifest, real_resolver.admit_snapshot, real_resolver.bind_for_constructor) == ORIGINAL_REAL_FUNCTIONS
adapter_globals_restored = adapter.resolver is real_resolver and all(getattr(adapter, field) is None for field in GLOBAL_NAMES)
metadata_trap_mismatches = [label for owner, name, installed, label in METADATA_TRAPS
                            if getattr(owner, name, None) is not installed]
metadata_traps_installed = len(METADATA_TRAPS) == 11 and not metadata_trap_mismatches
guard_valid = not DENIED and not heavy_loaded and real_approval_closed and real_functions_unchanged and adapter_globals_restored and metadata_traps_installed
result = {"schema": "uoink.inert-asr-adapter-qualification.v1", "passed": passed, "failed": failed,
          "elapsed_seconds": round(time.monotonic() - started, 6), "cases": results,
          "input_sha256": HASHES, "guard_denials": DENIED, "heavy_roots_loaded": heavy_loaded,
          "real_resolver_approval_unchanged_none": real_approval_closed,
          "real_resolver_functions_unchanged": real_functions_unchanged,
          "adapter_globals_restored": adapter_globals_restored, "guard_valid": guard_valid,
          "metadata_traps_installed": metadata_traps_installed, "metadata_trap_count": len(METADATA_TRAPS),
          "metadata_trap_mismatches": metadata_trap_mismatches,
          "scope": "Only pinned stdlib proposal modules and dummy ports; no asset fixtures or runtime factory",
          "startup_binding_asserted": True, "torch_backend_autoload_disabled_before_startup": True,
          "qualification_exit": 0 if not failed and guard_valid else 1}
print(json.dumps(result, indent=2))
sys.exit(result["qualification_exit"])
