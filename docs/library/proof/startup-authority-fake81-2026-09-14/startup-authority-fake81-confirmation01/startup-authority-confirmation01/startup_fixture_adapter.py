"""Unintegrated owned-facade ASR adapter. Real authority/services stay absent.

The imported resolver is the separately qualified source, not a copy here.
Only the pure-Python lifecycle is added; no native/model package is imported.
"""
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
from pathlib import Path
import re

import trusted_asr_resolver as resolver
from snapshot_lifecycle import OwnedSession, OperationFacade
from durable_lifecycle import DurableOwnedRuntimeFactory


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
class _OwnedASRStart:
    # This controller-local record carries the selected admission and policy
    # into fixed worker startup. It grants no real model or serialized permit.
    policy: RuntimeProfile
    usage: str
    binding: resolver.LocalBinding


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
    # Forward the primary exception to the concrete lease on exit;
    # ExitStack.close() would discard that exception context.
    with ExitStack() as stack:
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
        factory = RUNTIME_FACTORY
        _require(type(factory) is DurableOwnedRuntimeFactory and factory.manager is SNAPSHOT_LIFECYCLE,
                 "Concrete runtime factory must own the active snapshot lifecycle")
        # The exact returned permit binds this factory to this lease's local
        # record. A generation string or a second lease cannot substitute.
        permit = lease.begin_native_session()
        runtime = None
        primary_error = None
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
        except BaseException as error:
            primary_error = error
            raise
        finally:
            try:
                if runtime is None or runtime.close_and_join() is not True:
                    raise NativeCleanupUnconfirmed("Native cleanup unconfirmed; snapshot lease must remain quarantined")
                lease.confirm_native_closed()
            except BaseException as cleanup_error:
                if primary_error is None:
                    raise
                BaseException.add_note(primary_error, "Owned ASR cleanup remains unconfirmed: " + type(cleanup_error).__name__)
                # Preserve the first error. The outer exception-aware lease
                # exit retains/quarantines the still-unconfirmed reservation.


def whisperx_session(choice, *, data_root, consent_given=False):
    return _model_session(choice, data_root, usage="whisperx", root_kind="transcription", consent_given=consent_given)


def faster_whisper_session(choice, *, model_root, usage="reliability"):
    # Ordinary reliability/caption execution can never opt into acquisition.
    return _model_session(choice, model_root, usage=usage, root_kind="reliability", consent_given=False)


# Private controller-only admission custody. No child or constructor authority.
from snapshot_lifecycle import _NativePermit, Phase
from durable_lifecycle import DurableSnapshotLifecycle, _DurableLease
from snapshot_reservations import Reservation


_STARTUP_RESOLVER = resolver
_STARTUP_LOAD = resolver.load_manifest
_STARTUP_ADMIT = resolver.admit_snapshot
_STARTUP_BIND = resolver.bind_for_constructor
_STARTUP_RELEASE = _release
_STARTUP_PROFILE = _runtime_profile
_CONTROLLER_STARTUPS = {}
_CONTROLLER_STARTUP_ATTEMPTS = {}


@dataclass(frozen=True, eq=False)
class _ControllerASRStart:
    release: ReleaseAuthority
    approval: resolver.ManifestApproval
    manifest: resolver.TrustedManifest
    admission: resolver.Admission
    selected: resolver.Model
    policy: RuntimeProfile
    usage: str
    binding: resolver.LocalBinding
    permit: _NativePermit


class _StartupCustody:
    def __init__(self, release, manifest, selected, profile, usage, manager, factory):
        self.release, self.manifest, self.selected = release, manifest, selected
        self.profile, self.usage, self.manager, self.factory = profile, usage, manager, factory
        self.lease = self.admission = self.binding = self.permit = self.startup = None
        self.record = self.protection = self.token = self.key = None
        self.active = True
        self.consumed_by = None
        self.primary_error = None
        self.references = self.values = None
        self.initial_references, self.initial_values = _startup_authority_snapshot(self)


