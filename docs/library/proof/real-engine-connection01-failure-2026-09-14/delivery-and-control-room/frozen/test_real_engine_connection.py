"""Inert unit tests for admitted real-engine connection and protected ownership.

Tests exercise:
- Authenticated selection/handle/member mismatch before construction
- Pre-begin cancel without materialization
- Forged or copied namespace lease refusal
- Successful five-file forwarding with fixed class/VAD/profile identity
- Four-file, empty preprocessor and missing tokenizer refusal before any path service
- Constructor dictionary mutation immunity (pinned namespace buffers survive pops)
- Explicit CPU and options policy enforcement (device='cpu', compute_type, beam/best_of=1)
- Model and tokenizer retention when downstream constructors fail
- Revocation during construction with returned objects retained
- Publication refusal after revocation
- Secondary cleanup failure preserving the original error
- Nested/overlapping operation refusal

Source authoring only: no native execution, no subprocess, no torch/pyannote import.
"""
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType, SimpleNamespace
import unittest

from pinned_buffer_namespace import (
    BufferAsset, PinnedBufferNamespace, AdmittedNamespaceRecord,
    FOUR, FIVE, NamespaceRefusal
)
from inherited_readset import (
    InheritedReadSetAdoption, validate_admitted_manifest, ADMITTED_FORMAT, ReadSetRefusal
)
from worker_runtime_owner import (
    _WorkerRuntimeOwnerProposal, _AdmittedNamespaceLease, RuntimeOwnerRefusal
)
from owned_generation_protocol import (
    WorkerBootstrap, GenerationChannel, GenerationBinding, ProtocolRefusal
)
from owned_asr_engine import (
    OwnedASREngine, _EngineConstructionPolicy, execute_admitted_construction,
    construct_owned_asr_engine, EngineRefusal,
    FOUR, FIVE, FOUR_FILE_MODELS, FIVE_FILE_MODELS,
    FEATURE_EXTRACTOR_DEFAULTS, COMPANION_DELTA_B3_NO_PATH
)
from after.whisperx.asr import _load_admitted_model_from_namespace
import model_binding_registry as registry_module
import owned_factory_port as factory_module
import owned_guard as guard


# --- Inert Win32 & System Primitives ---

class FakeHandle:
    def __init__(self, value, label="fake-handle"):
        self.value = value
        self.closed = False
        self.label = label
        self.read_offset = 0
        self.inherited = True


class FakeFFIValue:
    def __init__(self, val=0):
        self.value = val


class FakeFFI:
    def c_int64(self, val=0):
        return FakeFFIValue(val)

    def c_uint32(self, val=0):
        return FakeFFIValue(val)

    def byref(self, item):
        return item

    def create_string_buffer(self, size):
        class Buf:
            def __init__(self, s):
                self.raw = bytearray(s)
        return Buf(size)


class FakeWin32API:
    """Inert Win32 API mock with exact checked() argument offsets.

    primitives.api.checked(name, handle, *args) passes handle as 2nd arg.
    SetFilePointerEx: args[0]=offset, args[1]=byref(pos), args[2]=method
    ReadFile: args[0]=scratch, args[1]=requested, args[2]=byref(count), args[3]=overlapped
    GetHandleInformation: args[0]=byref(flags)
    SetHandleInformation: args[0]=mask, args[1]=flags
    """
    def __init__(self, storage):
        self.ffi = FakeFFI()
        self.storage = storage

    def checked(self, fn_name, handle, *args):
        if fn_name == "SetFilePointerEx":
            # args[0] is offset, args[1] is byref(position), args[2] is origin
            if len(args) > 1 and hasattr(args[1], "value"):
                args[1].value = 0
            handle.read_offset = 0
            return 1
        elif fn_name == "ReadFile":
            # args[0] is scratch, args[1] is requested, args[2] is byref(count), args[3] is overlapped
            scratch = args[0]
            requested = args[1]
            count = args[2]
            data = self.storage.get(handle.value, b"")
            offset = getattr(handle, "read_offset", 0)
            chunk = data[offset:offset + requested]
            scratch.raw[:len(chunk)] = chunk
            count.value = len(chunk)
            handle.read_offset = offset + len(chunk)
            return 1
        elif fn_name == "GetHandleInformation":
            # args[0] is byref(flags)
            flags = args[0]
            flags.value = 1 if getattr(handle, "inherited", True) else 0
            return 1
        elif fn_name == "SetHandleInformation":
            # args[0] is mask, args[1] is flags
            handle.inherited = bool(args[1] & 1) if len(args) > 1 else False
            return 1
        return 1


