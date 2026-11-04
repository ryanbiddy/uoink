"""Initialize and list tools through an installed CLI: smoke_stdio.py COMMAND [ARGS...]."""
from collections import deque
import json
import queue
import subprocess
import sys
import threading
import time


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: smoke_stdio.py COMMAND [ARGS...]")
    child = subprocess.Popen(
        [*sys.argv[1:], "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8")
    responses = queue.Queue()
    errors = deque(maxlen=20)

    def drain_stdout():
        for line in child.stdout:
            responses.put(line)
        responses.put(None)

    def drain_stderr():
        for line in child.stderr:
            errors.append(line.rstrip())

    threads = [threading.Thread(target=drain_stdout, daemon=True),
               threading.Thread(target=drain_stderr, daemon=True)]
    for thread in threads:
        thread.start()

    def send(message):
        child.stdin.write(json.dumps(dict(jsonrpc="2.0", **message)) + "\n")
        child.stdin.flush()

    def receive(request_id):
        deadline = time.monotonic() + 30
        while True:
            try:
                line = responses.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty:
                raise AssertionError("MCP response timed out: " + "\n".join(errors)) from None
            assert line is not None, "Server exited: " + "\n".join(errors)
            reply = json.loads(line)
            assert reply.get("jsonrpc") == "2.0", reply
            if "method" in reply and "id" not in reply:
                continue  # Server notifications may precede the response.
            assert reply.get("id") == request_id and "result" in reply, reply
            return reply["result"]

    try:
        send(dict(id=1, method="initialize", params={
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "uoink-linux-install-smoke", "version": "1"}}))
        initialized = receive(1)
        assert initialized["serverInfo"]["version"]
        assert "tools" in initialized["capabilities"]
        send(dict(method="notifications/initialized"))
        send(dict(id=2, method="tools/list"))
        listed = receive(2)["tools"]
        assert listed, "The installed MCP server returned no tools"
        names = [tool["name"] for tool in listed]
        assert len(set(names)) == len(names), "Duplicate MCP tools"
        print(f"PASS: installed MCP initialize and tools/list ({len(names)} tools)")
    finally:
        child.stdin.close()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=2)
        child.stdout.close()
        child.stderr.close()
    assert child.returncode == 0, list(errors)


if __name__ == "__main__":
    main()
