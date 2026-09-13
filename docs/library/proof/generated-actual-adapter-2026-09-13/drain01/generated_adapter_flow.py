"""Unexecuted actual-adapter/generated-worker bridge. No real authority.

Only a separately reviewed generated bootstrap may invoke this module. Import
executes definitions and hashes fixed generated text; it performs no I/O.
"""
from contextlib import contextmanager, ExitStack
from types import SimpleNamespace
import hashlib
import json
import asr_loading_adapter as adapter
import trusted_asr_resolver as real_resolver
import generated_operation_flow as operation_flow
from snapshot_lifecycle import OwnedRuntimeFactory, OperationFacade, TranscribeRequest, Phase
from owned_generation_protocol import GenerationChannel, decode_private_bootstrap
from inherited_readset import InheritedReadSetAdoption, GENERATED, NAMES, namespace_digest, fixed_paths

_assert = operation_flow._assert
_remaining = operation_flow._remaining
_fixed = operation_flow._fixed
declare_exit_call = operation_flow.declare_exit_call
CHOICE = "large-v3-turbo"
REVISION = real_resolver.MODEL_SPECS[CHOICE][1]
PROFILE_ID = "generated-asr-reliability-v1"
FILES = tuple((name, len(GENERATED[name]), hashlib.sha256(GENERATED[name]).hexdigest()) for name in NAMES)
RECIPE = {"purpose": "generated-adapter-connection-only", "profile_id": PROFILE_ID,
          "choice": CHOICE, "revision": REVISION,
          "files": [{"name": name, "bytes": size, "sha256": digest} for name, size, digest in FILES]}
