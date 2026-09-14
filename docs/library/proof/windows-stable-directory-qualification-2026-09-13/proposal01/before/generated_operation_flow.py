"""Source-only generated OperationFacade flow; no work occurs at import.

The exact future bootstrap supplies the reviewed native API objects. This module
does not grant runtime authority. Every returned word is generated fixture text.
"""
from contextlib import contextmanager
from threading import RLock
import generated_worker_flow as adoption_flow
from owned_generation_protocol import GenerationChannel, decode_private_bootstrap
from snapshot_lifecycle import (OwnedRuntimeFactory, OwnedSession, OperationFacade,
    MediaResultContract, TranscribeRequest, Segment, SessionClosed, Phase)
from inherited_readset import (InheritedReadSetAdoption, GENERATED, namespace_digest,
    fixed_paths)

_assert = adoption_flow._assert
_remaining = adoption_flow._remaining
declare_exit_call = adoption_flow.declare_exit_call
MEDIA_ID = "generated-media-01"
CURSOR_ID = "generated-cursor-01"
TEXT_MEMBERS = ("config.json", "tokenizer.json")
TEXTS = tuple(GENERATED[name].decode("ascii").strip() for name in TEXT_MEMBERS)
SEGMENTS = tuple({"start": index / 2, "end": (index + 1) / 2,
                  "text": text, "words": []} for index, text in enumerate(TEXTS))
BOUNDS = {"sample_rate": 16000, "sample_count": 16000, "max_segments": 2,
          "max_words": 1, "max_text_chars": sum(len(text) for text in TEXTS)}


def _fixed(actual, expected):
    """Exact fixed passive shape, including bool versus integer distinctions."""
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(_fixed(actual[key], value) for key, value in expected.items())
    if type(expected) is list:
        return len(actual) == len(expected) and all(_fixed(a, b) for a, b in zip(actual, expected))
    return type(expected) in (str, int, float, bool, type(None)) and actual == expected


def contract_payload(binding):
    return {"media_id": MEDIA_ID, "generation": binding.generation_hex,
            "manifest_sha256": binding.manifest_sha256,
            "namespace_sha256": namespace_digest(), "generated_only": True,
            "bounds": dict(BOUNDS)}


def fixed_options(request):
    _assert(type(request) is TranscribeRequest and (request.language is None
            or type(request.language) is str and request.language == "en")
            and request.word_timestamps is False and request.vad_filter is False
            and type(request.beam_size) is int and request.beam_size == 1
            and type(request.best_of) is int and request.best_of == 1,
            "fixed_generated_options_only")
    return {"language": request.language, "word_timestamps": False, "vad_filter": False,
            "beam_size": 1, "best_of": 1}


