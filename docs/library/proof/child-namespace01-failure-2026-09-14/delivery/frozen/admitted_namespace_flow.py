"""Fixed coordinator module for dormant controller-to-child namespace connection.

No ctypes import, DLL load, live process, model execution or physical port 5179 at import.
Only qualified controller and child entry methods using reviewed ownership primitives.
"""
from dataclasses import dataclass
import hashlib
from owned_generation_protocol import (
    GenerationBinding,
    GenerationChannel,
    WorkerBootstrap,
    ControllerHandshake,
    AdmittedNamespaceLease,
    validate_admitted_lease,
    encode_private_bootstrap,
    decode_private_bootstrap,
    ProtocolRefusal,
    _hex,
)
from asr_loading_adapter import (
    _consume_controller_startup,
    _validate_controller_stage,
    _validate_controller_stage_locked,
    AdapterRefusal,
)
from inherited_readset import (
    controller_admitted_envelope,
    validate_admitted_envelope,
    admitted_envelope_digest,
    expected_admitted_adoption_response,
    AdmittedReadSetAdoption,
    AdoptionRefusal,
    MODEL_MEMBERS,
)
from pinned_buffer_namespace import (
    PinnedBufferNamespace,
    NamespaceRefusal,
)
from worker_runtime_owner import _WorkerRuntimeOwnerProposal
from owned_factory_port import _OwnedFactoryPortProposal
from snapshot_lifecycle import Phase

MAX_WAIT_MS = 5000


class FlowRefusal(RuntimeError):
    pass


def _require(value, message):
    if not value:
        raise FlowRefusal(message)


def _remaining(clock):
    return clock() + 10.0


@dataclass
class _ControllerAttempt:
    startup: object
    permit: object
    session: object
    token: object
    pair: object = None
    worker: object = None
    envelope: dict = None
    envelope_digest: str = None
    binding: GenerationBinding = None
    channel: GenerationChannel = None
    handshake: ControllerHandshake = None
    error: BaseException = None


