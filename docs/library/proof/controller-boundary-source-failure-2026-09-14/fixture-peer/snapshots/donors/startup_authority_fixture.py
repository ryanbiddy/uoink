"""Inert lower services for proposed startup controls, never a real trust root.

The six-model manifest and its temporary test approval are generated here.
Actual release parsing, admission orchestration, lifecycle, factory and new
startup methods run only if a later guarded qualification is admitted. Lower
filesystem observations and the worker-start service contain no native/file IO.
"""
from contextlib import ExitStack, contextmanager
import hashlib
import json
from types import SimpleNamespace

import startup_fixture_adapter as adapter
import startup_fixture_resolver as resolver
import asr_loading_adapter as canonical_adapter
import trusted_asr_resolver as canonical_resolver
import test_reservations as inherited
from snapshot_reservations import SnapshotSemantics


class StopAtControllerSeam(RuntimeError):
    pass


@contextmanager
def changed(owner, name, value):
    before = getattr(owner, name)
    setattr(owner, name, value)
    try:
        yield
    finally:
        setattr(owner, name, before)


class StartupFixture:
    def __init__(self):
        self.f, self.kernel, self.manager = inherited.ConnectionContracts().setup()
        self.choice = "large"
        self.data_root = r"E:\uoink-inert-startup"
        self.store = adapter.Path(self.data_root) / "model_assets" / "asr"
        self.models = []
        self.files = {}
        for choice, (repo, revision, names) in resolver.MODEL_SPECS.items():
            assets = []
            for name in names:
                # Metadata about generated placeholder bytes only. No model
                # bytes are opened, allocated as tensors or treated as acquired.
                value = ("INERT-STARTUP-" + choice + "-" + name).encode("ascii")
                digest = hashlib.sha256(value).hexdigest()
                assets.append({"path": name, "bytes": len(value), "sha256": digest})
                self.files[str(self.store / choice / revision / name)] = (len(value), digest)
            self.models.append({"choice": choice, "repo": repo, "revision": revision,
                                "manifest_accepted": True, "files": assets})
        raw = json.dumps({"schema": "uoink.asr-trusted-manifest.v1", "purpose": "real",
                          "manifest_accepted": True, "models": self.models},
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.approval = resolver.ManifestApproval("real", hashlib.sha256(raw).hexdigest())
        self.profile = adapter.RuntimeProfile("inert-startup-profile", "cpu", "int8", "inert-vad", None)
        self.release = adapter.ReleaseAuthority(raw, self.approval, self.data_root, self.profile.profile_id)
        creation = self.manager._bindings("unused", "unused", "unused")[3]
        revision = resolver.MODEL_SPECS[self.choice][1]
        self.semantic = SnapshotSemantics(7, "b" * 32, self.choice, revision, self.approval.manifest_sha256)
        self.manager._bindings = lambda *args: (inherited.P, self.semantic, inherited.G, creation)
        self.factory = adapter.DurableOwnedRuntimeFactory(self.manager)
        self.admission_reads = 0
        self.after_acquire = self.on_hash = self.on_start = None
        self.startup = self.session = None
        self.stop = StopAtControllerSeam("inert stop at controller seam")
        inherited_acquire = self.kernel.acquire_read
        def acquire(key):
            result = inherited_acquire(key)
            if self.after_acquire is not None:
                self.after_acquire()
            return result
        self.kernel.acquire_read = acquire
        self.kernel.create_suspended = self.enter_start_service

    def observed(self, path, *, directory):
        path = str(path)
        if directory:
            allowed = {str(self.store)} | {str(self.store / m["choice"] / m["revision"]) for m in self.models}
            if path not in allowed:
                raise AssertionError("unexpected inert directory")
            size, mode = 0, 0o040700
        else:
            if path not in self.files:
                raise AssertionError("unexpected inert asset")
            size, _ = self.files[path]
            mode = 0o100600
        identity = int(hashlib.sha256(path.encode("utf-8")).hexdigest()[:12], 16)
        return SimpleNamespace(st_dev=7, st_ino=identity, st_mode=mode, st_nlink=1,
                               st_size=size, st_mtime_ns=10, st_ctime_ns=11, st_birthtime_ns=12)

    def inventory(self, snapshot, expected):
        actual = {adapter.Path(path).name for path in self.files if adapter.Path(path).parent == snapshot}
        if actual != set(expected):
            raise AssertionError("inert inventory mismatch")

    def hash_asset(self, path, asset, synthetic, started):
        self.admission_reads += 1
        if synthetic is not False or self.files[str(path)] != (asset.size, asset.sha256):
            raise AssertionError("inert asset metadata mismatch")
        if self.on_hash is not None:
            self.on_hash(self.admission_reads)
        identity = resolver._identity(self.observed(path, directory=False))
        return resolver.FileObservation(asset.name, asset.size, asset.sha256, identity, identity)

    def enter_start_service(self, protection, identity, startup):
        record = startup.permit.record
        if protection is not self.kernel.protection or identity is not startup.permit.identity:
            raise AssertionError("foreign inert start inputs")
        self.startup, self.session = startup, record.owner
        self.f.events.append("controller_start_service")
        if self.on_start is not None:
            return self.on_start(startup, self.session)
        raise self.stop

    def __enter__(self):
        if (adapter is canonical_adapter or resolver is canonical_resolver
                or adapter._STARTUP_RESOLVER is not resolver or adapter.resolver is not resolver
                or canonical_adapter.resolver is not canonical_resolver
                or canonical_resolver.REAL_APPROVAL is not None
                or any(getattr(canonical_adapter, name) is not None for name in
                    ("RELEASE_AUTHORITY", "RUNTIME_PROFILE", "SNAPSHOT_LIFECYCLE", "RUNTIME_FACTORY", "ACQUISITION_SERVICE"))):
            raise AssertionError("separately loaded inert startup pair required")
        self.stack = ExitStack()
        values = ((resolver, "REAL_APPROVAL", self.approval),
                  (adapter, "RELEASE_AUTHORITY", self.release),
                  (adapter, "RUNTIME_PROFILE", self.profile),
                  (adapter, "SNAPSHOT_LIFECYCLE", self.manager),
                  (adapter, "RUNTIME_FACTORY", self.factory),
                  (resolver, "_checked_chain", self.observed),
                  (resolver, "_inventory", self.inventory),
                  (resolver, "_hash_asset", self.hash_asset))
        try:
            for owner, name, value in values:
                self.stack.enter_context(changed(owner, name, value))
        except BaseException:
            self.stack.close()
            raise
        return self

    def __exit__(self, *args):
        result = self.stack.__exit__(*args)
        restored = (resolver.REAL_APPROVAL is None and canonical_resolver.REAL_APPROVAL is None
            and all(getattr(module, name) is None for module in (adapter, canonical_adapter)
                for name in ("RELEASE_AUTHORITY", "RUNTIME_PROFILE", "SNAPSHOT_LIFECYCLE", "RUNTIME_FACTORY", "ACQUISITION_SERVICE")))
        if not restored:
            if isinstance(args[1], BaseException):
                BaseException.add_note(args[1], "Inert startup fixture authority restoration failed")
            else:
                raise AssertionError("inert startup fixture authority restoration failed")
        return result

    def scope(self):
        return adapter._controller_startup_scope(self.choice, self.data_root,
                                                usage="whisperx", root_kind="transcription")

    @contextmanager
    def issued(self):
        # Deliberately leave the reserved seam by an exact sentinel. This helper
        # does not manufacture successful teardown for an unstarted real route.
        try:
            with self.scope() as startup:
                self.startup = startup
                yield startup
                raise self.stop
        except StopAtControllerSeam as error:
            if error is not self.stop:
                raise

    def custody(self, startup=None):
        return adapter._CONTROLLER_STARTUPS[id(startup or self.startup)]