RECIPE_SHA256 = hashlib.sha256(json.dumps(RECIPE, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


def policy_payload(root, binding):
    # This root is the fixed private generated run, already selected by the
    # bootstrap. It is never opened or treated as a caller-supplied model path.
    return {"action": "bind_generated_adapter_start", "generated_only": True,
            "profile_id": PROFILE_ID, "usage": "reliability", "device": "cpu", "compute_type": "int8",
            "choice": CHOICE, "revision": REVISION, "generated_root": root,
            "recipe_sha256": RECIPE_SHA256, "namespace_sha256": namespace_digest(),
            "inherited_manifest_sha256": binding.manifest_sha256,
            "local_files_only": True, "constructor_called": False, "real_runtime_approved": False}


def policy_ack(payload):
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()
    return {"action": "generated_adapter_start_bound", "policy_sha256": digest, "model_calls": 0}


class GeneratedLifecyclePort(operation_flow.GeneratedLifecyclePort):
    def __init__(self, *args, operation_mode="drain", **kwargs):
        _assert(operation_mode == "drain", "one_actual_adapter_drain_scope")
        super().__init__(*args, operation_mode=operation_mode, **kwargs)
        _assert(real_resolver.REAL_APPROVAL is None, "real_model_authority_must_remain_absent")
        self.adapter_profile = adapter.RuntimeProfile(PROFILE_ID, "cpu", "int8", None, None)
        self.generated_authority = SimpleNamespace(runtime_profile_id=PROFILE_ID,
            manifest_approval=SimpleNamespace(manifest_sha256=RECIPE_SHA256))
        self.generated_trusted = object()
        self.generated_selected = SimpleNamespace(revision=REVISION)
        self.generated_admission = SimpleNamespace(snapshot=self.cwd)
        self.generated_binding = real_resolver.LocalBinding(self.cwd, CHOICE, REVISION, RECIPE_SHA256, FILES)
        self.binding_calls = 0
        self.adapter_startup = self.adapter_start_payload = self.adapter_start_ack = None
        self.authority_events = []

    def acquire_read(self, key):
        _assert((key.store_root, key.choice, key.revision) == (self.cwd, CHOICE, REVISION),
                "exact_generated_adapter_lease_key")
        return super().acquire_read(key)

    def generated_release(self, choice, caller_root, *, root_kind):
        _assert(type(choice) is str and choice == CHOICE and type(caller_root) is str
                and caller_root == self.cwd and root_kind == "reliability"
                and self.read_set is None and real_resolver.REAL_APPROVAL is None,
                "fixed_visible_generated_release_seam")
        self.authority_events.append("generated_release")
        return self.generated_authority, self.generated_trusted, self.generated_selected, self.cwd, self.cwd

    def generated_admit(self, trusted, choice, store, snapshot):
        record = self.lifecycle._records.get(self.key)
        _assert(trusted is self.generated_trusted and choice == CHOICE
                and type(store) is str and store == self.cwd and type(snapshot) is str and snapshot == self.cwd
                and record is not None and record.protection is self.read_set and record.phase is Phase.PROTECTED
                and record.permit is None and not self.read_set.unconfirmed and not self.read_set.released,
                "generated_admission_requires_actual_protection")
        self.authority_events.append("generated_admit")
        return self.generated_admission

    def generated_bind(self, admission):
        record = self.lifecycle._records.get(self.key)
        _assert(admission is self.generated_admission and record is not None
                and record.phase is Phase.NATIVE_RESERVED and record.permit is not None and record.owner is None
                and record.protection is self.read_set and len(self.read_set.members) == len(self.read_set.identities) == 5
                and all(not handle.closed for handle in self.read_set.members)
                and not self.read_set.unconfirmed and self.binding_calls == 0
                and real_resolver.REAL_APPROVAL is None, "generated_binding_requires_reserved_owned_handles")
        self.binding_calls += 1
        self.authority_events.append("generated_bind")
        return self.generated_binding

    def start_owned_worker(self, protection, permit, startup):
        record = self._record(protection, permit)
        _assert(type(startup) is adapter._OwnedASRStart and startup.policy is self.adapter_profile
                and type(startup.policy) is adapter.RuntimeProfile and startup.usage == "reliability"
                and startup.binding is self.generated_binding and type(startup.binding) is real_resolver.LocalBinding
                and startup.binding.model_path == self.cwd and startup.binding.choice == CHOICE
                and startup.binding.revision == REVISION and startup.binding.manifest_sha256 == RECIPE_SHA256
                and startup.binding.files == FILES and startup.binding.local_files_only is True
                and startup.binding.constructor_called is False and startup.binding.real_runtime_approved is False
                and record.phase is Phase.NATIVE_RESERVED and record.permit is permit and self.binding_calls == 1
                and self.adapter_startup is None and real_resolver.REAL_APPROVAL is None,
                "exact_generated_owned_asr_start_before_process")
        self.adapter_startup = startup
        self.authority_events.append("owned_start_validated")
        # The inherited sentinel is only an internal generated transport check,
        # reached after the exact adapter startup and lease validation above.
        worker = super().start_owned_worker(protection, permit, self.profile)
        try:
            self.handshake._owned_phase(True)
            payload = policy_payload(self.cwd, self.channel.binding)
            self.pipes.write_bytes(self.pair, self.channel.encode("next", payload), _remaining(self.pipes.clock))
            operation, response = self.channel.decode(self.pipes.read_frame(self.pair, _remaining(self.pipes.clock)))
            _assert(operation == "done" and _fixed(response, policy_ack(payload)), "generated_worker_start_binding_ack")
            self.handshake._owned_phase(True)
            self.adapter_start_payload, self.adapter_start_ack = payload, response
            self.authority_events.append("worker_start_bound")
            return worker
        except BaseException:
            self.pipes._quarantine(self.pair)
            raise


@contextmanager
def _replace(owner, name, value):
    before = getattr(owner, name)
    setattr(owner, name, value)
    try:
        yield
    finally:
        setattr(owner, name, before)


@contextmanager
def generated_authority_seams(port):
    """Visible fake release/admission only; actual lifecycle/factory/adapter."""
    _assert(type(port) is GeneratedLifecyclePort and real_resolver.REAL_APPROVAL is None,
            "exact_generated_bridge_required")
    names = ("RELEASE_AUTHORITY", "RUNTIME_PROFILE", "SNAPSHOT_LIFECYCLE", "RUNTIME_FACTORY", "ACQUISITION_SERVICE")
    _assert(adapter.resolver is real_resolver and all(getattr(adapter, name) is None for name in names),
            "real_adapter_services_must_be_unconfigured")
    original_release = adapter._release
    original_functions = (real_resolver.load_manifest, real_resolver.admit_snapshot, real_resolver.bind_for_constructor)
    proxy = SimpleNamespace(LocalBinding=real_resolver.LocalBinding, AdmissionRefusal=real_resolver.AdmissionRefusal,
        admit_snapshot=port.generated_admit, bind_for_constructor=port.generated_bind, REAL_APPROVAL=None)
    replacements = {"_release": port.generated_release, "resolver": proxy, "RUNTIME_PROFILE": port.adapter_profile,
                    "SNAPSHOT_LIFECYCLE": port.lifecycle, "RUNTIME_FACTORY": OwnedRuntimeFactory(port.lifecycle)}
    primary = None
    try:
        with ExitStack() as stack:
            for name, value in replacements.items():
                stack.enter_context(_replace(adapter, name, value))
            yield
    except BaseException as error:
        primary = error
        raise
    finally:
        restored = (adapter._release is original_release and adapter.resolver is real_resolver
            and all(getattr(adapter, name) is None for name in names)
            and real_resolver.REAL_APPROVAL is None
            and (real_resolver.load_manifest, real_resolver.admit_snapshot, real_resolver.bind_for_constructor) == original_functions)
        if not restored:
            if primary is not None:
                BaseException.add_note(primary, "Generated authority seam restoration failed")
            else:
                raise AssertionError("Generated authority seam restoration failed")


def controller_flow(port):
    _assert(type(port) is GeneratedLifecyclePort, "exact_actual_adapter_generated_port")
    with generated_authority_seams(port):
        # The unchanged adapter opens the actual lease, retains its permit,
        # constructs _OwnedASRStart and creates the actual owned factory/session.
        with adapter.faster_whisper_session(CHOICE, model_root=port.cwd) as facade:
            _assert(type(facade) is OperationFacade and facade._session._manager is port.lifecycle,
                    "actual_adapter_owned_facade")
            session = facade._session
            record = session._record
            _assert(record.protection is port.read_set and record.permit is port.permit
                    and record.owner is session and port.adapter_startup.policy is port.adapter_profile
                    and port.adapter_startup.binding is port.generated_binding and port.adapter_start_ack is not None,
                    "actual_start_permit_and_worker_ack")
            ticket = port.issue_generated_media_ticket(session)
            request = TranscribeRequest(ticket, language="en")
            stream = facade.transcribe(request)
            _assert(port._next_index == 0 and port.operation_events == ["admit_generated_media", "begin_generated_transcription"],
                    "actual_adapter_start_keeps_segments_lazy")
            observed = [next(stream), next(stream)]
            try:
                next(stream)
            except StopIteration:
                pass
            else:
                raise AssertionError("Actual adapter generated stream must end")
            _assert(port._cursor_state == "eof" and all(not h.closed for h in port.read_set.members),
                    "actual_adapter_consumption_holds_read_guards")
            for path, expected in port.expectations:
                port.observations.append(operation_flow.adoption_flow._write_access_probe(port.primitives, path, True))
        # Only the adapter's actual finally performed close/join and lease exit.
        _assert(record.phase is Phase.RELEASED and session._closed_verified
                and port.read_set.released and port.pair.closed, "actual_adapter_finally_released_after_join")
    before = tuple(port.operation_events)
    operation_flow._require_session_closed(lambda: facade.transcribe(request))
    operation_flow._require_session_closed(lambda: next(stream))
    _assert(tuple(port.operation_events) == before, "actual_adapter_retained_references_have_no_wire_use")
    for path, expected in port.expectations:
        port.observations.append(operation_flow.adoption_flow._write_access_probe(port.primitives, path, False))
    return {"operation_mode": "drain", "actual_adapter_context": "faster_whisper_session",
            "segments": [{"start": s.start, "end": s.end, "text": s.text, "words": []} for s in observed],
            "operation_events": port.operation_events, "cursor_state": port._cursor_state, "cursor_start": port.start_observation,
            "authority_events": port.authority_events, "adapter_start": port.adapter_start_payload,
            "adapter_start_ack": port.adapter_start_ack, "adapter_globals_restored": True,
            "real_resolver_approval_unchanged_none": real_resolver.REAL_APPROVAL is None,
            "binding_calls": port.binding_calls, "actual_factory_and_permit": True,
            "adapter_owned_cleanup": True, "retained_facade_and_stream_refused": True,
            "lifecycle_phase": record.phase.value, "read_set_released": port.read_set.released,
            "pipe_retired": port.pair.closed, "exit_observation": port.exit_observation,
            "write_access_observations": port.observations,
            "parent_guards_held_through_exit": port.parent_guards_held_through_exit,
            "adoption_case": port.case, "adoption_response": port.adoption_response,
            "authenticated_manifest": port.adoption_payload, "manifest_sha256": port.manifest,
            "controller_handshake_begun": port.handshake._begun, "model_calls": 0}


def _bound_worker_operations(pipes, pair, channel, adoption, fixed_root):
    _assert(real_resolver.REAL_APPROVAL is None, "child_real_model_authority_absent")
    original_functions = (real_resolver.load_manifest, real_resolver.admit_snapshot, real_resolver.bind_for_constructor)
    operation, payload = channel.decode(pipes.read_frame(pair, _remaining(pipes.clock)))
    expected = policy_payload(fixed_root, channel.binding)
    _assert(operation == "next" and _fixed(payload, expected)
            and adoption.status == "adopted" and not adoption.materialization_started,
            "child_generated_adapter_policy_before_begin")
    acknowledgement = policy_ack(payload)
    pipes.write_bytes(pair, channel.encode("done", acknowledgement), _remaining(pipes.clock))
    result = operation_flow._worker_operations(pipes, pair, channel, adoption)
    _assert(real_resolver.REAL_APPROVAL is None
            and (real_resolver.load_manifest, real_resolver.admit_snapshot, real_resolver.bind_for_constructor) == original_functions,
            "child_real_resolver_authority_unchanged")
    return {**result, "adapter_start": payload, "adapter_start_ack": acknowledgement,
            "real_resolver_approval_unchanged_none": True, "real_resolver_functions_unchanged": True}


def child_flow(primitives, pipes, inherited_control_value, expected_child_source_sha256, fixed_root, fixed_case):
    """Same adoption prefix; one explicit generated startup binding before begin."""
    _assert(fixed_case == "positive", "generated_operation_positive_adoption_only")
    fixed_paths(fixed_root)
    pair = pipes.adopt_inherited_client(inherited_control_value)
    channel = None
    adoption = InheritedReadSetAdoption(primitives)
    try:
        binding, key = decode_private_bootstrap(pipes.read_private_bootstrap(pair, _remaining(pipes.clock)))
        _assert(binding.bootstrap_source_sha256 == expected_child_source_sha256
                and binding.namespace_sha256 == namespace_digest(), "fixed_operation_source_and_namespace")
        current = primitives.api.call("GetCurrentProcess")
        values = [primitives.api.structure("FILETIME") for _ in range(4)]
        primitives.api.checked("GetProcessTimes", current, *(primitives.api.ffi.byref(value) for value in values))
        creation = int(values[0].low) | int(values[0].high) << 32
        _assert(creation == binding.process_creation_time, "child_operation_creation_binding")
        channel = GenerationChannel(binding, key, "worker")
        operation, payload = channel.decode(pipes.read_frame(pair, _remaining(pipes.clock)))
        expected = {"generation": binding.generation_hex, "namespace_sha256": binding.namespace_sha256}
        _assert(operation == "challenge" and payload == expected, "operation_challenge_binding")
        pipes.write_bytes(pair, channel.encode("ready", expected), _remaining(pipes.clock))
        operation, payload = channel.decode(pipes.read_frame(pair, _remaining(pipes.clock)))
        _assert(operation == "adopt_readset", "owned_readset_before_operation")
        adoption.adopt(payload, fixed_root, "positive", inherited_control_value, binding.manifest_sha256)
        _assert(adoption.status == "adopted" and adoption.inheritance_cleared == adoption.identities_checked == 5,
                "complete_adoption_before_operation")
        pipes.write_bytes(pair, channel.encode("readset_ready", operation_flow.adoption_flow.expected_adoption_response("positive")),
                          _remaining(pipes.clock))
        result = _bound_worker_operations(pipes, pair, channel, adoption, fixed_root)
        pipes.retire_endpoint(pair)
        return {"child_flow_return": 0, "adoption": adoption.receipt(), **result, "model_calls": 0}
    except BaseException:
        if adoption.read_set is not None:
            adoption.read_set.unconfirmed = True
        pipes._quarantine(pair)
        raise
    finally:
        if channel is not None:
            channel.revoke()
