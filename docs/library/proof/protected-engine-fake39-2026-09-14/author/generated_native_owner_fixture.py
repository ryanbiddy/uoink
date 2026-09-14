"""In-memory child-route seams. No process, native API, file or model calls.

The actual channel/bootstrap/owner/factory/dispatcher run. Adoption metadata,
handle operations and pipe transport are explicit fake seams. Generated teardown
restores test globals only; it supplies no native reclamation evidence.
"""
from contextlib import contextmanager
import json
from types import SimpleNamespace

import generated_adapter_flow as flow
import generated_operation_flow as operations
import owned_generation_protocol as protocol
import owned_guard as guard
from inherited_readset import InheritedReadSetAdoption, NAMES, GENERATED, namespace_digest

ROOT = r'E:\generated-runtime-owner-fixture'
SOURCE = '44' * 32


@contextmanager
def replaced(owner, name, value):
    original = vars(owner).get(name)
    present = name in vars(owner)
    setattr(owner, name, value)
    try:
        yield
    finally:
        if present:
            setattr(owner, name, original)
        else:
            delattr(owner, name)


class Fixture:
    def __init__(self, *, early_cancel=False):
        self.binding = protocol.GenerationBinding('11' * 32, '22' * 32,
            namespace_digest(), SOURCE, 9)
        self.key = b'\x55' * 32
        self.controller = protocol.GenerationChannel(self.binding, self.key, 'controller')
        self.frames, self.writes, self.events = [], [], []
        self.before_read = self.before_write = self.release_hook = self.quarantine_hook = None
        self.pair = SimpleNamespace(closed=False)
        self.read_set = SimpleNamespace(unconfirmed=False, released=False,
            members=[SimpleNamespace(closed=False) for _ in NAMES])
        self.primitives = SimpleNamespace(release_read_set=self.release_read_set,
            api=SimpleNamespace(call=self.call, checked=self.checked,
                structure=lambda name: SimpleNamespace(low=0, high=0),
                ffi=SimpleNamespace(byref=lambda value: value)))
        self.pipes = SimpleNamespace(clock=lambda: 1.0,
            adopt_inherited_client=lambda control: self.pair,
            read_private_bootstrap=lambda pair, expires: protocol.encode_private_bootstrap(self.binding, self.key),
            read_frame=self.read_frame, write_bytes=self.write_bytes,
            retire_endpoint=self.retire_endpoint, _quarantine=self.quarantine)
        self.add('challenge', {'generation': self.binding.generation_hex,
                             'namespace_sha256': self.binding.namespace_sha256})
        self.add('adopt_readset', {'explicit_fake_adoption': True})
        self.add('next', flow.policy_payload(ROOT, self.binding))
        if early_cancel:
            self.add('cancel', {})
        else:
            self.add('begin', {'manifest_sha256': self.binding.manifest_sha256})
            self.add('next', {'action': 'admit_generated_media', 'media_id': operations.MEDIA_ID})
            self.add('next', {'action': 'begin_generated_transcription', 'media_id': operations.MEDIA_ID,
                'options': {'language': None, 'word_timestamps': False, 'vad_filter': False,
                            'beam_size': 1, 'best_of': 1}})
            self.add('next', {'action': 'next_generated_segment', 'cursor_id': operations.CURSOR_ID, 'index': 0})
            self.add('next', {'action': 'cancel_generated_cursor', 'cursor_id': operations.CURSOR_ID})
            self.add('cancel', {})
        self.retained = None

    def add(self, op, payload):
        self.frames.append((op, payload, self.controller.encode(op, payload)))

    def call(self, name, *args):
        assert name == 'GetCurrentProcess'
        return 17

    def checked(self, name, current, first, *other):
        assert name == 'GetProcessTimes' and current == 17
        first.low, first.high = self.binding.process_creation_time, 0

    def read_frame(self, pair, expires):
        assert pair is self.pair and self.frames
        op, payload, frame = self.frames.pop(0)
        if self.before_read is not None:
            self.before_read(op, payload)
        return frame

    def write_bytes(self, pair, frame, expires):
        assert pair is self.pair
        # Inspect generated outbound bytes only to select a fake write failure.
        # Successful delivery still uses the actual authenticated decoder.
        envelope = json.loads(frame[protocol.HEADER.size:-32].decode('ascii'))
        if self.before_write is not None:
            self.before_write(envelope['op'], envelope['payload'])
        self.writes.append(self.controller.decode(frame))
        self.events.append('write:' + envelope['op'])

    def release_read_set(self, read_set):
        assert read_set is self.read_set
        if self.release_hook is not None:
            return self.release_hook(read_set)
        read_set.released = True
        for handle in read_set.members:
            handle.closed = True
        self.events.append('release_read_set')
        return True

    def retire_endpoint(self, pair):
        assert pair is self.pair
        pair.closed = True
        self.events.append('retire_endpoint')

    def quarantine(self, pair):
        assert pair is self.pair
        self.events.append('quarantine')
        if self.quarantine_hook is not None:
            self.quarantine_hook()

    def run(self):
        return flow.child_runtime_owner_flow(self.primitives, self.pipes, 23, SOURCE, ROOT, 'positive')


@contextmanager
def fixture(*, early_cancel=False):
    assert flow._RETAINED_CHILD_RUNTIME_BRIDGE is None and guard._RUNTIME is None
    f = Fixture(early_cancel=early_cancel)

    def adopt(a, payload, root, case, control, digest):
        assert payload == {'explicit_fake_adoption': True}
        assert root == ROOT and case == 'positive' and control == 23 and digest == f.binding.manifest_sha256
        a.read_set = f.read_set
        a.inheritance_cleared = a.identities_checked = 5
        a.status = 'adopted'
        f.events.append('fake_adoption')

    def materialize(a):
        assert a.status == 'adopted' and not a.materialization_started
        a.materialization_started = True
        a.namespace = SimpleNamespace(lookup=lambda name: GENERATED[name])
        a.status = 'materialized'
        f.events.append('fake_materialize')
        return operations.adoption_flow.expected_readback()

    try:
        with replaced(InheritedReadSetAdoption, 'adopt', adopt):
            with replaced(InheritedReadSetAdoption, 'materialize_generated', materialize):
                yield f
    finally:
        f.retained = flow._RETAINED_CHILD_RUNTIME_BRIDGE
        if f.retained is not None:
            try:
                f.retained.close_preserving(f.retained.failure)
            finally:
                if guard._RUNTIME is f.retained.bootstrap.registry:
                    guard._RUNTIME = None
        flow._RETAINED_CHILD_RUNTIME_BRIDGE = None
        f.controller.revoke()