class GeneratedLifecyclePort(adoption_flow.GeneratedLifecyclePort):
    """One generated-only session with local identities and serial IPC.

    The base owns process/pipe/read handles. This subclass implements only the
    fixed facade methods. Neither class implements durable crash recovery.
    """

    def __init__(self, *args, operation_mode="drain", **kwargs):
        super().__init__(*args, **kwargs)
        _assert(self.case == "positive" and operation_mode in ("drain", "cancel"),
                "positive_generated_adoption_and_fixed_operation_mode")
        self.operation_mode = operation_mode
        self._operation_lock = RLock()
        self._operation_active = False
        self._ticket = self._contract = self._cursor = None
        self._cursor_state = "new"
        self._next_index = 0
        self.operation_events = []
        self.start_observation = None

    def issue_generated_media_ticket(self, session):
        # This exact controller-side setup call is not an API for caller media.
        with self.lifecycle._lock:
            record = self._record(self.read_set, self.permit)
            _assert(type(session) is OwnedSession and record.owner is session
                    and session._manager is self.lifecycle and session._worker is self.worker
                    and record.phase is Phase.NATIVE_RUNNING and self._ticket is None,
                    "single_owned_generated_ticket")
            session._require_live()
            self._ticket = object()
            return self._ticket

    @contextmanager
    def _operation(self, worker):
        with self._operation_lock:
            _assert(not self._operation_active, "serial_generated_operation_required")
            self._operation_active = True
            try:
                record = self._record(self.read_set, self.permit)
                _assert(worker is self.worker and record.owner._worker is worker
                        and record.owner._active == 1 and record.phase is Phase.NATIVE_RUNNING,
                        "facade_call_and_exact_worker_required")
                self.handshake._owned_phase(False)
                yield
                self.handshake._owned_phase(False)
            except BaseException as original:
                # Authenticated but invalid responses and ordinary Python
                # errors also revoke the lifecycle, not only interruptions.
                with self.lifecycle._lock:
                    record = self.lifecycle._records.get(self.key)
                    if record is not None:
                        self.lifecycle._quarantine_preserving(record, "Generated operation failed", original)
                raise
            finally:
                self._operation_active = False

    def _exchange(self, payload):
        _assert(self._operation_active, "owned_exchange_scope")
        self.pipes.write_bytes(self.pair, self.channel.encode("next", payload), _remaining(self.pipes.clock))
        result = self.channel.decode(self.pipes.read_frame(self.pair, _remaining(self.pipes.clock)))
        self.operation_events.append(payload["action"])
        return result

    def admit_media_request(self, worker, permit, ticket):
        with self._operation(worker):
            _assert(permit is self.permit and ticket is self._ticket and ticket is not None
                    and self._contract is None and self._cursor_state == "new", "exact_generated_ticket")
            self.pipes.write_bytes(self.pair, self.handshake.begin(), _remaining(self.pipes.clock))
            operation, payload = self._exchange({"action": "admit_generated_media", "media_id": MEDIA_ID})
            _assert(operation == "done" and _fixed(payload, contract_payload(self.channel.binding)),
                    "worker_issued_generated_contract")
            self._contract = MediaResultContract(permit, ticket, **BOUNDS)
            return self._contract

    def is_issued_media_contract(self, worker, permit, contract):
        with self._operation(worker):
            return (permit is self.permit and contract is self._contract and contract is not None
                    and contract.permit_identity is permit and contract.media_identity is self._ticket)

    def begin_transcription(self, worker, contract, request):
        with self._operation(worker):
            _assert(contract is self._contract and contract is not None
                    and request.media_ticket is self._ticket and self._cursor_state == "new",
                    "issued_contract_before_generated_transcription")
            options = fixed_options(request)
            operation, payload = self._exchange({"action": "begin_generated_transcription", "media_id": MEDIA_ID,
                                                  "options": options})
            _assert(operation == "done" and _fixed(payload, {"cursor_id": CURSOR_ID, "started": True,
                    "produced_segments": 0}), "lazy_generated_cursor_start")
            self.start_observation = dict(payload)
            self._cursor = object()
            self._cursor_state = "active"
            return self._cursor

    def next_segment(self, worker, cursor):
        with self._operation(worker):
            _assert(cursor is self._cursor and cursor is not None and self._cursor_state == "active",
                    "exact_active_generated_cursor")
            operation, payload = self._exchange({"action": "next_generated_segment", "cursor_id": CURSOR_ID,
                                                  "index": self._next_index})
            if self._next_index == len(SEGMENTS):
                _assert(operation == "done" and _fixed(payload, {"cursor_id": CURSOR_ID, "eof": True,
                        "produced_segments": len(SEGMENTS)}), "complete_generated_eof")
                self._cursor_state = "eof"
                return None
            expected = {"cursor_id": CURSOR_ID, "index": self._next_index, "segment": SEGMENTS[self._next_index]}
            _assert(operation == "segment" and _fixed(payload, expected), "fixed_generated_segment")
            value = payload["segment"]
            self._next_index += 1
            return Segment(value["start"], value["end"], value["text"], ())

    def cancel_transcription(self, worker, cursor):
        with self._operation(worker):
            _assert(cursor is self._cursor and cursor is not None and self._cursor_state == "active",
                    "active_generated_cursor_for_cancel")
            operation, payload = self._exchange({"action": "cancel_generated_cursor", "cursor_id": CURSOR_ID})
            _assert(operation == "done" and _fixed(payload, {"cursor_id": CURSOR_ID, "cancelled": True,
                    "produced_segments": self._next_index}), "generated_cursor_cancel_acknowledged")
            self._cursor_state = "cancelled"
            return True

    def close_and_join(self, worker, permit):
        # Session close revokes before calling the port. It must not invoke the
        # live-operation handshake check. Serialize against an admitted request;
        # the lifecycle separately refuses release while a caller remains active.
        with self._operation_lock:
            _assert(not self._operation_active, "operation_must_return_before_worker_close")
            return super().close_and_join(worker, permit)


