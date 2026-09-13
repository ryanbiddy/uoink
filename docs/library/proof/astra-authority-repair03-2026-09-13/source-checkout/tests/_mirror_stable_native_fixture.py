"""Native-handle setup for the uncommitted authority proposal tests only.

This adapts their existing inert PID observations to explicit fake handles.
No behavior assertion is changed and no missing observation reaches Windows.
"""
import pytest

import library_mirror as mirror


@pytest.fixture(autouse=True)
def stable_native_authority(monkeypatch, request):
    review_launch = request.module.__name__.endswith("test_mirror_authority_review02")
    if review_launch:
        request.getfixturevalue("inert_native_boundary")
    original_ms = mirror._windows_process_created_ms
    original_pid_created = mirror._process_created_ms
    original_liveness = mirror._process_liveness
    handles = {}
    next_handle = [900000]

    def popen_handle(proc):
        handle = getattr(proc, "_handle", None)
        if handle is None:
            next_handle[0] += 1
            handle = next_handle[0]
            proc._handle = handle
        handles[handle] = proc.pid
        return handle

    def open_child(pid):
        next_handle[0] += 1
        handle = next_handle[0]
        handles[handle] = pid
        # Launch controls already supply an inert kernel with exact handles.
        # Use its configured child handle when present, preserving effect IDs.
        kernel = mirror._kernel32()
        mapping = getattr(kernel, "handles", None)
        if isinstance(mapping, dict) and pid in mapping:
            handle = mapping[pid]
            handles[handle] = pid
        return handle

    def native_created(handle):
        fn = mirror._windows_process_created_ms
        if fn is not original_ms:
            value = fn(handle)
        else:
            pid = handles.get(handle)
            fn = mirror._process_created_ms
            if pid is None or fn is original_pid_created:
                return None
            value = fn(pid)
        return None if value is None else mirror._FILETIME_EPOCH_OFFSET_100NS + value * 10000

    def liveness(handle, created_ms=None):
        pid = handles.get(handle)
        fn = mirror._process_liveness
        if pid is None or fn is original_liveness:
            raise AssertionError("Missing inert handle liveness observation")
        return fn(pid, created_ms)

    # No default kernel operation is authorized for these discovery fixtures.
    class RefusingKernel:
        def __getattr__(self, name):
            if name == "handles":
                return {}
            raise AssertionError("Unmocked native operation: " + name)

    if not review_launch:
        monkeypatch.setattr(mirror, "_kernel32", lambda: RefusingKernel())
    monkeypatch.setattr(mirror, "_popen_native_handle", popen_handle)
    monkeypatch.setattr(mirror, "_open_ownership_handle", open_child)
    monkeypatch.setattr(mirror, "_windows_process_created_100ns", native_created)
    monkeypatch.setattr(mirror, "_native_handle_liveness", liveness)