def _startup_configuration():
    # Verify the configured trust root before using even the pure resolver.
    _require(resolver is _STARTUP_RESOLVER
             and resolver.load_manifest is _STARTUP_LOAD
             and resolver.admit_snapshot is _STARTUP_ADMIT
             and resolver.bind_for_constructor is _STARTUP_BIND,
             "Fixed startup resolver required")
    authority = RELEASE_AUTHORITY
    _require(type(authority) is ReleaseAuthority
             and type(resolver.REAL_APPROVAL) is resolver.ManifestApproval
             and authority.manifest_approval is resolver.REAL_APPROVAL
             and resolver.REAL_APPROVAL.purpose == "real",
             "Accepted real startup approval is unavailable")
    return authority


def _startup_authority_snapshot(custody):
    a, m, p = custody.release, custody.manifest, custody.profile
    refs = (a, a.manifest_approval, a.manifest_bytes, m, m.models, *m.models,
            *(asset for model in m.models for asset in model.assets), p)
    values = (a.manifest_bytes, a.data_root, a.runtime_profile_id,
        a.manifest_approval.purpose, a.manifest_approval.manifest_sha256, m.raw,
        tuple((model.choice, model.repo, model.revision,
            tuple((asset.name, asset.size, asset.sha256) for asset in model.assets))
            for model in m.models), p.profile_id, p.device, p.compute_type,
        p.whisperx_fixed_vad_contract, p.capture_vad_contract, custody.usage)
    return refs, values


def _startup_selection_current(custody):
    _require(_startup_configuration() is custody.release
             and RUNTIME_PROFILE is custody.profile
             and SNAPSHOT_LIFECYCLE is custody.manager and RUNTIME_FACTORY is custody.factory
             and custody.factory.manager is custody.manager,
             "Configured startup authority changed")
    refs, values = _startup_authority_snapshot(custody)
    _require(len(refs) == len(custody.initial_references)
             and all(a is b for a, b in zip(refs, custody.initial_references))
             and values == custody.initial_values,
             "Configured startup values changed")
    _require(_STARTUP_PROFILE(custody.release, custody.usage) is custody.profile,
             "Current startup policy required")


def _startup_values(custody):
    # Bounded immutable scalar snapshots detect mutation of retained records;
    # matching these values alone never registers another startup object.
    a, m, d, p, b = (custody.release, custody.manifest, custody.admission,
                     custody.profile, custody.binding)
    manifest_values = tuple((model.choice, model.repo, model.revision,
        tuple((asset.name, asset.size, asset.sha256) for asset in model.assets))
        for model in m.models)
    return (a.manifest_bytes, a.data_root, a.runtime_profile_id,
        a.manifest_approval.purpose, a.manifest_approval.manifest_sha256,
        m.raw, manifest_values, d.manifest.raw,
        tuple((model.choice, model.repo, model.revision,
            tuple((asset.name, asset.size, asset.sha256) for asset in model.assets))
            for model in d.manifest.models),
        d.choice, d.private_root, d.snapshot, d.directory_identity,
        tuple((f.name, f.size, f.sha256, f.identity, f.handle_identity) for f in d.files),
        p.profile_id, p.device, p.compute_type, p.whisperx_fixed_vad_contract,
        p.capture_vad_contract, custody.usage,
        b.model_path, b.choice, b.revision, b.manifest_sha256,
        tuple((f.name, f.size, f.sha256, f.identity, f.handle_identity) for f in b.files),
        b.local_files_only, b.constructor_called, b.real_runtime_approved,
        custody.key.store_root, custody.key.choice, custody.key.revision,
        custody.token.generation, custody.token.physical.volume, custody.token.physical.file_id,
        custody.token.semantic.store_volume, custody.token.semantic.store_file_id,
        custody.token.semantic.choice, custody.token.semantic.revision, custody.token.semantic.manifest)


def _startup_references(custody):
    a, m, d = custody.release, custody.manifest, custody.admission
    return (a, a.manifest_approval, a.manifest_bytes, m, m.models,
        *m.models, *(asset for model in m.models for asset in model.assets),
        custody.selected, d, d.manifest, d.manifest.models, *d.manifest.models,
        *(asset for model in d.manifest.models for asset in model.assets),
        d.files, *d.files, custody.profile, custody.binding,
        custody.binding.files, *custody.binding.files,
        custody.permit, custody.permit.identity, custody.permit.manager, custody.permit.record,
        custody.record, custody.key, custody.protection, custody.token,
        custody.token.physical, custody.token.semantic, custody.token.gate,
        custody.token.service, custody.lease.binding)


