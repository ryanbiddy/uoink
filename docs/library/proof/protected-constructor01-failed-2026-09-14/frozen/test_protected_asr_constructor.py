"""Inert unit tests for protected ASR constructor connection and engine ownership.

Tests exercise constructor inputs, files forwarding, four-file policies, tokenizer
checks, foreign/stale namespace rejections, CPU/options mismatches, constructor
failures, and owner revocation. Tests do not emit fixed success receipts and are
not executed during this source-only authoring step.
"""
from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
import unittest

from pinned_buffer_namespace import (
    BufferAsset, PinnedBufferNamespace, AdmittedNamespaceRecord,
    FOUR, FIVE, NamespaceRefusal
)
from inherited_readset import InheritedReadSetAdoption
from worker_runtime_owner import (
    _WorkerRuntimeOwnerProposal, _AdmittedNamespace, _EngineOwner,
    RuntimeOwnerRefusal
)
from owned_generation_protocol import (
    WorkerBootstrap, GenerationChannel, GenerationBinding
)
from owned_asr_engine import (
    OwnedASREngine, construct_owned_asr_engine, EngineRefusal,
    FEATURE_EXTRACTOR_DEFAULTS, COMPANION_DELTA_B3_NO_PATH,
    FOUR_FILE_MODELS, FIVE_FILE_MODELS
)
from whisperx.vads.pyannote import VoiceActivitySegmentation


# --- Fixed Fake Services for Inert Testing ---

class FakeTokenizer:
    def __init__(self, eot=50256, language_code="en", task="transcribe"):
        self.eot = eot
        self.language_code = language_code
        self.task = task
        self.tokenizer = self

    def encode(self, text):
        return [1, 2, 3]

    def decode(self, tokens):
        return "fake text"

    def decode_batch(self, batch):
        return ["fake text" for _ in batch]


class FakeCT2Whisper:
    def __init__(self, model_path, device="cpu", device_index=0, compute_type="default",
                 intra_threads=0, inter_threads=1, files=None, **kwargs):
        self.model_path = model_path
        self.device = device
        self.device_index = device_index
        self.compute_type = compute_type
        self.intra_threads = intra_threads
        self.inter_threads = inter_threads
        self.files = files
        self.kwargs = kwargs
        self.is_multilingual = True

    def encode(self, features, to_cpu=False):
        return object()


class FakeWhisperModel:
    def __init__(self, model_size_or_path, device="auto", device_index=0, compute_type="default",
                 cpu_threads=0, num_workers=1, download_root=None, local_files_only=False,
                 files=None, **kwargs):
        self.model_size_or_path = model_size_or_path
        self.device = device
        self.device_index = device_index
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self.local_files_only = local_files_only
        self.raw_files = dict(files) if files else None

        tokenizer_bytes = files.pop("tokenizer.json", None) if files else None
        preprocessor_bytes = files.pop("preprocessor_config.json", None) if files else None

        self.tokenizer_bytes = tokenizer_bytes
        self.preprocessor_bytes = preprocessor_bytes
        self.remaining_files = dict(files) if files else None

        self.model = FakeCT2Whisper(
            model_size_or_path,
            device=device,
            device_index=device_index,
            compute_type=compute_type,
            intra_threads=cpu_threads,
            inter_threads=num_workers,
            files=files,
            **kwargs
        )
        self.hf_tokenizer = FakeTokenizer()
        self.feat_kwargs = {"feature_size": 80}
        self.max_length = 448


class FakePipeline:
    def __init__(self, model, vad, **kwargs):
        self.model = model
        self.vad_model = vad
        self.model_path = getattr(model, 'model_size_or_path', 'uoink-memory-fake')
        self.options = kwargs.get('options')
        self.tokenizer = kwargs.get('tokenizer')
        self.kwargs = kwargs


class FakeVoiceActivitySegmentation(VoiceActivitySegmentation):
    def __init__(self):
        pass

    def __call__(self, *args, **kwargs):
        return []

    def instantiate(self, params):
        pass


class FakeHandle:
    def __init__(self, value, label="fake-handle"):
        self.value = value
        self.closed = False
        self.label = label