class AdmittedControllerPort:
    """Fixed controller port for suspended worker connection and envelope dispatch.

    Consumes controller startup before process work. Retains attempt, pair, worker,
    channel, and all custody before validation or any fallible call.
    """

    def __init__(self, primitives, pipes, startup, permit, session, release,
                 executable, arguments, working_directory, environment,
                 generation_hex, child_source_sha256, master_key, pipe_name_material,
                 model_spec):
        self.primitives = primitives
        self.pipes = pipes
        self.startup = startup
        self.permit = permit
        self.session = session
        self.release = release
        self.executable = executable
        self.arguments = arguments
        self.working_directory = working_directory
        self.environment = environment
        self.generation_hex = generation_hex
        self.child_source_sha256 = child_source_sha256
        self.master_key = master_key
        self.pipe_name_material = pipe_name_material
        self.model_spec = model_spec

        self.attempt = None
        self.adoption_response = None
        self.quarantined = False

    def execute_handshake(self, cancel=False):
        """Execute controller-to-child connection up to begin or cancel."""
        # 1. Consume controller authority before process work
        token = _consume_controller_startup(self.startup, self.permit, self.session)
        self.attempt = _ControllerAttempt(
            startup=self.startup,
            permit=self.permit,
            session=self.session,
            token=token,
        )

        record = self.session._record
        protection = record.protection
        selection = getattr(self.release, "selection", None) or getattr(record, "selection", None)
        profile = getattr(self.release, "profile", None) or getattr(record, "profile", None)

        try:
            # 2. Attach to suspended worker
            pair = self.pipes.create_pair(self.pipe_name_material, _remaining(self.pipes.clock))
            self.attempt.pair = pair
            pair.read_set = protection

            worker = self.pipes.attach_to_suspended_worker(
                pair, protection, self.executable, self.arguments,
                self.working_directory, self.environment
            )
            self.attempt.worker = worker
            record.worker = worker

            # 3. Create admitted envelope
            envelope = controller_admitted_envelope(
                self.primitives, protection, worker, record, self.model_spec
            )
            envelope_digest = admitted_envelope_digest(envelope)
            self.attempt.envelope = envelope
            self.attempt.envelope_digest = envelope_digest

            # 4. Bind exact read set, process creation time, fixed child source and generation
            binding = GenerationBinding(
                self.generation_hex,
                envelope.get("manifest_sha256"),
                getattr(protection, "namespace_digest", lambda: "0" * 64)(),
                self.child_source_sha256,
                worker.creation_time,
            )
            self.attempt.binding = binding

            channel = GenerationChannel(binding, self.master_key, "controller")
            self.attempt.channel = channel

            # Handshake receives permit's token; session retains actual permit wrapper
            handshake = ControllerHandshake(
                channel, self.session, token.token, self.primitives, worker
            )
            self.attempt.handshake = handshake

            # Pre-effects stage check
            _validate_controller_stage(token, self.startup, self.release, selection, profile)

            # 5. Bootstrap transmission & challenge / ready handshake
            bootstrap_packet = encode_private_bootstrap(binding, self.master_key)
            self.pipes.write_bytes(pair, bootstrap_packet, _remaining(self.pipes.clock))

            challenge_frame = handshake.challenge()
            self.pipes.write_bytes(pair, challenge_frame, _remaining(self.pipes.clock))

            ready_frame = self.pipes.read_frame(pair, _remaining(self.pipes.clock))
            handshake.accept_ready(ready_frame)

            # 6. Envelope dispatch
            envelope_frame = channel.encode("adopt_admitted_readset", envelope)
            self.pipes.write_bytes(pair, envelope_frame, _remaining(self.pipes.clock))

            response_frame = self.pipes.read_frame(pair, _remaining(self.pipes.clock))
            operation, response = channel.decode(response_frame)
            _require(
                operation in ("admitted_readset_ready", "readset_ready")
                and response == expected_admitted_adoption_response("positive"),
                "admitted_readset_response_unexpected",
            )
            self.adoption_response = response

            # 7. Initial control: begin or cancel
            if cancel:
                cancel_frame = handshake.cancel()
                self.pipes.write_bytes(pair, cancel_frame, _remaining(self.pipes.clock))
                # Read child's closed frame
                closed_frame = self.pipes.read_frame(pair, _remaining(self.pipes.clock))
                closed_op, closed_payload = channel.decode(closed_frame)
                _require(closed_op == "closed", "expected_closed_operation_on_cancel")
            else:
                begin_frame = handshake.begin_admitted(envelope_digest)
                self.pipes.write_bytes(pair, begin_frame, _remaining(self.pipes.clock))

            # Post-consumption stage check at publication boundary
            _validate_controller_stage(token, self.startup, self.release, selection, profile)

            return {
                "status": "cancelled" if cancel else "begun",
                "attempt": self.attempt,
                "worker": worker,
                "envelope": envelope,
                "envelope_digest": envelope_digest,
                "adoption_response": self.adoption_response,
            }

        except BaseException as original:
            if self.attempt is not None:
                self.attempt.error = original
            if self.attempt is not None and self.attempt.pair is not None:
                try:
                    self.pipes._quarantine(self.attempt.pair)
                    self.quarantined = True
                except BaseException as cleanup:
                    BaseException.add_note(
                        original, "Pipe quarantine remains unconfirmed: " + type(cleanup).__name__
                    )
            raise


