"""The supervisor writes helper output to helper-output.log as it arrives."""
from __future__ import annotations

import subprocess
import sys
import threading
import time

import uoink_supervisor


def test_short_helper_output_reaches_the_log_before_the_helper_exits(tmp_path):
    child = subprocess.Popen(
        [sys.executable, "-c", "import sys, time; print('menu bar icon: ready', flush=True); time.sleep(30)"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    reader = threading.Thread(target=uoink_supervisor.capture_output,
                              args=(child.stdout, tmp_path, [b""]), daemon=True)
    reader.start()
    log = tmp_path / "helper-output.log"
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if log.is_file() and "menu bar icon: ready" in log.read_text(encoding="utf-8"):
                break
            time.sleep(0.05)
        else:
            raise AssertionError("Helper output waited for 4 KiB or exit")
        assert child.poll() is None
    finally:
        child.kill()
        child.wait()
        reader.join(5)


def test_tail_is_bounded_and_output_is_kept_in_order(tmp_path):
    lines = 3000
    child = subprocess.Popen(
        [sys.executable, "-c", f"for i in range({lines}): print('line', i)"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    tail = [b""]
    uoink_supervisor.capture_output(child.stdout, tmp_path, tail)
    child.wait()
    text = "".join((tmp_path / "helper-output.log").read_text(encoding="utf-8").split("\n"))
    assert text.endswith(f"line {lines - 1}") and len(tail[0]) <= 8192
    # Windows children write CRLF line endings.
    assert tail[0].rstrip(b"\r\n").endswith(f"line {lines - 1}".encode())
