"""Generated controller-only fixture; every subject call awaits separate qualification.

The canonical factory, custody, reservation and validation methods stay actual.
Only generated metadata/lower kernel services and explicitly declared transparent
fault seams are installed. No generated transport compatibility is claimed.
"""
from contextlib import ExitStack, contextmanager
import hashlib
import json
from types import SimpleNamespace

import asr_loading_adapter as adapter
import trusted_asr_resolver as resolver
import durable_lifecycle as durable
import snapshot_lifecycle as lifecycle
import snapshot_reservations as reservations
import test_reservations as inherited
from snapshot_reservations import SnapshotSemantics


@contextmanager
def changed(owner, name, value):
    original = getattr(owner, name)
    setattr(owner, name, value)
    try:
        yield
    finally:
        setattr(owner, name, original)


class ControllerBoundaryFixture:
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
                value = ("INERT-STARTUP-" + choice + "-" + name).encode("ascii")
                digest = hashlib.sha256(value).hexdigest()
                assets.append({"path": name, "bytes": len(value), "sha256": digest})
                self.files[str(self.store / choice / revision / name)] = (len(value), digest)
            self.models.append({
                "choice": choice, "repo": repo, "revision": revision,
                "manifest_accepted": True, "files": assets
            })
        raw = json.dumps({
            "schema": "uoink.asr-trusted-manifest.v1", "purpose": "real",
            "manifest_accepted": True, "models": self.models
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.approval = resolver.ManifestApproval("real", hashlib.sha256(raw).hexdigest())
        self.profile = adapter.RuntimeProfile("inert-startup-profile", "cpu", "int8", "inert-vad", None)
        self.release = adapter.ReleaseAuthority(raw, self.approval, self.data_root, self.profile.profile_id)
        creation = self.manager._bindings("unused", "unused", "unused")[3]
        revision = resolver.MODEL_SPECS[self.choice][1]
        self.semantic = SnapshotSemantics(7, "b" * 32, self.choice, revision, self.approval.manifest_sha256)
        self.manager._bindings = lambda *args: (inherited.P, self.semantic, inherited.G, creation)
        self.factory = durable.DurableOwnedRuntimeFactory(self.manager)
        self.admission_reads = 0
        self.on_hash = None
        self.startup = self.session = self.record = self.token = None
        self.custody = self.attempt = self.returned_worker = None
        self.before_create = self.after_bind = self.after_finish = None
        self.stop_error = self.close_error = None
        self.sync_fault_calls = 0
        self.trace = []
        self.stop_workers = []
        self.close_workers = []
        self.cleanup_errors = []
        self.cleanup_attempts = 0
        self.scope_exit_calls = 0
        self.scope_exit_error = None
        self._scope_stack = None
        self._scope_closed = False
        self._create = self.kernel.create_suspended
        self._bind = self.manager._reservations.bind_worker
        self._finish = self.kernel.finish_start
        self._resume = self.kernel.resume
        self._stop = self.kernel.stop_start_failure
        self._close = self.kernel.close_and_join

    def event(self, name, worker=None):
        token = self.token
        self.trace.append({
            "name": name, "worker": worker,
            "manager_locked": self.manager._lock._is_owned(),
            "token_locked": token._lock._is_owned() if token is not None else False,
            "token_phase": token.phase if token is not None else None,
            "pending": token.pending if token is not None else None,
            "resume_attempted": token.resume_attempted if token is not None else None,
        })

    def create_suspended(self, protection, identity, startup):
        self.session = self.record.owner
        self.attempt = self.manager._kernel._factory_starts[identity][0]
        self.event("create_enter")
        if self.before_create is not None:
            self.before_create(self, startup)
        adapter._consume_controller_startup(startup, startup.permit, self.session)
        self.event("consumed")
        worker = self._create(protection, identity, startup)
        self.returned_worker = worker
        self.event("create_return", worker)
        return worker

    def bind_worker(self, token, worker):
        # Declared transparent seam: publication completes in the actual method.
        self._bind(token, worker)
        assert token is self.token and token.phase == "WORKER_BOUND"
        assert token.pending is None and token.worker is worker
        assert self.manager._kernel._starts[self.startup.permit.identity] is worker
        self.event("bind_return", worker)
        if self.after_bind is not None:
            self.after_bind(self, worker)

    def resume(self, worker):
        self.event("resume_enter", worker)
        return self._resume(worker)

    def finish_start(self, worker, identity, startup):
        self.event("finish_enter", worker)
        result = self._finish(worker, identity, startup)
        self.event("finish_return", worker)
        if self.after_finish is not None:
            self.after_finish(self, worker)
        return result

    def stop_start_failure(self, worker):
        self.stop_workers.append(worker)
        self.event("stop_enter", worker)
        if self.stop_error is not None:
            raise self.stop_error
        result = self._stop(worker)
        self.event("stop_return", worker)
        return result

    def close_and_join(self, worker, identity):
        self.close_workers.append(worker)
        self.event("close_enter", worker)
        if self.close_error is not None:
            raise self.close_error
        result = self._close(worker, identity)
        self.event("close_return", worker)
        return result

    def arm_sync_failure(self, error):
        self.event("sync_fault_armed")
        def fail():
            self.sync_fault_calls += 1
            raise error
        self.f.sync_action = fail

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

    def __enter__(self):
        if adapter.resolver is not resolver:
            raise AssertionError("One canonical adapter/resolver family required")
        if (resolver.REAL_APPROVAL is not None
                or any(getattr(adapter, name) is not None for name in
                    ("RELEASE_AUTHORITY", "RUNTIME_PROFILE", "SNAPSHOT_LIFECYCLE",
                     "RUNTIME_FACTORY", "ACQUISITION_SERVICE"))):
            raise AssertionError("Canonical authority must start absent")
        self.stack = ExitStack()
        replacements = (
            (resolver, "REAL_APPROVAL", self.approval),
            (adapter, "RELEASE_AUTHORITY", self.release),
            (adapter, "RUNTIME_PROFILE", self.profile),
            (adapter, "SNAPSHOT_LIFECYCLE", self.manager),
            (adapter, "RUNTIME_FACTORY", self.factory),
            (resolver, "_checked_chain", self.observed),
            (resolver, "_inventory", self.inventory),
            (resolver, "_hash_asset", self.hash_asset),
            (self.kernel, "create_suspended", self.create_suspended),
            (self.manager._reservations, "bind_worker", self.bind_worker),
            (self.kernel, "resume", self.resume),
            (self.kernel, "finish_start", self.finish_start),
            (self.kernel, "stop_start_failure", self.stop_start_failure),
            (self.kernel, "close_and_join", self.close_and_join),
        )
        try:
            for owner, name, value in replacements:
                self.stack.enter_context(changed(owner, name, value))
        except BaseException:
            self.stack.close()
            raise
        return self

    def __exit__(self, *args):
        result = self.stack.__exit__(*args)
        restored = (adapter.resolver is resolver and resolver.REAL_APPROVAL is None
            and all(getattr(adapter, name) is None for name in
                ("RELEASE_AUTHORITY", "RUNTIME_PROFILE", "SNAPSHOT_LIFECYCLE",
                 "RUNTIME_FACTORY", "ACQUISITION_SERVICE")))
        if not restored:
            if isinstance(args[1], BaseException):
                BaseException.add_note(args[1], "Generated fixture authority restoration failed")
            else:
                raise AssertionError("Generated fixture authority restoration failed")
        return result

    @contextmanager
    def scope(self):
        with ExitStack() as owned:
            self._scope_stack = owned
            self._scope_closed = False
            startup = owned.enter_context(adapter._controller_startup_scope(
                self.choice, self.data_root, usage="whisperx", root_kind="transcription"))
            self.startup = startup
            self.record = startup.permit.record
            self.token = self.manager._token(self.record.key)
            self.custody = adapter._CONTROLLER_STARTUPS[id(startup)]
            try:
                yield startup
            finally:
                self._scope_stack = None

    def close_scope_early(self):
        assert self._scope_stack is not None and not self._scope_closed
        self._scope_closed = True
        self.scope_exit_calls += 1
        self.event("lease_exit_enter")
        try:
            self._scope_stack.close()
        except BaseException as original:
            self.scope_exit_error = original
            self.event("lease_exit_error")
            raise
        self.event("lease_exit_return")

    @contextmanager
    def published(self):
        with self.scope() as startup:
            session = None
            primary = None
            try:
                session = self.factory.open_owned_session(startup, startup.permit)
                self.session = session
                self.event("factory_return", self.returned_worker)
                yield startup, session, self.returned_worker
            except BaseException as original:
                primary = original
                raise
            finally:
                if session is not None:
                    self.cleanup_attempts += 1
                    try:
                        if session.close_and_join() is not True:
                            raise lifecycle.CleanupUnconfirmed("Generated session close unconfirmed")
                        self.custody.lease.confirm_native_closed()
                        self.event("native_close_confirmed", self.returned_worker)
                    except BaseException as cleanup_error:
                        self.cleanup_errors.append(cleanup_error)
                        if primary is not None:
                            BaseException.add_note(primary,
                                "Generated fixture cleanup raised: " + type(cleanup_error).__name__)
                        else:
                            raise

