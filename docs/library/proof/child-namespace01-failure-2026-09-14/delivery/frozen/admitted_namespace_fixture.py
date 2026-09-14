"""Isolated inert fixture for dormant controller-to-child namespace controls.

Synthetic approval and inert test authority remain strictly fixture-local.
No native DLL calls, live process execution, filesystem I/O or physical port 5179.
"""
from dataclasses import dataclass
import hashlib
import json
import struct
from collections import deque
from threading import RLock

from snapshot_lifecycle import Phase
from inherited_readset import (
    MODEL_MEMBERS,
    AdmittedReadSetAdoption,
    controller_admitted_envelope,
    admitted_envelope_digest,
    expected_admitted_adoption_response,
)
from pinned_buffer_namespace import PinnedBufferNamespace
from owned_generation_protocol import (
    GenerationBinding,
    GenerationChannel,
    WorkerBootstrap,
    ControllerHandshake,
    encode_private_bootstrap,
    decode_private_bootstrap,
    AdmittedNamespaceLease,
    validate_admitted_lease,
)
from asr_loading_adapter import (
    _consume_controller_startup,
    _validate_controller_stage,
)
from worker_runtime_owner import _WorkerRuntimeOwnerProposal
from owned_factory_port import _OwnedFactoryPortProposal

MODEL_SPECS = {
    "tiny": ("openai/whisper-tiny", "main", ("config.json", "generation_config.json", "model.safetensors", "vocabulary.txt")),
    "base": ("openai/whisper-base", "main", ("config.json", "generation_config.json", "model.safetensors", "vocabulary.txt")),
    "small": ("openai/whisper-small", "main", ("config.json", "generation_config.json", "model.safetensors", "vocabulary.txt")),
    "medium": ("openai/whisper-medium", "main", ("config.json", "generation_config.json", "model.safetensors", "vocabulary.txt")),
    "large": ("openai/whisper-large", "main", ("config.json", "generation_config.json", "model.safetensors", "preprocessor_config.json", "vocabulary.json")),
    "large-v3-turbo": ("openai/whisper-large-v3-turbo", "main", ("config.json", "generation_config.json", "model.safetensors", "preprocessor_config.json", "vocabulary.json")),
}


class FakeFileHandle:
    def __init__(self, name, data, volume_serial=1001, file_id=None, raw_handle=None):
        self.name = name
        self.data = data
        self.size = len(data)
        self.volume_serial = volume_serial
        self.file_id = file_id or (hash(name) & 0xFFFFFFFF)
        self.raw = raw_handle or (1000 + (hash(name) % 5000))
        self.closed = False
        self.purpose = "read_member"

    def read_unbuffered(self, offset, length):
        if self.closed:
            raise RuntimeError("handle_closed")
        return self.data[offset:offset + length]

    def close(self):
        self.closed = True


class FakeHandleRecord:
    def __init__(self, name, handle, size, sha256):
        self.name = name
        self.handle = handle
        self.size = size
        self.sha256 = sha256
        self.raw = handle.raw


class FakeReadSet:
    def __init__(self, members):
        self.members = members  # dict or list of FakeHandleRecord
        self.unconfirmed = False

    def namespace_digest(self):
        h = hashlib.sha256()
        if isinstance(self.members, dict):
            items = sorted(self.members.items())
        else:
            items = sorted([(m.name, m) for m in self.members])
        for name, member in items:
            h.update(name.encode("utf-8"))
            h.update(member.sha256.encode("ascii"))
        return h.hexdigest()


class FakeWorker:
    def __init__(self, read_set, creation_time=123456789012):
        self.read_set = read_set
        self.creation_time = creation_time
        self.assigned = True
        self.unconfirmed = False
        self.shutdown_started = False
        self.process = 8888
        self.job = 9999


class FakeApi:
    def __init__(self, handles=None, creation_time=123456789012):
        self.handles = handles or {}
        self.creation_time = creation_time

    def call(self, name, *args):
        if name == "GetCurrentProcess":
            return 8888
        raise NotImplementedError("FakeApi call: " + name)


class FakeWin32Primitives:
    def __init__(self, files_data=None, creation_time=123456789012):
        self.files_data = files_data or {}
        self.creation_time = creation_time
        self.api = FakeApi(creation_time=creation_time)
        self.workers = []
        self.allocated_buffers = []
        self.freed_buffers = []

    def _creation_time(self, process_handle):
        return self.creation_time

    def pin_exact_members(self, member_tuples):
        # member_tuples: list/tuple of (name, size, sha256, data)
        members = {}
        serial = 1001
        for i, item in enumerate(member_tuples):
            name, size, digest, data = item
            handle = FakeFileHandle(name, data, volume_serial=serial, file_id=2000 + i, raw_handle=5000 + i)
            rec = FakeHandleRecord(name, handle, size, digest)
            members[name] = rec
        rs = FakeReadSet(members)
        return rs

    def allocate_page_aligned(self, length):
        buf = bytearray(length)
        self.allocated_buffers.append(buf)
        return buf

    def free_pinned_buffer(self, buf):
        self.freed_buffers.append(buf)


class FakePipePair:
    def __init__(self, material="inert_pipe"):
        self.material = material
        self.read_set = None
        self.quarantined = False
        self.retired = False
        self.c_to_w = deque()
        self.w_to_c = deque()
        self.bootstrap_data = None