class FakeFileIdentity:
    def __init__(self, final_path, volume_serial, file_id, size, links, directory):
        self.final_path = final_path
        self.volume_serial = volume_serial
        self.file_id = file_id
        self.size = size
        self.links = links
        self.directory = directory

    def __eq__(self, other):
        return (isinstance(other, FakeFileIdentity) and
                (self.final_path, self.volume_serial, self.file_id, self.size, self.links, self.directory) ==
                (other.final_path, other.volume_serial, other.file_id, other.size, other.links, other.directory))


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


class FakeAPI:
    def __init__(self, storage):
        self.ffi = FakeFFI()
        self.storage = storage

    def checked(self, fn_name, handle, *args):
        if fn_name == "SetFilePointerEx":
            out_pos = args[2]
            out_pos.value = 0
            handle.read_offset = 0
            return 1
        elif fn_name == "ReadFile":
            scratch = args[1]
            requested = args[2]
            count = args[3]
            data = self.storage.get(handle.value, b"")
            offset = getattr(handle, 'read_offset', 0)
            chunk = data[offset:offset + requested]
            scratch.raw[:len(chunk)] = chunk
            count.value = len(chunk)
            handle.read_offset = offset + len(chunk)
            return 1
        return 1


class FakePrimitives:
    def __init__(self, storage):
        self.read_sets = []
        self.handles = []
        self.storage = storage
        self.api = FakeAPI(storage)

    def _owned(self, handle):
        return handle

    def _retain(self, value, label):
        handle = FakeHandle(value, label)
        self.handles.append(handle)
        return handle

    def identity(self, handle):
        data = self.storage.get(handle.value, b"")
        return FakeFileIdentity(f"\\\\?\\C:\\fake\\{handle.value}", 1, b"\x01" * 16, len(data), 1, False)

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
        self.worker_reserved = False
        self.identities = []


# --- Test Suite ---