def _validate_startup_locked(custody, startup, permit, session):
    manager, record, token = custody.manager, custody.record, custody.token
    _require(custody.active and custody.startup is startup
             and _CONTROLLER_STARTUPS.get(id(startup)) is custody,
             "Exact live issued controller startup required")
    _startup_selection_current(custody)
    current = _startup_references(custody)
    _require(len(current) == len(custody.references)
             and all(a is b for a, b in zip(current, custody.references))
             and _startup_values(custody) == custody.values,
             "Retained startup selection changed")
    _require(custody.admission.manifest == custody.manifest
             and custody.admission.manifest.approval is custody.release.manifest_approval
             and custody.selected is next(model for model in custody.admission.manifest.models
                 if model.choice == custody.admission.choice)
             and custody.selected == next(model for model in custody.manifest.models
                 if model.choice == custody.admission.choice),
             "Admission model differs from approved selection")
    _require((startup.release is custody.release and startup.approval is custody.release.manifest_approval
              and startup.manifest is custody.manifest and startup.admission is custody.admission
              and startup.selected is custody.selected and startup.policy is custody.profile
              and startup.usage == custody.usage and startup.binding is custody.binding
              and startup.permit is custody.permit), "Startup record was replaced or changed")
    _require(type(permit) is _NativePermit and permit is custody.permit
             and permit.manager is manager and permit.record is record
             and record.key is custody.key
             and manager._records.get(record.key) is record and record.permit is permit.identity
             and record.protection is custody.protection
             and record.phase is Phase.NATIVE_RESERVED
             and not custody.lease.inner._exited and not custody.lease._finalization_started,
             "Current startup lease permit required")
    _require(type(token) is Reservation and custody.lease.token is token
             and manager._tokens.get(record.key) is token
             and token.service is manager._reservations
             and token.service._live.get(token.gate) is token
             and token.phase == "RESERVED" and token.pending is None
             and token.persistence_failure is None and token.revoked is False
             and token.worker is None and not token.resume_attempted,
             "Current unused durable startup reservation required")
    _require(record.key.store_root == custody.admission.private_root
             and record.key.choice == custody.admission.choice == custody.selected.choice
             and record.key.revision == custody.selected.revision
             and token.physical is custody.lease.binding[0]
             and token.semantic is custody.lease.binding[1]
             and token.generation == custody.lease.binding[2], "Exact reserved startup selection required")
    _require(token.semantic.choice == custody.selected.choice
             and token.semantic.revision == custody.selected.revision
             and token.semantic.manifest == custody.release.manifest_approval.manifest_sha256,
             "Durable selection differs from approved startup")
    if session is None:
        _require(record.owner is None and custody.consumed_by is None,
                 "Unconsumed pre-worker startup required")
    else:
        _require(type(session) is OwnedSession and record.owner is session
                 and session._record is record and session._manager is manager
                 and session._worker is None and not session._revoked and not session._closing
                 and session._active == 0 and not session._closed_verified
                 and (custody.consumed_by is None or custody.consumed_by is session),
                 "Exact live pre-worker session required")


def _validate_controller_startup(startup, permit, session=None):
    _require(type(startup) is _ControllerASRStart, "Issued controller startup required")
    custody = _CONTROLLER_STARTUPS.get(id(startup))
    _require(type(custody) is _StartupCustody and custody.startup is startup,
             "Copied controller startup has no issuance authority")
    with custody.manager._lock:
        with custody.token._lock:
            _validate_startup_locked(custody, startup, permit, session)
    return startup


def _consume_controller_startup(startup, permit, session):
    # Fixed future worker infrastructure may take this controller record once.
    # It is not an IPC witness, child-local lease or permission to construct.
    _require(type(session) is OwnedSession, "Exact session required to consume controller startup")
    _require(type(startup) is _ControllerASRStart, "Issued controller startup required")
    custody = _CONTROLLER_STARTUPS.get(id(startup))
    _require(type(custody) is _StartupCustody and custody.startup is startup,
             "Copied controller startup has no issuance authority")
    with custody.manager._lock:
        with custody.token._lock:
            _validate_startup_locked(custody, startup, permit, session)
            _require(custody.consumed_by is None, "Controller startup was already consumed")
            custody.consumed_by = session
    return startup


