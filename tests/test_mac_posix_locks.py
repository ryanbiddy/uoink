"""Real flock contention and inode-preserving recovery after SIGKILL."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time

import pytest


CHILD = r'''
import contextlib,json,sys,threading,time
from pathlib import Path
import library_mirror as mirror
from library_work import LibraryWorkService
from source_subscriptions import CaptureLock
root, kind, mode = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
root.mkdir(parents=True, exist_ok=True)
@contextlib.contextmanager
def locked():
    if kind == 'capture':
        lock = CaptureLock.acquire(root, 'youtube:test', timeout=10, interval=.01)
        assert lock is not None
        try:
            yield Path(lock.path)
        finally:
            lock.release()
    elif kind == 'work':
        service = LibraryWorkService.__new__(LibraryWorkService)
        service.store_root = root
        service._store_lock = threading.RLock()
        with service._locked_store():
            yield root / '.library.lock'
    elif kind == 'ledger':
        service = mirror.Mirror.__new__(mirror.Mirror)
        service._lock_path = lambda: root / 'ledger.lock'
        fd, acquired = service._ledger_lock_acquire(10)
        try:
            yield service._lock_path()
        finally:
            service._ledger_lock_release(fd, acquired)
    else:
        owner = mirror._DestExclusionOwner(str(root), 10)
        owner.start_wait()
        try:
            yield mirror._dest_lock_path(str(root))
        finally:
            owner.release()
def send(event, **fields):
    print(json.dumps({'event': event, **fields}), flush=True)
send('attempting')
try:
    with locked() as path:
        st = path.stat()
        send('acquired', inode=[st.st_dev, st.st_ino])
        if mode == 'hold':
            sys.stdin.readline()
except BaseException as exc:
    send('error', error=type(exc).__name__, message=str(exc))
    raise
'''


def read(proc, expected):
    # Read a bounded, newline-framed message without a buffered readline
    # hiding the next frame from select or hanging on an incomplete frame.
    deadline = time.monotonic() + 15
    data = bytearray()
    while len(data) < 65536:
        remaining = max(0, deadline - time.monotonic())
        assert select.select([proc.stdout], [], [], remaining)[0], (
            f"lock worker stalled waiting for {expected}: {data!r}")
        byte = os.read(proc.stdout.fileno(), 1)
        assert byte, f"lock worker closed before {expected} (exit={proc.poll()}): {data!r}"
        if byte == b"\n":
            message = json.loads(data)
            assert message.get("event") == expected, message
            return message
        data.extend(byte)
    pytest.fail("lock worker frame exceeded 64 KiB")


@pytest.mark.skipif(os.name == "nt", reason="native fcntl contention and recovery")
@pytest.mark.parametrize("kind", ["capture", "work", "ledger", "admission"])
def test_lock_contention_holder_death_and_restart(tmp_path, kind):
    def spawn(mode):
        return subprocess.Popen([sys.executable, "-u", "-c", CHILD, str(tmp_path), kind, mode],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
    processes = []
    try:
        holder = spawn("hold")
        processes.append(holder)
        read(holder, "attempting")
        inode = read(holder, "acquired")["inode"]
        contender = spawn("hold")
        processes.append(contender)
        read(contender, "attempting")
        assert not select.select([contender.stdout], [], [], .2)[0]
        assert holder.poll() is None and contender.poll() is None
        holder.kill()
        holder.wait(timeout=10)
        assert read(contender, "acquired")["inode"] == inode
        contender.stdin.write(b"release\n")
        contender.stdin.flush()
        assert contender.wait(timeout=10) == 0
        restarted = spawn("once")
        processes.append(restarted)
        read(restarted, "attempting")
        assert read(restarted, "acquired")["inode"] == inode
        assert restarted.wait(timeout=10) == 0
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
            proc.stdin.close()
            proc.stdout.close()
