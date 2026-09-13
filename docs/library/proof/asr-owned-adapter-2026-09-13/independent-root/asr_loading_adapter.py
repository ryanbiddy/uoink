"""Unintegrated ASR adapter proposal. Real authority and services stay absent.

The imported resolver is the separately qualified source, not a copy here.
No runtime/package/model module is imported by this adapter.
"""
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
from pathlib import Path
import re

import trusted_asr_resolver as resolver


class AdapterUnavailable(RuntimeError):
    pass


class AssetConsentRequired(PermissionError):
    pass


class NativeCleanupUnconfirmed(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseAuthority:
    manifest_bytes: bytes
    manifest_approval: resolver.ManifestApproval
    data_root: str
    runtime_profile_id: str


@dataclass(frozen=True)
class RuntimeProfile:
    profile_id: str
    device: str
    compute_type: str
    whisperx_fixed_vad_contract: str | None
    capture_vad_contract: str | None


@dataclass(frozen=True)
class AcquisitionPlan:
    choice: str
    repository: str
    revision: str
    manifest_sha256: str
    destination: str
    assets: tuple
    logical_bytes: int


# Only reviewed application bootstrap may provide these, after external release
# and runtime decisions. No public function accepts replacement authorities.
# Setting one alone does not bypass the resolver's still-absent REAL_APPROVAL.
RELEASE_AUTHORITY = None
RUNTIME_PROFILE = None
SNAPSHOT_LIFECYCLE = None
RUNTIME_FACTORY = None
ACQUISITION_SERVICE = None

SUPPORTED_CHOICES = tuple(resolver.MODEL_SPECS)
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


def _require(condition, message):
    if not condition:
        raise AdapterUnavailable(message)


def policy_status():
    """Cheap configuration status only; never inspect a cache or import models."""
    return {
        "choices": SUPPORTED_CHOICES,
        "release_authority_configured": RELEASE_AUTHORITY is not None,
        "resolver_real_approval_configured": resolver.REAL_APPROVAL is not None,
        "runtime_profile_configured": RUNTIME_PROFILE is not None,
        "snapshot_lifecycle_configured": SNAPSHOT_LIFECYCLE is not None,
        "runtime_factory_configured": RUNTIME_FACTORY is not None,
        "acquisition_service_configured": ACQUISITION_SERVICE is not None,
        "asset_readiness_checked": False,
        "runtime_probe_performed": False,
    }


def _release(choice, caller_root, *, root_kind):
    _require(type(choice) is str and choice in SUPPORTED_CHOICES, "Exact supported model choice required")
    authority = RELEASE_AUTHORITY
    _require(type(authority) is ReleaseAuthority, "Accepted release manifest authority is unavailable")
    _require(resolver.REAL_APPROVAL is not None
             and authority.manifest_approval is resolver.REAL_APPROVAL
             and authority.manifest_approval.purpose == "real", "Real manifest approval is unavailable")
    _require(type(authority.data_root) is str and Path(authority.data_root).is_absolute()
             and ".." not in Path(authority.data_root).parts, "Bound data root refused")
    bound_root = Path(authority.data_root)
    _require(len(bound_root.drive) == 2 and bound_root.drive[0].isalpha()
             and bound_root.drive[1] == ":" and str(bound_root) == authority.data_root,
             "Canonical local Windows data root required before any service call")
    _require(type(authority.runtime_profile_id) is str and TOKEN.fullmatch(authority.runtime_profile_id), "Bound runtime profile identity refused")
    _require(type(caller_root) is str or isinstance(caller_root, Path), "Explicit caller root required")
    expected = bound_root
    if root_kind == "reliability":
        expected = expected / "models" / "whisper"
    else:
        _require(root_kind == "transcription", "Caller root kind refused")
    _require(Path(caller_root) == expected, "Caller root differs from the externally bound profile")
    trusted = resolver.load_manifest(authority.manifest_bytes, authority.manifest_approval)
    selected = next(model for model in trusted.models if model.choice == choice)
    store = Path(authority.data_root) / "model_assets" / "asr"
    snapshot = store / choice / selected.revision
    return authority, trusted, selected, store, snapshot


def _plan(authority, selected, snapshot):
    return AcquisitionPlan(selected.choice, selected.repo, selected.revision,
                           authority.manifest_approval.manifest_sha256,
                           str(snapshot), selected.assets,
                           sum(asset.size for asset in selected.assets))


@contextmanager
def _leased_admission(choice, caller_root, *, root_kind, consent_given):
    _require(type(consent_given) is bool, "Explicit Boolean download consent required")
    authority, trusted, selected, store, snapshot = _release(choice, caller_root, root_kind=root_kind)
    lifecycle = SNAPSHOT_LIFECYCLE
    _require(lifecycle is not None, "Private immutable snapshot lifecycle is unavailable")
    stack = ExitStack()
    try:
        lease = stack.enter_context(lifecycle.read_lease(str(store), choice, selected.revision))
        try:
            admission = resolver.admit_snapshot(trusted, choice, store, snapshot)
        except resolver.AdmissionRefusal as failure:
            # Only the initial asset check may lead to acquisition. Constructor,
            # inference and cleanup failures happen after this handler.
            stack.close()
            if not consent_given:
                raise AssetConsentRequired("Trusted local assets unavailable; explicit download consent is required") from failure
            service = ACQUISITION_SERVICE
            _require(service is not None, "Approved asset acquisition service is unavailable")
            # The service owns quarantine, writer locking, bounded immutable
            # transfer, verification and atomic publication. Ignore its result:
            # a returned path or receipt cannot replace our own fresh admission.
            service.acquire_and_publish(_plan(authority, selected, snapshot), consent_given=True)
            lease = stack.enter_context(lifecycle.read_lease(str(store), choice, selected.revision))
            admission = resolver.admit_snapshot(trusted, choice, store, snapshot)
        yield authority, lease, admission
    finally:
        stack.close()


def ensure_assets(choice, *, model_root, consent_given=False):
    """Explicit reliability acquisition/verification; never construct a model."""
    with _leased_admission(choice, model_root, root_kind="reliability", consent_given=consent_given) as (authority, lease, admission):
        return {
            "ok": True, "model": choice, "model_root": str(model_root),
            "snapshot": admission.snapshot,
            "manifest_sha256": authority.manifest_approval.manifest_sha256,
            "verified": True, "model_constructed": False, "ready_marker": None,
        }


def _runtime_profile(authority, usage):
    profile = RUNTIME_PROFILE
    _require(type(profile) is RuntimeProfile and profile.profile_id == authority.runtime_profile_id,
             "Approved runtime profile is unavailable or does not match the release")
    # The first owner protocol is CPU-only. A future GPU profile needs its own
    # reviewed values/qualification; neither user settings nor probing picks it.
    _require(profile.device == "cpu" and profile.compute_type in ("int8", "float32"), "Qualified CPU compute policy required")
    if usage == "whisperx":
        _require(type(profile.whisperx_fixed_vad_contract) is str
                 and TOKEN.fullmatch(profile.whisperx_fixed_vad_contract), "Approved fixed VAD contract is unavailable")
    elif usage == "capture_fallback":
        _require(type(profile.capture_vad_contract) is str
                 and TOKEN.fullmatch(profile.capture_vad_contract), "Capture fallback VAD is not qualified")
    else:
        _require(usage == "reliability", "Runtime usage refused")
    _require(RUNTIME_FACTORY is not None, "Qualified runtime factory is unavailable")
    return profile


@contextmanager
def _model_session(choice, caller_root, *, usage, root_kind, consent_given):
    with _leased_admission(choice, caller_root, root_kind=root_kind, consent_given=consent_given) as (authority, lease, admission):
        profile = _runtime_profile(authority, usage)
        # Contract: an unconfirmed native session leaves this lease quarantined
        # when its context exits. Closing the with block must not release it.
        lease.begin_native_session()
        runtime = None
        try:
            runtime = RUNTIME_FACTORY.open_owned_session(profile)
            if usage == "whisperx":
                vad = runtime.make_fixed_vad(profile.whisperx_fixed_vad_contract)
                _require(vad is not None, "Fixed VAD injection is required")
                binding = resolver.bind_for_constructor(admission)
                model = runtime.whisperx_load_model(binding.model_path, device=profile.device,
                    compute_type=profile.compute_type, vad_model=vad, local_files_only=True)
            else:
                if usage == "capture_fallback":
                    runtime.verify_capture_vad_contract(profile.capture_vad_contract)
                binding = resolver.bind_for_constructor(admission)
                model = runtime.faster_whisper_model(binding.model_path, device=profile.device,
                    compute_type=profile.compute_type, local_files_only=True)
            _require(model is not None, "Runtime returned no model")
            # Caller must consume lazy segments inside this context, and must
            # not retain a model/generator beyond it. Proposed splices do so.
            yield model
        finally:
            if runtime is None or runtime.close_and_join() is not True:
                raise NativeCleanupUnconfirmed("Native cleanup unconfirmed; snapshot lease must remain quarantined")
            lease.confirm_native_closed()


def whisperx_session(choice, *, data_root, consent_given=False):
    return _model_session(choice, data_root, usage="whisperx", root_kind="transcription", consent_given=consent_given)


def faster_whisper_session(choice, *, model_root, usage="reliability"):
    # Ordinary reliability/caption execution can never opt into acquisition.
    return _model_session(choice, model_root, usage=usage, root_kind="reliability", consent_given=False)