def _fixed_real_worker_start(startup, permit, session):
    _validate_controller_startup(startup, permit, session)
    raise AdapterUnavailable("Authenticated child transport, runtime state and fixed real bootstrap are unavailable")


@contextmanager
def _controller_startup_scope(choice, caller_root, *, usage, root_kind):
    """Retain accepted controller input before the still-closed worker seam.

    No acquisition, worker start or model constructor is called here. Once a
    native permit is reserved, an unfinished scope remains quarantined under
    the existing exception-aware lifecycle; it never invents no-worker cleanup.
    """
    configured = _startup_configuration()
    authority, trusted, selected, store, snapshot = _STARTUP_RELEASE(choice, caller_root, root_kind=root_kind)
    _require(authority is configured, "Startup release changed during selection")
    profile = _STARTUP_PROFILE(authority, usage)
    manager, factory = SNAPSHOT_LIFECYCLE, RUNTIME_FACTORY
    _require(type(manager) is DurableSnapshotLifecycle and type(factory) is DurableOwnedRuntimeFactory
             and factory.manager is manager, "Exact durable startup lifecycle and factory required")
    custody = _StartupCustody(authority, trusted, selected, profile, usage, manager, factory)
    # Custody starts before any lease/admission/binding operation can fail.
    _CONTROLLER_STARTUP_ATTEMPTS[id(custody)] = custody
    try:
        # Retain the lease wrapper before entry can reserve protection.
        custody.lease = manager.read_lease(str(store), choice, selected.revision)
        _require(type(custody.lease) is _DurableLease and custody.lease.manager is manager,
                 "Exact issued durable lease required")
        _startup_selection_current(custody)
        with custody.lease:
            _startup_selection_current(custody)
            custody.admission = _STARTUP_ADMIT(trusted, choice, store, snapshot)
            admitted = custody.admission
            _require(type(admitted) is resolver.Admission and type(admitted.manifest) is resolver.TrustedManifest
                     and admitted.manifest == trusted and admitted.manifest.approval is authority.manifest_approval
                     and admitted.choice == choice and admitted.snapshot == str(snapshot)
                     and admitted.private_root == str(store), "Exact successful selected admission required")
            # Admission reparses the manifest; retain its exact selected object,
            # while retaining the initial approved manifest separately.
            custody.selected = next(model for model in admitted.manifest.models if model.choice == choice)
            _require(custody.selected == selected, "Admission selected a different model")
            _startup_selection_current(custody)
            custody.permit = custody.lease.begin_native_session()
            custody.record = custody.permit.record
            custody.key = custody.record.key
            custody.protection = custody.record.protection
            custody.token = custody.lease.token
            _startup_selection_current(custody)
            custody.binding = _STARTUP_BIND(admitted)
            b = custody.binding
            _require(type(b) is resolver.LocalBinding and b.choice == choice
                     and b.revision == custody.selected.revision
                     and b.manifest_sha256 == authority.manifest_approval.manifest_sha256
                     and b.model_path == admitted.snapshot and b.files == admitted.files
                     and b.local_files_only is True and b.constructor_called is False
                     and b.real_runtime_approved is False, "Exact rechecked local startup binding required")
            startup = _ControllerASRStart(authority, authority.manifest_approval, trusted,
                admitted, custody.selected, profile, usage, b, custody.permit)
            custody.startup = startup
            custody.references, custody.values = _startup_references(custody), _startup_values(custody)
            _CONTROLLER_STARTUPS[id(startup)] = custody
            _validate_controller_startup(startup, custody.permit)
            try:
                yield startup
            finally:
                with manager._lock:
                    custody.active = False
    except BaseException as original:
        custody.primary_error = original
        raise
    finally:
        custody.active = False
        # A failed/reserved attempt remains retained. It is never converted to
        # completion by removing Python references or by a recorded digest.
        record = custody.lease.inner._record if type(custody.lease) is _DurableLease else None
        if record is not None and record.phase is Phase.RELEASED:
            _CONTROLLER_STARTUP_ATTEMPTS.pop(id(custody), None)
            if custody.startup is not None:
                _CONTROLLER_STARTUPS.pop(id(custody.startup), None)