class FakePipeController:
    def __init__(self):
        self.clock = lambda: 0.0
        self.pairs = []

    def create_pair(self, material, deadline):
        pair = FakePipePair(material)
        self.pairs.append(pair)
        return pair

    def attach_to_suspended_worker(self, pair, read_set, exe, args, cwd, env):
        worker = FakeWorker(read_set=read_set)
        return worker

    def adopt_inherited_client(self, pair):
        return pair

    def write_bytes(self, pair, data, deadline):
        # From controller perspective, write to c_to_w
        pair.c_to_w.append(data)

    def read_frame(self, pair, deadline):
        if not pair.c_to_w:
            raise RuntimeError("no_frame_available")
        return pair.c_to_w.popleft()

    def read_private_bootstrap(self, pair, deadline):
        if not pair.c_to_w:
            raise RuntimeError("no_bootstrap_available")
        return pair.c_to_w.popleft()

    def _quarantine(self, pair):
        pair.quarantined = True

    def retire_endpoint(self, pair):
        pair.retired = True


class FakePipeClient(FakePipeController):
    def write_bytes(self, pair, data, deadline):
        pair.w_to_c.append(data)

    def read_frame(self, pair, deadline):
        if not pair.c_to_w:
            raise RuntimeError("no_frame_available")
        return pair.c_to_w.popleft()

    def read_private_bootstrap(self, pair, deadline):
        if not pair.c_to_w:
            raise RuntimeError("no_bootstrap_available")
        return pair.c_to_w.popleft()


class FakeRecord:
    def __init__(self, key, protection, permit, owner, selection, profile):
        self.key = key
        self.protection = protection
        self.permit = permit
        self.owner = owner
        self.selection = selection
        self.profile = profile
        self.phase = Phase.NATIVE_RESERVED
        self.worker = None


class FakeManager:
    def __init__(self):
        self._lock = RLock()
        self._records = {}


class FakeSession:
    def __init__(self, record, manager):
        self._record = record
        self._manager = manager
        self._revoked = False
        self._closing = False


class FakePermit:
    def __init__(self, record):
        self.record = record
        self.identity = object()
        self.token = self.identity


class FakeStartup:
    def __init__(self, permit, session, selection, profile):
        self.permit = permit
        self.session = session
        self.selection = selection
        self.profile = profile
        self.model_assets = None


class FakeRelease:
    def __init__(self, manifest_raw, approval, root, profile_id, selection, profile):
        self.manifest_raw = manifest_raw
        self.manifest_approval = approval
        self.root = root
        self.profile_id = profile_id
        self.selection = selection
        self.profile = profile


class FakeApproval:
    def __init__(self, manifest_sha256):
        self.manifest_sha256 = manifest_sha256


class AdmittedFixture:
    """Fixture builder providing complete test environment for 17 controls."""

    def __init__(self, choice="large"):
        self.choice = choice
        self.repo, self.revision, self.member_names = MODEL_SPECS[choice]
        self.primitives = FakeWin32Primitives()

        # Build synthetic member data
        self.member_data = {}
        self.member_tuples = []
        for name in self.member_names:
            content = f"INERT-BUFFER-CONTENT-{choice}-{name}".encode("ascii")
            digest = hashlib.sha256(content).hexdigest()
            self.member_data[name] = (len(content), digest, content)
            self.member_tuples.append((name, len(content), digest, content))

        self.read_set = self.primitives.pin_exact_members(self.member_tuples)

        # Build manifest raw and approval
        models_manifest = [{
            "choice": choice,
            "repo": self.repo,
            "revision": self.revision,
            "manifest_accepted": True,
            "files": [{"path": name, "bytes": len(c), "sha256": d}
                      for name, (l, d, c) in self.member_data.items()]
        }]
        manifest_obj = {
            "schema": "uoink.asr-trusted-manifest.v1",
            "purpose": "real",
            "manifest_accepted": True,
            "models": models_manifest,
        }
        self.manifest_raw = json.dumps(manifest_obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.manifest_sha256 = hashlib.sha256(self.manifest_raw).hexdigest()
        self.approval = FakeApproval(self.manifest_sha256)

        self.selection = {"choice": choice, "repo": self.repo, "revision": self.revision}
        self.profile = {"profile_id": f"inert-profile-{choice}", "device": "cpu", "compute_type": "int8"}
        self.release = FakeRelease(
            self.manifest_raw, self.approval, r"E:\inert\models",
            self.profile["profile_id"], self.selection, self.profile
        )

        self.manager = FakeManager()
        self.record = FakeRecord(
            key="key-001",
            protection=self.read_set,
            permit=None,
            owner=None,
            selection=self.selection,
            profile=self.profile,
        )
        self.permit = FakePermit(self.record)
        self.record.permit = self.permit
        self.session = FakeSession(self.record, self.manager)
        self.record.owner = self.session
        self.manager._records[self.record.key] = self.record

        self.startup = FakeStartup(self.permit, self.session, self.selection, self.profile)

        # Wire communication setup
        self.generation_hex = "a" * 64
        self.child_source_sha256 = "b" * 64
        self.master_key = b"k" * 32
        self.pipe_name_material = "test_pipe_material"

        # In-memory synchronous channel
        self.pipes = FakePipeController()
        self.worker = FakeWorker(read_set=self.read_set)
        self.primitives.workers.append(self.worker)