class FakePrimitives:
    def __init__(self, storage):
        self.read_sets = []
        self.handles = []
        self.storage = storage
        self.api = FakeWin32API(storage)

    def _owned(self, handle):
        return handle

    def _retain(self, value, label):
        handle = FakeHandle(value, label)
        self.handles.append(handle)
        return handle

    def release_read_set(self, read_set):
        read_set.released = True
        for h in read_set.members:
            h.closed = True
        return True


class FakeReadSet:
    def __init__(self, members=None):
        self.members = list(members or [])
        self.unconfirmed = False
        self.released = False


# --- Inert WhisperX / ASR Mocks ---

class FakeTokenizer:
    def __init__(self, hf_tokenizer=None, is_multilingual=True, task="transcribe", language=None):
        self.hf_tokenizer = hf_tokenizer
        self.is_multilingual = is_multilingual
        self.task = task
        self.language_code = language
        self.eot = 50256
        self.tokenizer = self

    def encode(self, text):
        return [1, 2, 3]

    def decode(self, tokens):
        return "fake text"

    def decode_batch(self, batch):
        return ["fake text" for _ in batch]


class FakeWhisperModel:
    """Inert WhisperModel mock simulating B3 files popping and storage."""
    def __init__(self, model_size_or_path, device="auto", device_index=0, compute_type="default",
                 cpu_threads=0, num_workers=1, download_root=None, local_files_only=False,
                 files=None, **kwargs):
        self.model_size_or_path = model_size_or_path
        self.device = device
        self.device_index = device_index
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self.num_workers = num_workers
        self.local_files_only = local_files_only
        self.raw_files_copy = dict(files) if files is not None else None

        # Simulate B3 popping tokenizer and preprocessor files
        tokenizer_bytes = files.pop("tokenizer.json", None) if files else None
        preprocessor_bytes = files.pop("preprocessor_config.json", None) if files else None

        self.tokenizer_bytes = tokenizer_bytes
        self.preprocessor_bytes = preprocessor_bytes
        self.remaining_files = dict(files) if files else None
        self.hf_tokenizer = FakeTokenizer()
        self.model = SimpleNamespace(is_multilingual=True)
        self.prepared = True

    def prepare(self):
        self.prepared = True


class FakeTranscriptionOptions:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeFasterWhisperPipeline:
    def __init__(self, model, vad, options=None, tokenizer=None, language=None,
                 suppress_numerals=False, vad_params=None):
        self.model = model
        self.vad_model = vad
        self.options = options
        self.tokenizer = tokenizer
        self.language = language
        self.suppress_numerals = suppress_numerals
        self.vad_params = vad_params
        self.model_path = getattr(model, "model_size_or_path", "uoink-memory-fake")
        self.prepared = True

    def prepare(self):
        self.prepared = True


# --- Inert Admitted Fixture Helpers ---

@dataclass(frozen=True, slots=True)
class FakeModelAsset:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class FakeSelectedModel:
    choice: str
    assets: tuple


@dataclass(frozen=True, slots=True)
class FakeRuntimeProfile:
    device: str = "cpu"
    compute_type: str = "int8"
    cpu_threads: int = 4
    num_workers: int = 1


def create_five_file_data():
    return {
        "config.json": b'{"vocab_size": 51865, "d_model": 384}',
        "model.bin": b"\x00" * 1024,
        "preprocessor_config.json": b'{"feature_size": 80, "sampling_rate": 16000}',
        "tokenizer.json": b'{"version": "1.0", "model": {"type": "BPE"}}',
        "vocabulary.json": b'{"<|endoftext|>": 50256}',
    }