def _require_session_closed(callback):
    try:
        callback()
    except SessionClosed:
        return True
    raise AssertionError("Retained operation must refuse after session close")


def controller_flow(port):
    _assert(type(port) is GeneratedLifecyclePort, "exact_generated_operation_port")
    with port.lifecycle.read_lease(port.cwd, "generated-dummy", port.generation) as lease:
        permit = lease.begin_native_session()
        session = OwnedRuntimeFactory(port.lifecycle).open_owned_session(port.profile, permit)
        facade = session.operations()
        _assert(type(facade) is OperationFacade, "exact_operation_facade")
        ticket = port.issue_generated_media_ticket(session)
        request = TranscribeRequest(ticket, language="en")
        stream = facade.transcribe(request)
        _assert(port._next_index == 0 and port.operation_events == ["admit_generated_media",
                "begin_generated_transcription"], "start_does_not_consume_segments")
        observed = [next(stream)]
        if port.operation_mode == "drain":
            observed.append(next(stream))
            try:
                next(stream)
            except StopIteration:
                pass
            else:
                raise AssertionError("Generated stream must end after two segments")
            _assert(port._cursor_state == "eof", "generated_eof_recorded")
        else:
            stream.close()
            _assert(port._cursor_state == "cancelled" and port._next_index == 1,
                    "cancel_stops_before_second_generated_segment")
            before = tuple(port.operation_events)
            try:
                next(stream)
            except StopIteration:
                pass
            else:
                raise AssertionError("Cancelled stream must refuse further results")
            _assert(tuple(port.operation_events) == before, "cancelled_stream_has_no_wire_use")
        _assert(len(port.read_set.members) == 5 and all(not h.closed for h in port.read_set.members),
                "parent_guards_through_facade_consumption")
        for path, expected in port.expectations:
            port.observations.append(adoption_flow._write_access_probe(port.primitives, path, True))
        _assert(session.close_and_join() is True, "generated_operation_join")
        lease.confirm_native_closed()
    before = tuple(port.operation_events)
    _require_session_closed(lambda: facade.transcribe(request))
    _require_session_closed(lambda: next(stream))
    _assert(tuple(port.operation_events) == before, "retained_references_have_no_wire_use")
    for path, expected in port.expectations:
        port.observations.append(adoption_flow._write_access_probe(port.primitives, path, False))
    return {"operation_mode": port.operation_mode,
            "segments": [{"start": s.start, "end": s.end, "text": s.text, "words": []} for s in observed],
            "operation_events": port.operation_events, "cursor_state": port._cursor_state,
            "cursor_start": port.start_observation,
            "retained_facade_and_stream_refused": True, "lifecycle_phase": lease._record.phase.value,
            "read_set_released": port.read_set.released, "pipe_retired": port.pair.closed,
            "exit_observation": port.exit_observation, "write_access_observations": port.observations,
            "parent_guards_held_through_exit": port.parent_guards_held_through_exit,
            "adoption_case": port.case, "adoption_response": port.adoption_response,
            "authenticated_manifest": port.adoption_payload, "manifest_sha256": port.manifest,
            "controller_handshake_begun": port.handshake._begun, "model_calls": 0}