def child_admitted_flow(
    primitives,
    pipes,
    inherited_control_value,
    expected_child_source_sha256,
    model_spec,
    registry_type=_WorkerRuntimeOwnerProposal,
    factory_type=_OwnedFactoryPortProposal,
):
    """Child-side execution of admitted namespace connection up to lease issuance.

    Adopts inherited pipe, decodes bootstrap, verifies process creation time and source,
    conducts challenge/ready, verifies and adopts admitted envelope, processes initial
    control (begin or cancel), materializes buffers, and issues child-local lease.
    """
    pair = pipes.adopt_inherited_client(inherited_control_value)
    channel = None
    bootstrap = None
    adoption = AdmittedReadSetAdoption(primitives)
    first_error = None

    try:
        # 1. Decode private bootstrap
        bootstrap_data = pipes.read_private_bootstrap(pair, _remaining(pipes.clock))
        binding, key = decode_private_bootstrap(bootstrap_data)

        _require(
            binding.bootstrap_source_sha256 == expected_child_source_sha256,
            "child_source_sha256_mismatch",
        )

        # 2. Verify process creation time
        current_process = primitives.api.call("GetCurrentProcess")
        creation_time = primitives._creation_time(current_process)
        _require(
            creation_time == binding.process_creation_time,
            "child_process_creation_time_mismatch",
        )

        # 3. Channel & bootstrap initialization
        channel = GenerationChannel(binding, key, "worker")
        bootstrap = WorkerBootstrap(channel, registry_type, factory_type)

        # 4. Challenge / ready handshake
        challenge_frame = pipes.read_frame(pair, _remaining(pipes.clock))
        ready_frame = bootstrap.accept_challenge(challenge_frame)
        pipes.write_bytes(pair, ready_frame, _remaining(pipes.clock))

        # 5. Envelope reception and adoption
        envelope_frame = pipes.read_frame(pair, _remaining(pipes.clock))
        operation, envelope = channel.decode(envelope_frame)
        _require(
            operation in ("adopt_admitted_readset", "adopt_readset"),
            "unexpected_envelope_operation",
        )

        adoption.adopt_admitted(envelope, binding, model_spec)
        envelope_digest = admitted_envelope_digest(envelope)
        bootstrap.bind_admitted_envelope(envelope, envelope_digest)

        ack_frame = channel.encode(
            "admitted_readset_ready",
            expected_admitted_adoption_response("positive"),
        )
        pipes.write_bytes(pair, ack_frame, _remaining(pipes.clock))

        # 6. Initial control: begin or cancel
        initial_frame = pipes.read_frame(pair, _remaining(pipes.clock))
        initial_operation = bootstrap.accept_initial_control(initial_frame)

        if initial_operation == "begin":
            # Materialization allowed only after begin
            adoption.mark_begin_accepted()
            adoption.materialize_admitted()

            # Issue child-local lease
            lease = bootstrap.issue_admitted_namespace(
                adoption,
                adoption.namespace,
                envelope["selection"],
                envelope["profile"],
            )
            validate_admitted_lease(lease, bootstrap)

            return {
                "status": "issued",
                "lease": lease,
                "adoption": adoption.receipt(),
                "bootstrap": bootstrap,
                "namespace": adoption.namespace,
                "member_count": len(adoption.namespace.buffers),
            }

        elif initial_operation == "cancel":
            # Initial cancel releases unread adoption, sends closed, closes/revokes
            adoption.release_unread()
            closed_frame = channel.encode("closed", {"status": "closed"})
            pipes.write_bytes(pair, closed_frame, _remaining(pipes.clock))
            bootstrap.close_preserving()
            pipes.retire_endpoint(pair)

            return {
                "status": "cancelled",
                "lease": None,
                "adoption": adoption.receipt(),
                "bootstrap": bootstrap,
                "namespace": None,
                "member_count": 0,
            }

        else:
            raise FlowRefusal("unexpected_initial_operation: " + str(initial_operation))

    except BaseException as original:
        first_error = original
        if bootstrap is not None:
            try:
                bootstrap.close_preserving(original)
            except BaseException as cleanup:
                BaseException.add_note(
                    original, "Bootstrap revocation remains unconfirmed: " + type(cleanup).__name__
                )
        if adoption.read_set is not None:
            adoption.read_set.unconfirmed = True
        try:
            pipes._quarantine(pair)
        except BaseException as cleanup:
            BaseException.add_note(
                original, "Pipe quarantine remains unconfirmed: " + type(cleanup).__name__
            )
        raise
    finally:
        if bootstrap is None and channel is not None:
            try:
                channel.revoke()
            except BaseException as cleanup:
                if first_error is not None:
                    BaseException.add_note(
                        first_error, "Channel revocation remains unconfirmed: " + type(cleanup).__name__
                    )
                else:
                    raise
