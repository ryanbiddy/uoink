"""Source-only cleanup repair and focused-case setup; no candidate execution."""
from pathlib import Path
import ast
import difflib
import hashlib
import json

HERE = Path(__file__).resolve().parent
BEFORE = HERE / "before-cleanup-review01"
BEFORE.mkdir(exist_ok=False)
for name in ("asr_loading_adapter.py", "connection_cases.py"):
    (BEFORE / name).write_bytes((HERE / name).read_bytes())
old = (HERE / "asr_loading_adapter.py").read_text()
assert hashlib.sha256(old.encode()).hexdigest() == "73a0100e36a4ec8e4f75f8dd02065ecc79d1312ebad4ff5798edce4734a9f24a"
new = old
assert new.count('    stack = ExitStack()\n    try:\n') == 1
new = new.replace('    stack = ExitStack()\n    try:\n',
                  '    # Forward the primary exception to the concrete lease on exit;\n'
                  '    # ExitStack.close() would discard that exception context.\n'
                  '    with ExitStack() as stack:\n')
assert new.count('        yield authority, lease, admission\n    finally:\n        stack.close()\n') == 1
new = new.replace('        yield authority, lease, admission\n    finally:\n        stack.close()\n', '        yield authority, lease, admission\n')
assert new.count('        runtime = None\n        try:\n') == 1
new = new.replace('        runtime = None\n        try:\n', '        runtime = None\n        primary_error = None\n        try:\n')
before = '''            yield operations
        finally:
            if runtime is None or runtime.close_and_join() is not True:
                raise NativeCleanupUnconfirmed("Native cleanup unconfirmed; snapshot lease must remain quarantined")
            lease.confirm_native_closed()
'''
after = '''            yield operations
        except BaseException as error:
            primary_error = error
            raise
        finally:
            try:
                if runtime is None or runtime.close_and_join() is not True:
                    raise NativeCleanupUnconfirmed("Native cleanup unconfirmed; snapshot lease must remain quarantined")
                lease.confirm_native_closed()
            except BaseException as cleanup_error:
                if primary_error is None:
                    raise
                BaseException.add_note(primary_error, "Owned ASR cleanup remains unconfirmed: " + type(cleanup_error).__name__)
                # Preserve the first error. The outer exception-aware lease
                # exit retains/quarantines the still-unconfirmed reservation.
'''
assert new.count(before) == 1
new = new.replace(before, after)
ast.parse(new, filename="asr_loading_adapter.py")
(HERE / "asr_loading_adapter.py").write_bytes(new.encode())
(HERE / "adapter-cleanup-review01.diff").write_text("".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
    fromfile="before/asr_loading_adapter.py", tofile="after/asr_loading_adapter.py")), encoding="utf-8", newline="\n")
old_cases = (HERE / "connection_cases.py").read_text()
cases = old_cases
cases = cases.replace('rebind_failure_never_starts_owned_worker', 'binding_or_start_failure_preserves_original_and_quarantine')
needle = '            self.rig.observed_permit, self.rig.startup = permit, profile\n'
assert cases.count(needle) == 1
cases = cases.replace(needle, needle + '            if self.rig.fault == "start":\n                raise self.rig.start_error\n')
needle = '            self.startup = self.observed_permit = None\n'
assert cases.count(needle) == 1
cases = cases.replace(needle, needle + '            self.binding_error = real_resolver.AdmissionRefusal("inert rebind refused")\n'
                                      '            self.start_error = RuntimeError("inert startup refused")\n')
cases = cases.replace('                raise real_resolver.AdmissionRefusal("inert rebind refused")', '                raise self.binding_error')
start = cases.index('        @contextmanager\n        def leased(')
end = cases.index('        def __enter__(self):', start)
cases = cases[:start] + '''        def release_policy(self, choice, caller_root, *, root_kind):
            assert choice == "base" and root_kind in ("transcription", "reliability")
            # This visible seam bypasses only the closed real authority check.
            # The actual _leased_admission and concrete lifecycle still run.
            return self.authority, object(), SimpleNamespace(revision=revision), store, snapshot

        def admit(self, trusted, choice, given_store, given_snapshot):
            assert choice == "base" and given_store == store and given_snapshot == snapshot
            assert self.record().phase is lifecycle.Phase.PROTECTED
            return self.admission

''' + cases[end:]
cases = cases.replace('                "_leased_admission": self.leased,\n                "resolver": SimpleNamespace(LocalBinding=real_resolver.LocalBinding, bind_for_constructor=self.bind),',
    '                "_release": self.release_policy,\n'
    '                "resolver": SimpleNamespace(LocalBinding=real_resolver.LocalBinding, bind_for_constructor=self.bind,\n'
    '                    admit_snapshot=self.admit, AdmissionRefusal=real_resolver.AdmissionRefusal),')
start = cases.index('    def binding_or_start_failure_preserves_original_and_quarantine():')
end = cases.index('    def unconfirmed_close_keeps_snapshot_quarantined():', start)
cases = cases[:start] + '''    def binding_or_start_failure_preserves_original_and_quarantine():
        for fault in ("rebind", "start"):
            with Rig(fault) as rig:
                expected = rig.binding_error if fault == "rebind" else rig.start_error
                actual = expect(type(expected), lambda: enter(rig.context()))
                assert actual is expected
                assert any("NativeCleanupUnconfirmed" in note for note in actual.__notes__)
                assert rig.record().phase is lifecycle.Phase.QUARANTINED and rig.kernel.worker is None
                assert "binding.recheck" in rig.events
                assert ("worker.start" in rig.events) == (fault == "start")
                assert "lease.quarantine" in rig.events and "lease.release" not in rig.events

''' + cases[end:]
ast.parse(cases, filename="connection_cases.py")
(HERE / "connection_cases.py").write_bytes(cases.encode())
(HERE / "cases-cleanup-review01.diff").write_text("".join(difflib.unified_diff(old_cases.splitlines(True), cases.splitlines(True),
    fromfile="before/connection_cases.py", tofile="after/connection_cases.py")), encoding="utf-8", newline="\n")
print(json.dumps({"source_only": True, "candidate_executions": 0,
    "adapter_sha256": hashlib.sha256(new.encode()).hexdigest(),
    "connection_cases_sha256": hashlib.sha256(cases.encode()).hexdigest()}, indent=2))