def _worker_operations(pipes, pair, channel, adoption):
    """Serial child dispatcher for fixed generated requests; no callable lookup."""
    operation, payload = channel.decode(pipes.read_frame(pair, _remaining(pipes.clock)))
    if operation == "cancel":
        _assert(payload == {} and adoption.status == "adopted"
                and not adoption.materialization_started and not adoption.read_set.unconfirmed,
                "close_before_generated_read_or_transcription")
        _assert(adoption.primitives.release_read_set(adoption.read_set) is True
                and adoption.read_set.released, "unread_child_handle_release")
        adoption.status = "released"
        pipes.write_bytes(pair, channel.encode("closed", {}), _remaining(pipes.clock))
        return {"readback": None, "operation_events": [], "cursor_state": "not_started",
                "produced_segments": 0, "generated_duration_only": True}
    _assert(operation == "begin" and payload == {"manifest_sha256": channel.binding.manifest_sha256},
            "generated_begin_manifest")
    readback = adoption.materialize_generated()
    _assert(readback == adoption_flow.expected_readback(), "generated_namespace_before_contract")
    # These exact decoded bytes are owned by the adopted namespace. No path is
    # reopened and no constructor, waveform or decoder is invoked.
    texts = tuple(adoption.namespace.lookup(name).decode("ascii").strip() for name in TEXT_MEMBERS)
    _assert(texts == TEXTS, "generated_text_source_binding")
    state, index, actions = "new", 0, []
    start_observation = None
    for _ in range(9):
        operation, payload = channel.decode(pipes.read_frame(pair, _remaining(pipes.clock)))
        if operation == "cancel":
            _assert(payload == {} and state in ("eof", "cancelled", "active", "admitted", "new"),
                    "fixed_generated_session_cancel")
            adoption.release_after_reads()
            pipes.write_bytes(pair, channel.encode("closed", {}), _remaining(pipes.clock))
            return {"readback": readback, "operation_events": actions, "cursor_state": state,
                    "produced_segments": index, "generated_duration_only": True, "cursor_start": start_observation}
        _assert(operation == "next" and type(payload) is dict, "fixed_generated_request_operation")
        action = payload.get("action")
        if action == "admit_generated_media":
            _assert(state == "new" and payload == {"action": action, "media_id": MEDIA_ID},
                    "generated_media_admission_order")
            state = "admitted"
            response_operation, response = "done", contract_payload(channel.binding)
        elif action == "begin_generated_transcription":
            options = payload.get("options")
            _assert(type(options) is dict and any(_fixed(options, fixed) for fixed in (
                {"language": None, "word_timestamps": False, "vad_filter": False, "beam_size": 1, "best_of": 1},
                {"language": "en", "word_timestamps": False, "vad_filter": False, "beam_size": 1, "best_of": 1})),
                "worker_fixed_options")
            _assert(state == "admitted" and payload == {"action": action, "media_id": MEDIA_ID, "options": options},
                    "single_generated_transcription_start")
            state = "active"
            response_operation, response = "done", {"cursor_id": CURSOR_ID, "started": True, "produced_segments": 0}
            start_observation = dict(response)
        elif action == "next_generated_segment":
            _assert(state == "active" and type(payload.get("index")) is int
                    and payload == {"action": action, "cursor_id": CURSOR_ID, "index": index},
                    "generated_cursor_sequence")
            if index == len(SEGMENTS):
                state = "eof"
                response_operation, response = "done", {"cursor_id": CURSOR_ID, "eof": True, "produced_segments": index}
            else:
                row = dict(SEGMENTS[index])
                row["text"] = texts[index]
                response_operation, response = "segment", {"cursor_id": CURSOR_ID, "index": index, "segment": row}
                index += 1
        elif action == "cancel_generated_cursor":
            _assert(state == "active" and payload == {"action": action, "cursor_id": CURSOR_ID},
                    "generated_cursor_cancel_order")
            state = "cancelled"
            response_operation, response = "done", {"cursor_id": CURSOR_ID, "cancelled": True, "produced_segments": index}
        else:
            raise AssertionError("Unknown generated operation action")
        actions.append(action)
        pipes.write_bytes(pair, channel.encode(response_operation, response), _remaining(pipes.clock))
    raise AssertionError("Generated operation frame bound exceeded")


def child_flow(primitives, pipes, inherited_control_value, expected_child_source_sha256, fixed_root, fixed_case):
    """The fixed bootstrap owns cleanup/abort on any unconfirmed pipe operation."""
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
        pipes.write_bytes(pair, channel.encode("readset_ready", adoption_flow.expected_adoption_response("positive")),
                          _remaining(pipes.clock))
        result = _worker_operations(pipes, pair, channel, adoption)
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