def create_admitted_fixtures(file_data=None):
    if file_data is None:
        file_data = create_five_file_data()

    storage = {}
    assets = []
    members = []
    for idx, (name, data) in enumerate(sorted(file_data.items())):
        handle = FakeHandle(idx + 100, name)
        storage[handle.value] = data
        members.append(handle)
        digest = hashlib.sha256(data).hexdigest()
        assets.append(BufferAsset(name, len(data), digest, handle))

    primitives = FakePrimitives(storage)
    read_set = FakeReadSet(members)
    primitives.read_sets.append(read_set)

    pinned = PinnedBufferNamespace(primitives, read_set, tuple(assets), 10 * 1024 * 1024)
    pinned.materialize()

    model_assets = tuple(FakeModelAsset(a.name, a.size, a.sha256) for a in assets)
    selected_model = FakeSelectedModel("large-v3-turbo", model_assets)
    profile = FakeRuntimeProfile(device="cpu", compute_type="int8", cpu_threads=4, num_workers=1)

    binding_rows = [[a.name, a.size, a.sha256] for a in sorted(model_assets, key=lambda item: item.name)]
    ns_sha256 = hashlib.sha256(json.dumps(binding_rows, separators=(",", ":")).encode("ascii")).hexdigest()
    manifest_sha256 = "m" * 64
    generation_hex = "g" * 64

    gen_binding = GenerationBinding(
        generation_hex=generation_hex,
        manifest_sha256=manifest_sha256,
        namespace_sha256=ns_sha256,
        parent_process_guid="p" * 64,
        process_creation_time=123456789,
    )
    controller_channel = GenerationChannel(gen_binding, b"\x11" * 32, "controller")
    worker_channel = GenerationChannel(gen_binding, b"\x11" * 32, "worker")

    bootstrap = WorkerBootstrap(worker_channel, _WorkerRuntimeOwnerProposal, factory_module._OwnedFactoryPortProposal)

    return SimpleNamespace(
        file_data=file_data,
        storage=storage,
        primitives=primitives,
        read_set=read_set,
        pinned=pinned,
        selected_model=selected_model,
        profile=profile,
        gen_binding=gen_binding,
        controller_channel=controller_channel,
        worker_channel=worker_channel,
        bootstrap=bootstrap,
        manifest_sha256=manifest_sha256,
        namespace_sha256=ns_sha256,
    )


# --- Test Suite ---

