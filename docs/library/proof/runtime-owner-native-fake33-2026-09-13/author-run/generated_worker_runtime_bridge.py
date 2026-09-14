"""Fixed generated dispatcher bound to the actual worker-local runtime owner.

Only the fixed child route supplies this object. No real loader, PCM decoder,
model path, package import or factory is selected from a received message.
"""
import owned_generation_protocol as protocol
import worker_runtime_owner as owner_module
import owned_factory_port as factory_module
import model_binding_registry as registry_module
import owned_guard as guard
import generated_worker_factory_inputs as generated_inputs
import generated_operation_flow as operations
from inherited_readset import InheritedReadSetAdoption, NAMES, GENERATED, namespace_digest


class GeneratedBridgeRefusal(RuntimeError):
    pass


def _require(condition, reason):
    if not condition:
        raise GeneratedBridgeRefusal(reason)


class GeneratedWorkerRuntimeBridge:
    """Single private caller; one channel, cursor, owner and retained input set.

    The native child retains this whole bridge until process exit. The class
    does not turn retained references into a claim of native memory release.
    """
    def __init__(self, channel, adoption):
        _require(type(adoption) is InheritedReadSetAdoption, 'fixed_adoption_type')
        self.bootstrap = protocol.WorkerBootstrap(channel,
            owner_module._WorkerRuntimeOwnerProposal, factory_module._OwnedFactoryPortProposal)
        self.channel, self.adoption = channel, adoption
        self.inputs = None
        self.media_identity = object()
        self.state, self.index = 'initial', 0
        self.actions, self.events = [], []
        self.readback = self.start_observation = None
        self.texts = None
        self.guard_bound = self.clean_closed = False
        self.failure = None

    def accept_challenge(self, frame):
        _require(self.state == 'initial', 'bridge_challenge_order')
        response = self.bootstrap.accept_challenge(frame)
        self.state = 'ready'
        self.events.append('owner_ready')
        return response

    def adopted(self):
        a = self.adoption
        _require(self.state == 'ready' and a.status == 'adopted'
                 and a.inheritance_cleared == a.identities_checked == 5
                 and a.read_set is not None and not a.read_set.unconfirmed
                 and not a.read_set.released and not a.materialization_started,
                 'complete_readset_before_policy')
        self.state = 'adopted'
        self.events.append('readset_adopted')

    def policy_acknowledged(self):
        _require(self.state == 'adopted', 'policy_after_adoption')
        self.state = 'policy'
        self.events.append('policy_acknowledged')

    def accept_initial_control(self, frame):
        _require(self.state == 'policy', 'initial_after_policy')
        operation = self.bootstrap.accept_initial_control(frame)
        self.state = 'begun' if operation == 'begin' else 'cancel_before_begin'
        self.events.append(self.state)
        return operation

    def prepare_generated_factory(self):
        _require(self.state == 'begun' and self.inputs is None, 'factory_after_begin_only')
        a = self.adoption
        _require(a.status == 'adopted' and not a.materialization_started
                 and not a.read_set.unconfirmed and not a.read_set.released,
                 'unread_owned_namespace_before_factory')
        self.readback = a.materialize_generated()
        _require(self.readback == operations.adoption_flow.expected_readback()
                 and a.status == 'materialized', 'exact_generated_readback')
        pieces = tuple(a.namespace.lookup(name) for name in NAMES)
        _require(pieces == tuple(GENERATED[name] for name in NAMES)
                 and self.channel.binding.namespace_sha256 == namespace_digest(),
                 'adopted_generated_pieces')
        self.texts = tuple(a.namespace.lookup(name).decode('ascii').strip()
                           for name in operations.TEXT_MEMBERS)
        _require(self.texts == operations.TEXTS, 'fixed_generated_texts')
        self.events.append('namespace_materialized')
        _require(guard._RUNTIME is None, 'owned_guard_initially_closed')
        self.inputs = generated_inputs.GeneratedFactoryInputs()
        self.inputs.prepare()  # Input owner is retained before this attempt.
        guard._RUNTIME = self.bootstrap.registry
        self.guard_bound = True
        self.bootstrap.issue_generated_inputs(pieces, self.media_identity, generated_inputs.GENERATED_PCM)
        self.events.append('generated_inputs_issued')
        f = self.inputs
        result = self.bootstrap.build_factory_product(f.fixed, f.port, guard,
            f.state, f.state_binding, registry_module.FIXED_RECIPE_SHA256)
        _require(result == {'built': True}, 'actual_factory_result')
        self.state = 'new'
        self.events.append('actual_factory_registered')

    def next_frame(self, payload):
        """Validate a fixed command and commit one existing wire-shaped reply."""
        _require(type(payload) is dict and len(self.actions) < 8, 'bounded_generated_command')
        action = payload.get('action')
        next_state, next_index = self.state, self.index
        if action == 'admit_generated_media':
            _require(self.state == 'new' and payload == {
                'action': action, 'media_id': operations.MEDIA_ID}, 'generated_media_order')
            next_state = 'admitted'
            op, reply = 'done', operations.contract_payload(self.channel.binding)
        elif action == 'begin_generated_transcription':
            options = payload.get('options')
            _require(type(options) is dict and any(operations._fixed(options, fixed) for fixed in (
                {'language': None, 'word_timestamps': False, 'vad_filter': False, 'beam_size': 1, 'best_of': 1},
                {'language': 'en', 'word_timestamps': False, 'vad_filter': False, 'beam_size': 1, 'best_of': 1})),
                'fixed_generated_options')
            _require(self.state == 'admitted' and payload == {
                'action': action, 'media_id': operations.MEDIA_ID, 'options': options}, 'generated_start_order')
            next_state = 'active'
            op, reply = 'done', {'cursor_id': operations.CURSOR_ID, 'started': True, 'produced_segments': 0}
        elif action == 'next_generated_segment':
            _require(self.state == 'active' and type(payload.get('index')) is int
                     and payload == {'action': action, 'cursor_id': operations.CURSOR_ID,
                                     'index': self.index}, 'generated_segment_order')
            if self.index == len(operations.SEGMENTS):
                next_state = 'eof'
                op, reply = 'done', {'cursor_id': operations.CURSOR_ID, 'eof': True,
                                    'produced_segments': self.index}
            else:
                row = dict(operations.SEGMENTS[self.index])
                row['text'] = self.texts[self.index]
                op, reply = 'segment', {'cursor_id': operations.CURSOR_ID,
                                       'index': self.index, 'segment': row}
                next_index += 1
        elif action == 'cancel_generated_cursor':
            _require(self.state == 'active' and payload == {
                'action': action, 'cursor_id': operations.CURSOR_ID}, 'generated_cancel_order')
            next_state = 'cancelled'
            op, reply = 'done', {'cursor_id': operations.CURSOR_ID, 'cancelled': True,
                                'produced_segments': self.index}
        else:
            raise GeneratedBridgeRefusal('unknown_generated_action')
        b = self.bootstrap
        with b.use_operation() as token:
            with b.registry._lock:
                _require(not b._closed, 'publication_revoked')
                b.registry.assert_waveform_binding(b._generated_pcm, sample_rate=16000)
                b.registry.assert_vad_binding(b._product)
                if op == 'segment':
                    reply['segment']['text'] = b.registry.publish_generated_text(
                        token, b._generated_pcm, reply['segment']['text'])
                frame = self.channel.encode(op, reply)
                self.state, self.index = next_state, next_index
                if action == 'begin_generated_transcription':
                    self.start_observation = dict(reply)
                self.actions.append(action)
                self.events.append('segment_committed' if op == 'segment' else 'control_committed')
        return frame

    def prepare_closed_frame(self):
        """Retire before closed publication; never revoke a live reply channel."""
        a, b = self.adoption, self.bootstrap
        if self.state == 'cancel_before_begin':
            _require(self.inputs is None and b._factory_inputs is None
                     and b._generated_pcm is None and b._product is None
                     and a.status == 'adopted' and not a.materialization_started
                     and not a.read_set.unconfirmed and not a.read_set.released,
                     'unread_cancel_before_generated_allocation')
            _require(a.primitives.release_read_set(a.read_set) is True
                     and a.read_set.released, 'unread_handle_release_unconfirmed')
            a.status = 'released'
        else:
            _require(self.state in ('new', 'admitted', 'active', 'cancelled', 'eof'), 'session_close_order')
            if self.state == 'active':
                self.events.append('active_cursor_stopped')
            _require(b.release_factory_product() == {'retired_by_factory': True}, 'factory_retirement')
            self.events.append('actual_factory_retired')
            a.release_after_reads()
        self.events.append('child_readset_released')
        frame = self.channel.encode('closed', {})
        self.events.append('closed_frame_committed')
        self.state = 'closing'
        return frame

    def closed_written(self):
        _require(self.state == 'closing', 'closed_write_order')
        self.events.append('closed_frame_written')
        self.close_preserving()
        self.clean_closed = True
        self.state = 'closed'

    def close_preserving(self, original=None):
        first = original
        try:
            self.bootstrap.close_preserving(original)
        except BaseException as error:
            first = error if first is None else first
        if self.guard_bound:
            if guard._RUNTIME is self.bootstrap.registry:
                guard._RUNTIME = None
                self.guard_bound = False
            else:
                error = GeneratedBridgeRefusal('owned_guard_replaced_at_close')
                if first is None:
                    first = error
                else:
                    BaseException.add_note(first, str(error))
        if first is not None:
            self.failure = first
            self.clean_closed = False
            if original is None:
                raise first
        else:
            self.events.append('owner_and_channel_revoked')

    def receipt(self):
        b = self.bootstrap
        return {'connection': 'generated-owner-native-v1', 'state': self.state,
            'events': list(self.events), 'operation_events': list(self.actions),
            'produced_segments': self.index, 'generated_duration_only': True,
            'readback': self.readback, 'cursor_start': self.start_observation,
            'clean_closed': self.clean_closed, 'failure_type': type(self.failure).__name__ if self.failure else None,
            'factory_attempted': b._factory_attempted,
            'generated_factory_events': list(self.inputs.runtime.events) if self.inputs and self.inputs.runtime else [],
            'generated_state_retained': self.inputs is not None and bool(self.inputs.state),
            'owner_active_at_exit': b.registry._active if b.registry is not None else False,
            'channel_revoked': self.channel._revoked, 'owned_guard_restored_none': guard._RUNTIME is None,
            'model_calls': 0, 'model_inference_calls': 0, 'real_runtime_approved': False}