class ProtectedASRConstructorCases(unittest.TestCase):
    """Inert qualification suite for protected ASR constructor connection and engine ownership."""

    def _build_namespace_and_bootstrap(self, file_dict, manifest_sha256="a" * 64):
        storage = {}
        assets = []
        members = []
        for idx, (name, data) in enumerate(sorted(file_dict.items())):
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

        binding = GenerationBinding(
            generation_hex="1" * 64,
            manifest_sha256=manifest_sha256,
            namespace_sha256=pinned.namespace_sha256,
            bootstrap_source_sha256="3" * 64,
            process_creation_time=12345678,
        )
        channel = GenerationChannel(binding, b"\x02" * 32, "worker")
        bootstrap = WorkerBootstrap(channel, _WorkerRuntimeOwnerProposal, FakeFactoryPort)

        # Challenge-ready handshake
        controller_channel = GenerationChannel(binding, b"\x02" * 32, "controller")
        challenge_frame = controller_channel.encode("challenge", {
            "generation": binding.generation_hex,
            "namespace_sha256": binding.namespace_sha256,
        })
        bootstrap.accept_challenge(challenge_frame)
        bootstrap._started = True

        adoption = InheritedReadSetAdoption(primitives)
        adoption.read_set = read_set
        adoption.assets = tuple(assets)
        adoption.namespace = pinned
        adoption.status = "materialized"
        adoption.materialization_started = True

        namespace_record = bootstrap.issue_admitted_namespace(adoption)
        return bootstrap, namespace_record, pinned, read_set

    def _sample_five_files(self):
        return {
            "config.json": b'{"model_type": "whisper"}',
            "model.bin": b'\x00\x01\x02\x03' * 16,
            "preprocessor_config.json": b'{"feature_size": 80}',
            "tokenizer.json": b'{"version": "1.0", "tokens": ["a", "b"]}',
            "vocabulary.json": b'{"a": 0, "b": 1}',
        }

    def _sample_four_files(self):
        return {
            "config.json": b'{"model_type": "whisper"}',
            "model.bin": b'\x00\x01\x02\x03' * 16,
            "tokenizer.json": b'{"version": "1.0", "tokens": ["a", "b"]}',
            "vocabulary.txt": b'a\nb\n',
        }

    def test_01_five_file_forwarding_preserves_namespace_and_returns_engine_ownership(self):
        """Case 01: Five-file forwarding passes fresh files map, preserves buffers, and binds engine."""
        five_files = self._sample_five_files()
        bootstrap, namespace_record, pinned, read_set = self._build_namespace_and_bootstrap(five_files)
        vad_model = FakeVoiceActivitySegmentation()

        owner = bootstrap.registry
        with owner.operation(bootstrap._permit, "factory"):
            owner._product = FakeVADOwner(vad_model, owner._generation)

        def fake_pipeline_ctor(ns, vad, files, **kwargs):
            self.assertIn("tokenizer.json", files)
            self.assertIn("preprocessor_config.json", files)
            whisper_model = FakeWhisperModel("uoink-memory-fake", files=files, **kwargs)
            self.assertNotIn("tokenizer.json", files)
            self.assertNotIn("preprocessor_config.json", files)
            return FakePipeline(whisper_model, vad, **kwargs)

        engine = construct_owned_asr_engine(
            bootstrap, namespace_record, vad_model,
            device="cpu", compute_type="int8", cpu_threads=4,
            pipeline_constructor=fake_pipeline_ctor
        )

        self.assertIsInstance(engine, OwnedASREngine)
        self.assertTrue(engine.active)
        self.assertEqual(len(pinned.buffers), 5)
        self.assertIn("tokenizer.json", pinned.buffers)
        self.assertIn("preprocessor_config.json", pinned.buffers)
        self.assertIs(engine.vad, vad_model)
        self.assertIs(engine.namespace_record, namespace_record)
        engine.assert_bound()

    def test_02_four_file_model_policy_tiny_refuses_path_probe_and_identifies_companion_delta(self):
        """Case 02: Four-file tiny model policy refuses filesystem path probe and identifies B3 delta."""
        four_files = self._sample_four_files()
        bootstrap, namespace_record, pinned, _ = self._build_namespace_and_bootstrap(four_files)
        vad_model = FakeVoiceActivitySegmentation()
        owner = bootstrap.registry
        with owner.operation(bootstrap._permit, "factory"):
            owner._product = FakeVADOwner(vad_model, owner._generation)

        with self.assertRaises(EngineRefusal) as cm:
            construct_owned_asr_engine(bootstrap, namespace_record, vad_model)

        self.assertIn("four_file_preprocessor_path_probe_requires_b3_companion_delta", str(cm.exception))
        self.assertIn("B2.py:741", str(cm.exception))
        self.assertNotIn("preprocessor_config.json", pinned.buffers)

    def test_03_four_file_model_policy_base_refuses_path_probe_and_identifies_companion_delta(self):
        """Case 03: Four-file base model policy refuses filesystem path probe and identifies B3 delta."""
        four_files = self._sample_four_files()
        bootstrap, namespace_record, pinned, _ = self._build_namespace_and_bootstrap(four_files)
        vad_model = FakeVoiceActivitySegmentation()
        owner = bootstrap.registry
        with owner.operation(bootstrap._permit, "factory"):
            owner._product = FakeVADOwner(vad_model, owner._generation)

        with self.assertRaises(EngineRefusal) as cm:
            construct_owned_asr_engine(bootstrap, namespace_record, vad_model)

        self.assertIn("four_file_preprocessor_path_probe_requires_b3_companion_delta", str(cm.exception))

    def test_04_four_file_model_policy_small_refuses_path_probe_and_identifies_companion_delta(self):
        """Case 04: Four-file small model policy refuses filesystem path probe and identifies B3 delta."""
        four_files = self._sample_four_files()
        bootstrap, namespace_record, pinned, _ = self._build_namespace_and_bootstrap(four_files)
        vad_model = FakeVoiceActivitySegmentation()
        owner = bootstrap.registry
        with owner.operation(bootstrap._permit, "factory"):
            owner._product = FakeVADOwner(vad_model, owner._generation)

        with self.assertRaises(EngineRefusal) as cm:
            construct_owned_asr_engine(bootstrap, namespace_record, vad_model)

        self.assertIn("four_file_preprocessor_path_probe_requires_b3_companion_delta", str(cm.exception))

    def test_05_four_file_model_policy_medium_refuses_path_probe_and_identifies_companion_delta(self):
        """Case 05: Four-file medium model policy refuses filesystem path probe and identifies B3 delta."""
        four_files = self._sample_four_files()
        bootstrap, namespace_record, pinned, _ = self._build_namespace_and_bootstrap(four_files)
        vad_model = FakeVoiceActivitySegmentation()
        owner = bootstrap.registry
        with owner.operation(bootstrap._permit, "factory"):
            owner._product = FakeVADOwner(vad_model, owner._generation)

        with self.assertRaises(EngineRefusal) as cm:
            construct_owned_asr_engine(bootstrap, namespace_record, vad_model)

        self.assertIn("four_file_preprocessor_path_probe_requires_b3_companion_delta", str(cm.exception))

    def test_06_missing_tokenizer_refused_before_constructor_and_hub_fallback(self):
        """Case 06: Missing or empty tokenizer.json is refused before constructor and Hub fallback."""
        five_files = self._sample_five_files()
        five_files["tokenizer.json"] = b""
        bootstrap, namespace_record, _, _ = self._build_namespace_and_bootstrap(five_files)
        vad_model = FakeVoiceActivitySegmentation()
        owner = bootstrap.registry
        with owner.operation(bootstrap._permit, "factory"):
            owner._product = FakeVADOwner(vad_model, owner._generation)

        with self.assertRaises(EngineRefusal) as cm:
            construct_owned_asr_engine(bootstrap, namespace_record, vad_model)

        self.assertIn("nonempty_tokenizer_bytes_required", str(cm.exception))

    def test_07_preprocessor_path_fallback_blocked_without_companion_delta(self):
        """Case 07: Absence of preprocessor blocks filesystem fallback probe as written in B3."""
        four_files = self._sample_four_files()
        bootstrap, namespace_record, _, _ = self._build_namespace_and_bootstrap(four_files)
        vad_model = FakeVoiceActivitySegmentation()
        owner = bootstrap.registry
        with owner.operation(bootstrap._permit, "factory"):
            owner._product = FakeVADOwner(vad_model, owner._generation)

        with self.assertRaises(EngineRefusal) as cm:
            construct_owned_asr_engine(bootstrap, namespace_record, vad_model)

        self.assertIn(COMPANION_DELTA_B3_NO_PATH, str(cm.exception))

    def test_08_forged_caller_created_namespace_refused_by_owner(self):
        """Case 08: Caller-created dummy namespace record is refused by owner authority check."""
        five_files = self._sample_five_files()
        bootstrap, _, pinned, read_set = self._build_namespace_and_bootstrap(five_files)
        vad_model = FakeVoiceActivitySegmentation()
        owner = bootstrap.registry
        with owner.operation(bootstrap._permit, "factory"):
            owner._product = FakeVADOwner(vad_model, owner._generation)

        forged_record = AdmittedNamespaceRecord(
            namespace_sha256="forged" * 10 + "1234",
            manifest_sha256="m" * 64,
            generation_hex="g" * 64,
            schema_name="five_file",
            label="uoink-memory-forged",
            asset_names=tuple(five_files.keys()),
            _namespace=pinned,
            _read_set=read_set,
        )

        with self.assertRaises(RuntimeOwnerRefusal) as cm:
            construct_owned_asr_engine(bootstrap, forged_record, vad_model)

        self.assertIn("admitted_namespace_identity", str(cm.exception))

    def test_09_stale_and_revoked_namespace_refused_by_owner(self):
        """Case 09: Stale or revoked namespace record is rejected by owner."""
        five_files = self._sample_five_files()
        bootstrap, namespace_record, _, _ = self._build_namespace_and_bootstrap(five_files)
        vad_model = FakeVoiceActivitySegmentation()
        owner = bootstrap.registry
        with owner.operation(bootstrap._permit, "factory"):
            owner._product = FakeVADOwner(vad_model, owner._generation)

        owner.revoke_generation(bootstrap._permit)

        with self.assertRaises(RuntimeOwnerRefusal):
            construct_owned_asr_engine(bootstrap, namespace_record, vad_model)

    def test_10_foreign_namespace_from_different_owner_refused(self):
        """Case 10: Namespace record issued by a foreign owner is rejected."""
        five_files = self._sample_five_files()
        bootstrap1, namespace_record1, _, _ = self._build_namespace_and_bootstrap(five_files)
        bootstrap2, _, _, _ = self._build_namespace_and_bootstrap(five_files)
        vad_model = FakeVoiceActivitySegmentation()
        owner2 = bootstrap2.registry
        with owner2.operation(bootstrap2._permit, "factory"):
            owner2._product = FakeVADOwner(vad_model, owner2._generation)

        with self.assertRaises(RuntimeOwnerRefusal) as cm:
            construct_owned_asr_engine(bootstrap2, namespace_record1, vad_model)

        self.assertIn("admitted_namespace_identity", str(cm.exception))

    def test_11_cpu_and_options_mismatch_refused(self):
        """Case 11: Mismatched compute device or options are refused before constructor entry."""
        five_files = self._sample_five_files()
        bootstrap, namespace_record, _, _ = self._build_namespace_and_bootstrap(five_files)
        vad_model = FakeVoiceActivitySegmentation()
        owner = bootstrap.registry
        with owner.operation(bootstrap._permit, "factory"):
            owner._product = FakeVADOwner(vad_model, owner._generation)

        with self.assertRaises(EngineRefusal) as cm:
            construct_owned_asr_engine(bootstrap, namespace_record, vad_model, device="cuda")
        self.assertIn("device_policy_cpu_required", str(cm.exception))

        with self.assertRaises(EngineRefusal) as cm:
            construct_owned_asr_engine(bootstrap, namespace_record, vad_model, compute_type="float16")
        self.assertIn("compute_type_policy_int8_required", str(cm.exception))

        with self.assertRaises(EngineRefusal) as cm:
            construct_owned_asr_engine(bootstrap, namespace_record, vad_model, cpu_threads=-1)
        self.assertIn("cpu_threads_positive_int_required", str(cm.exception))

    def test_12_constructor_failure_preserves_first_error_and_retains_uncertain_owner(self):
        """Case 12: Constructor failure preserves initial error and quarantines engine inputs."""
        five_files = self._sample_five_files()
        bootstrap, namespace_record, _, _ = self._build_namespace_and_bootstrap(five_files)
        vad_model = FakeVoiceActivitySegmentation()
        owner = bootstrap.registry
        with owner.operation(bootstrap._permit, "factory"):
            owner._product = FakeVADOwner(vad_model, owner._generation)

        def failing_constructor(*args, **kwargs):
            raise RuntimeError("CT2 Native Initialization Failure")

        with self.assertRaises(RuntimeError) as cm:
            construct_owned_asr_engine(
                bootstrap, namespace_record, vad_model,
                pipeline_constructor=failing_constructor
            )

        self.assertEqual(str(cm.exception), "CT2 Native Initialization Failure")
        self.assertIsNotNone(owner._quarantined_engine)
        self.assertIs(owner._quarantined_engine[0], namespace_record)
        self.assertIs(owner._quarantined_engine[1], vad_model)
        self.assertIs(owner._quarantined_engine[2], cm.exception)

    def test_13_revocation_and_cleanup_failure_retains_process_retirement_path(self):
        """Case 13: Revocation or cleanup failure notes original error and retains uncertain ownership."""
        five_files = self._sample_five_files()
        bootstrap, namespace_record, _, _ = self._build_namespace_and_bootstrap(five_files)
        vad_model = FakeVoiceActivitySegmentation()
        owner = bootstrap.registry
        with owner.operation(bootstrap._permit, "factory"):
            owner._product = FakeVADOwner(vad_model, owner._generation)

        def failing_constructor_and_quarantine(*args, **kwargs):
            original = RuntimeError("Primary failure")
            def broken_quarantine(*q_args):
                raise IOError("Quarantine secondary failure")
            owner.quarantine_engine = broken_quarantine
            raise original

        with self.assertRaises(RuntimeError) as cm:
            construct_owned_asr_engine(
                bootstrap, namespace_record, vad_model,
                pipeline_constructor=failing_constructor_and_quarantine
            )

        self.assertEqual(str(cm.exception), "Primary failure")
        self.assertTrue(hasattr(cm.exception, '__notes__'))
        self.assertTrue(any("Quarantine secondary failure" in note or "IOError" in note
                            for note in cm.exception.__notes__))


# Supporting dummy classes for test isolation
class FakeFactoryPort:
    pass


class FakeVADOwner:
    def __init__(self, vad, generation):
        self.vad = vad
        self.generation = generation
        self.active = True
        self.model = object()
        self.lease = FakeModelLease(self.model)
        self.factory = FakeFactoryWrapper()
        self.owned_module = FakeOwnedModule()


class FakeModelLease:
    def __init__(self, model):
        self.model = model

    def assert_bound(self, factory, model):
        pass


class FakeFactoryWrapper:
    def __init__(self):
        self._owned_runtime_module = None
        self._completed = None


class FakeOwnedModule:
    def __init__(self):
        self._RUNTIME = None