class RealEngineConnectionContracts(unittest.TestCase):
    """Inert qualification suite for real engine connection and protected ownership."""

    def test_01_authenticated_selection_and_member_mismatch_refused(self):
        """Negative control: manifest validation refuses choice/digest/count mismatches."""
        fix = create_admitted_fixtures()
        selected = fix.selected_model
        members = [
            {"name": a.name, "handle": idx + 10, "identity": {
                "final_path": f"\\\\?\\C:\\models\\{a.name}", "volume_serial": 1,
                "file_id": "01" * 16, "size": a.size, "links": 1, "directory": False
            }, "sha256": a.sha256}
            for idx, a in enumerate(selected.assets)
        ]
        valid_payload = {
            "schema": ADMITTED_FORMAT,
            "choice": selected.choice,
            "manifest_sha256": fix.manifest_sha256,
            "namespace_sha256": fix.namespace_sha256,
            "members": members,
        }

        # Valid payload succeeds
        validated = validate_admitted_manifest(valid_payload, selected, 9999, fix.manifest_sha256)
        self.assertEqual(len(validated), 5)

        # Choice mismatch refuses
        bad_choice = dict(valid_payload, choice="wrong-model")
        with self.assertRaisesRegex(ReadSetRefusal, "admitted_model_choice_mismatch"):
            validate_admitted_manifest(bad_choice, selected, 9999, fix.manifest_sha256)

        # Manifest digest mismatch refuses
        bad_man = dict(valid_payload, manifest_sha256="0" * 64)
        with self.assertRaisesRegex(ReadSetRefusal, "authenticated_manifest_binding"):
            validate_admitted_manifest(bad_man, selected, 9999, fix.manifest_sha256)

        # Member count mismatch (3 files) refuses
        bad_count = dict(valid_payload, members=members[:3])
        with self.assertRaisesRegex(ReadSetRefusal, "member_count_mismatch"):
            validate_admitted_manifest(bad_count, selected, 9999, fix.manifest_sha256)

        # Control handle collision refuses
        with self.assertRaisesRegex(ReadSetRefusal, "unique_inherited_file_handle"):
            validate_admitted_manifest(valid_payload, selected, members[0]["handle"], fix.manifest_sha256)

    def test_02_pre_begin_cancel_admits_no_buffers_or_factory(self):
        """Negative control: pre-begin cancel consumes control frame, resets ready, admits no allocation."""
        fix = create_admitted_fixtures()
        b = fix.bootstrap
        b.bind_admitted_selection(fix.selected_model, fix.profile)

        # Challenge / ready
        ch_frame = fix.controller_channel.encode("challenge", {
            "generation": fix.gen_binding.generation_hex,
            "namespace_sha256": fix.gen_binding.namespace_sha256,
        })
        ready_frame = b.accept_challenge(ch_frame)
        self.assertTrue(b._ready)

        # Send cancel instead of begin
        cancel_frame = fix.controller_channel.encode("cancel", {})
        op = b.accept_initial_control(cancel_frame)
        self.assertEqual(op, "cancel")
        self.assertFalse(b._started)
        self.assertFalse(b._ready)

        # Calling issue_admitted_namespace_lease after cancel refuses
        with self.assertRaises(ProtocolRefusal):
            b.issue_admitted_namespace_lease(fix.pinned, fix.read_set)

    def test_03_copied_or_forged_lease_refused(self):
        """Negative control: forged, duck-typed, or foreign namespace lease is refused."""
        fix = create_admitted_fixtures()
        b = fix.bootstrap
        b.bind_admitted_selection(fix.selected_model, fix.profile)

        ch = fix.controller_channel.encode("challenge", {
            "generation": fix.gen_binding.generation_hex,
            "namespace_sha256": fix.gen_binding.namespace_sha256,
        })
        b.accept_challenge(ch)
        begin = fix.controller_channel.encode("begin", {"manifest_sha256": fix.manifest_sha256})
        b.accept_begin(begin)

        owner = b.registry
        fake_lease = _AdmittedNamespaceLease(
            owner=owner,
            generation=fix.gen_binding,
            read_set=fix.read_set,
            pinned_namespace=fix.pinned,
            buffers=fix.pinned.buffers,
            model=fix.selected_model,
            profile=fix.profile,
            manifest_sha256=fix.manifest_sha256,
            namespace_sha256=fix.namespace_sha256,
            label="uoink-memory-forged",
            active=True,
        )

        with owner.operation(b._permit, "engine"):
            with self.assertRaisesRegex(RuntimeOwnerRefusal, "admitted_namespace_lease_identity"):
                owner.assert_admitted_namespace_binding(fake_lease)

    def test_04_successful_admitted_engine_construction_positive(self):
        """Positive control: authenticated five-file namespace successfully connects to owned ASR engine."""
        fix = create_admitted_fixtures()
        b = fix.bootstrap
        b.bind_admitted_selection(fix.selected_model, fix.profile)

        ch = fix.controller_channel.encode("challenge", {
            "generation": fix.gen_binding.generation_hex,
            "namespace_sha256": fix.gen_binding.namespace_sha256,
        })
        b.accept_challenge(ch)
        begin = fix.controller_channel.encode("begin", {"manifest_sha256": fix.manifest_sha256})
        b.accept_begin(begin)

        # Issue admitted namespace lease
        res_ns = b.issue_admitted_namespace_lease(fix.pinned, fix.read_set)
        self.assertEqual(res_ns, {"issued_admitted_namespace_lease": True})
        lease = b._namespace_lease
        self.assertIsNotNone(lease)

        # Register VAD via factory entry
        fake_vad = object()
        product = SimpleNamespace(vad=fake_vad, active=True)
        b._product = product
        owner = b.registry
        owner._product = product

        policy = _EngineConstructionPolicy(
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
            num_workers=1,
            beam_size=1,
            best_of=1,
            language="en",
            task="transcribe",
        )

        engine = construct_owned_asr_engine(
            b,
            policy,
            whisper_model_cls=FakeWhisperModel,
            tokenizer_cls=FakeTokenizer,
            options_cls=FakeTranscriptionOptions,
            pipeline_cls=FakeFasterWhisperPipeline,
        )

        self.assertIsInstance(engine, OwnedASREngine)
        self.assertTrue(engine.active)
        self.assertIs(engine.model.raw_files_copy is not fix.pinned.buffers, True)
        self.assertEqual(len(fix.pinned.buffers), 5)
        self.assertIn("tokenizer.json", fix.pinned.buffers)
        self.assertIn("preprocessor_config.json", fix.pinned.buffers)

        attempt = owner._engine_attempt
        self.assertIsNotNone(attempt)
        self.assertTrue(attempt.published)
        self.assertIs(attempt.model, engine.model)
        self.assertIs(attempt.pipeline, engine.pipeline)

    def test_05_four_file_model_refused_before_path_service(self):
        """Negative control: four-file model absent preprocessor_config.json is refused."""
        four_files = create_five_file_data()
        del four_files["preprocessor_config.json"]

        fix = create_admitted_fixtures(file_data=four_files)
        b = fix.bootstrap
        b.bind_admitted_selection(fix.selected_model, fix.profile)

        ch = fix.controller_channel.encode("challenge", {
            "generation": fix.gen_binding.generation_hex,
            "namespace_sha256": fix.gen_binding.namespace_sha256,
        })
        b.accept_challenge(ch)
        begin = fix.controller_channel.encode("begin", {"manifest_sha256": fix.manifest_sha256})
        b.accept_begin(begin)

        b.issue_admitted_namespace_lease(fix.pinned, fix.read_set)
        product = SimpleNamespace(vad=object(), active=True)
        b._product = product
        b.registry._product = product

        policy = _EngineConstructionPolicy(beam_size=1, best_of=1)
        with self.assertRaisesRegex(EngineRefusal, "four_file_models_refused_absent_preprocessor"):
            construct_owned_asr_engine(
                b, policy,
                whisper_model_cls=FakeWhisperModel,
                tokenizer_cls=FakeTokenizer,
                options_cls=FakeTranscriptionOptions,
                pipeline_cls=FakeFasterWhisperPipeline,
            )

    def test_06_empty_preprocessor_bytes_refused(self):
        """Negative control: empty preprocessor_config.json bytes refused to prevent B3 path probe."""
        files = create_five_file_data()
        files["preprocessor_config.json"] = b""

        fix = create_admitted_fixtures(file_data=files)
        b = fix.bootstrap
        b.bind_admitted_selection(fix.selected_model, fix.profile)

        ch = fix.controller_channel.encode("challenge", {
            "generation": fix.gen_binding.generation_hex,
            "namespace_sha256": fix.gen_binding.namespace_sha256,
        })
        b.accept_challenge(ch)
        begin = fix.controller_channel.encode("begin", {"manifest_sha256": fix.manifest_sha256})
        b.accept_begin(begin)

        b.issue_admitted_namespace_lease(fix.pinned, fix.read_set)
        product = SimpleNamespace(vad=object(), active=True)
        b._product = product
        b.registry._product = product

        policy = _EngineConstructionPolicy(beam_size=1, best_of=1)
        with self.assertRaisesRegex(EngineRefusal, "nonempty_preprocessor_bytes_required"):
            construct_owned_asr_engine(
                b, policy,
                whisper_model_cls=FakeWhisperModel,
                tokenizer_cls=FakeTokenizer,
                options_cls=FakeTranscriptionOptions,
                pipeline_cls=FakeFasterWhisperPipeline,
            )

    def test_07_missing_or_empty_tokenizer_bytes_refused(self):
        """Negative control: empty tokenizer.json bytes refused to prevent Hub fallback."""
        files = create_five_file_data()
        files["tokenizer.json"] = b""

        fix = create_admitted_fixtures(file_data=files)
        b = fix.bootstrap
        b.bind_admitted_selection(fix.selected_model, fix.profile)

        ch = fix.controller_channel.encode("challenge", {
            "generation": fix.gen_binding.generation_hex,
            "namespace_sha256": fix.gen_binding.namespace_sha256,
        })
        b.accept_challenge(ch)
        begin = fix.controller_channel.encode("begin", {"manifest_sha256": fix.manifest_sha256})
        b.accept_begin(begin)

        b.issue_admitted_namespace_lease(fix.pinned, fix.read_set)
        product = SimpleNamespace(vad=object(), active=True)
        b._product = product
        b.registry._product = product

        policy = _EngineConstructionPolicy(beam_size=1, best_of=1)
        with self.assertRaisesRegex(EngineRefusal, "nonempty_tokenizer_bytes_required"):
            construct_owned_asr_engine(
                b, policy,
                whisper_model_cls=FakeWhisperModel,
                tokenizer_cls=FakeTokenizer,
                options_cls=FakeTranscriptionOptions,
                pipeline_cls=FakeFasterWhisperPipeline,
            )

    def test_08_buffer_mutation_immunity(self):
        """Positive control: constructor popping keys from files dictionary leaves immutable buffers intact."""
        fix = create_admitted_fixtures()
        pinned = fix.pinned
        original_keys = set(pinned.buffers.keys())
        self.assertEqual(len(original_keys), 5)

        fresh_map = pinned.fresh_files_map()
        fresh_map.pop("tokenizer.json")
        fresh_map.pop("preprocessor_config.json")
        self.assertEqual(len(fresh_map), 3)

        # Pinned buffers untouched
        self.assertEqual(len(pinned.buffers), 5)
        self.assertEqual(set(pinned.buffers.keys()), original_keys)

    def test_09_cpu_and_options_policy_mismatch_refused(self):
        """Negative control: non-CPU device, invalid compute_type or beam_size!=1 is refused."""
        with self.assertRaisesRegex(EngineRefusal, "device_policy_cpu_required"):
            _EngineConstructionPolicy(device="cuda")
        with self.assertRaisesRegex(EngineRefusal, "compute_type_policy_required"):
            _EngineConstructionPolicy(compute_type="float16")
        with self.assertRaisesRegex(EngineRefusal, "device_index_zero_required"):
            _EngineConstructionPolicy(device_index=1)
        with self.assertRaisesRegex(EngineRefusal, "beam_and_best_of_one_required"):
            _EngineConstructionPolicy(beam_size=5)
        with self.assertRaisesRegex(EngineRefusal, "beam_and_best_of_one_required"):
            _EngineConstructionPolicy(best_of=5)

    def test_10_revocation_during_construction_retains_returned_objects(self):
        """Negative control: revocation during construction retains model and prevents publication."""
        fix = create_admitted_fixtures()
        b = fix.bootstrap
        b.bind_admitted_selection(fix.selected_model, fix.profile)

        ch = fix.controller_channel.encode("challenge", {
            "generation": fix.gen_binding.generation_hex,
            "namespace_sha256": fix.gen_binding.namespace_sha256,
        })
        b.accept_challenge(ch)
        begin = fix.controller_channel.encode("begin", {"manifest_sha256": fix.manifest_sha256})
        b.accept_begin(begin)

        b.issue_admitted_namespace_lease(fix.pinned, fix.read_set)
        product = SimpleNamespace(vad=object(), active=True)
        b._product = product
        owner = b.registry
        owner._product = product

        class RevokingPipeline(FakeFasterWhisperPipeline):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                # Revoke owner right after pipeline creation
                owner.revoke_generation(b._permit)

        policy = _EngineConstructionPolicy(beam_size=1, best_of=1)
        with self.assertRaisesRegex(RuntimeOwnerRefusal, "owner_revoked"):
            construct_owned_asr_engine(
                b, policy,
                whisper_model_cls=FakeWhisperModel,
                tokenizer_cls=FakeTokenizer,
                options_cls=FakeTranscriptionOptions,
                pipeline_cls=RevokingPipeline,
            )

        attempt = owner._engine_attempt
        self.assertIsNotNone(attempt)
        self.assertIsNotNone(attempt.model)
        self.assertFalse(attempt.active)
        self.assertFalse(attempt.published)

    def test_11_tokenizer_constructor_failure_retains_model(self):
        """Negative control: tokenizer constructor failure retains returned model on attempt."""
        fix = create_admitted_fixtures()
        b = fix.bootstrap
        b.bind_admitted_selection(fix.selected_model, fix.profile)

        ch = fix.controller_channel.encode("challenge", {
            "generation": fix.gen_binding.generation_hex,
            "namespace_sha256": fix.gen_binding.namespace_sha256,
        })
        b.accept_challenge(ch)
        begin = fix.controller_channel.encode("begin", {"manifest_sha256": fix.manifest_sha256})
        b.accept_begin(begin)

        b.issue_admitted_namespace_lease(fix.pinned, fix.read_set)
        product = SimpleNamespace(vad=object(), active=True)
        b._product = product
        owner = b.registry
        owner._product = product

        def failing_tokenizer(*args, **kwargs):
            raise ValueError("simulated_tokenizer_failure")

        policy = _EngineConstructionPolicy(beam_size=1, best_of=1, language="en")
        with self.assertRaisesRegex(ValueError, "simulated_tokenizer_failure"):
            construct_owned_asr_engine(
                b, policy,
                whisper_model_cls=FakeWhisperModel,
                tokenizer_cls=failing_tokenizer,
                options_cls=FakeTranscriptionOptions,
                pipeline_cls=FakeFasterWhisperPipeline,
            )

        attempt = owner._engine_attempt
        self.assertIsNotNone(attempt)
        self.assertIsNotNone(attempt.model)
        self.assertFalse(attempt.active)
        self.assertEqual(str(attempt.failure), "simulated_tokenizer_failure")

    def test_12_pipeline_constructor_failure_retains_model_and_tokenizer(self):
        """Negative control: pipeline constructor failure retains returned model and tokenizer."""
        fix = create_admitted_fixtures()
        b = fix.bootstrap
        b.bind_admitted_selection(fix.selected_model, fix.profile)

        ch = fix.controller_channel.encode("challenge", {
            "generation": fix.gen_binding.generation_hex,
            "namespace_sha256": fix.gen_binding.namespace_sha256,
        })
        b.accept_challenge(ch)
        begin = fix.controller_channel.encode("begin", {"manifest_sha256": fix.manifest_sha256})
        b.accept_begin(begin)

        b.issue_admitted_namespace_lease(fix.pinned, fix.read_set)
        product = SimpleNamespace(vad=object(), active=True)
        b._product = product
        owner = b.registry
        owner._product = product

        def failing_pipeline(*args, **kwargs):
            raise RuntimeError("simulated_pipeline_failure")

        policy = _EngineConstructionPolicy(beam_size=1, best_of=1, language="en")
        with self.assertRaisesRegex(RuntimeError, "simulated_pipeline_failure"):
            construct_owned_asr_engine(
                b, policy,
                whisper_model_cls=FakeWhisperModel,
                tokenizer_cls=FakeTokenizer,
                options_cls=FakeTranscriptionOptions,
                pipeline_cls=failing_pipeline,
            )

        attempt = owner._engine_attempt
        self.assertIsNotNone(attempt)
        self.assertIsNotNone(attempt.model)
        self.assertIsNotNone(attempt.tokenizer)
        self.assertFalse(attempt.active)
        self.assertEqual(str(attempt.failure), "simulated_pipeline_failure")

    def test_13_publication_refusal_after_revocation(self):
        """Negative control: publication refused if revoked during construction."""
        fix = create_admitted_fixtures()
        b = fix.bootstrap
        b.bind_admitted_selection(fix.selected_model, fix.profile)

        ch = fix.controller_channel.encode("challenge", {
            "generation": fix.gen_binding.generation_hex,
            "namespace_sha256": fix.gen_binding.namespace_sha256,
        })
        b.accept_challenge(ch)
        begin = fix.controller_channel.encode("begin", {"manifest_sha256": fix.manifest_sha256})
        b.accept_begin(begin)

        b.issue_admitted_namespace_lease(fix.pinned, fix.read_set)
        product = SimpleNamespace(vad=object(), active=True)
        b._product = product
        owner = b.registry
        owner._product = product

        with owner.operation(b._permit, "engine"):
            attempt = owner._begin_admitted_engine(b._permit, b._namespace_lease, product.vad)
            model = FakeWhisperModel("label", files=fix.pinned.fresh_files_map())
            owner._retain_admitted_engine_model(attempt, model)
            pipeline = FakeFasterWhisperPipeline(model, product.vad)
            owner._retain_admitted_engine_pipeline(attempt, pipeline)

            # Revoke attempt before publication
            attempt.active = False
            with self.assertRaisesRegex(RuntimeOwnerRefusal, "engine_operation_identity"):
                owner._publish_admitted_engine(attempt)

    def test_14_secondary_cleanup_failure_preserves_first_error(self):
        """Negative control: failure during cleanup preserves first error identity with note."""
        fix = create_admitted_fixtures()
        b = fix.bootstrap
        b.bind_admitted_selection(fix.selected_model, fix.profile)

        ch = fix.controller_channel.encode("challenge", {
            "generation": fix.gen_binding.generation_hex,
            "namespace_sha256": fix.gen_binding.namespace_sha256,
        })
        b.accept_challenge(ch)
        begin = fix.controller_channel.encode("begin", {"manifest_sha256": fix.manifest_sha256})
        b.accept_begin(begin)

        b.issue_admitted_namespace_lease(fix.pinned, fix.read_set)
        product = SimpleNamespace(vad=object(), active=True)
        b._product = product
        owner = b.registry
        owner._product = product

        def failing_cleanup(attempt, original):
            raise RuntimeError("cleanup_crash")

        owner._fail_admitted_engine = failing_cleanup

        def failing_model(*args, **kwargs):
            raise TypeError("primary_model_error")

        policy = _EngineConstructionPolicy(beam_size=1, best_of=1)
        with self.assertRaises(TypeError) as ctx:
            construct_owned_asr_engine(
                b, policy,
                whisper_model_cls=failing_model,
                tokenizer_cls=FakeTokenizer,
                options_cls=FakeTranscriptionOptions,
                pipeline_cls=FakeFasterWhisperPipeline,
            )

        self.assertEqual(str(ctx.exception), "primary_model_error")
        # Notes should mention the secondary failure
        notes = getattr(ctx.exception, "__notes__", [])
        self.assertTrue(any("cleanup_crash" in n or "RuntimeError" in n for n in notes))

    def test_15_nested_or_overlapping_operation_refused(self):
        """Negative control: attempting nested operation while engine operation is active refuses."""
        fix = create_admitted_fixtures()
        b = fix.bootstrap
        b.bind_admitted_selection(fix.selected_model, fix.profile)

        ch = fix.controller_channel.encode("challenge", {
            "generation": fix.gen_binding.generation_hex,
            "namespace_sha256": fix.gen_binding.namespace_sha256,
        })
        b.accept_challenge(ch)
        begin = fix.controller_channel.encode("begin", {"manifest_sha256": fix.manifest_sha256})
        b.accept_begin(begin)

        owner = b.registry
        with owner.operation(b._permit, "engine"):
            with self.assertRaisesRegex(RuntimeOwnerRefusal, "operation_already_active"):
                with owner.operation(b._permit, "engine"):
                    pass


if __name__ == "__main__":
    unittest.main()
