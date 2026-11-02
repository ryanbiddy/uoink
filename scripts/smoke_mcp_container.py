"""Offline initialize/tools-list smoke using the image's normal entry point."""
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    # Registry import is dependency-light and does not bind or start the helper.
    import uoink_mcp_tools as registry

    child = subprocess.Popen(
        [sys.executable, "-B", str(ROOT / "scripts/run_mcp_container.py")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8")
    responses = queue.Queue()
    errors = []

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
        try:
            line = responses.get(timeout=30)
        except queue.Empty:
            raise AssertionError("MCP response timed out: " + "\n".join(errors[-5:])) from None
        assert line is not None, "Server exited: " + "\n".join(errors[-5:])
        reply = json.loads(line)
        assert reply.get("jsonrpc") == "2.0" and reply.get("id") == request_id, reply
        assert "result" in reply, reply
        return reply["result"]

    try:
        send(dict(id=1, method="initialize", params={
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "glama-linux-smoke", "version": "1"}}))
        init = receive(1)
        assert init["serverInfo"]["version"] == (ROOT / "VERSION").read_text().strip()
        send(dict(method="notifications/initialized"))
        send(dict(id=2, method="tools/list"))
        listed = receive(2)["tools"]
        names = [tool["name"] for tool in listed]
        expected = registry.stdio_tool_names()
        assert len(names) == len(registry.TOOL_REGISTRY) == len(expected)
        assert tuple(names) == expected and len(set(names)) == len(names)
        for tool in listed:
            spec = registry.TOOL_REGISTRY[tool["name"]]
            assert tool["description"] == spec.description
            assert tool["inputSchema"] == registry.client_input_schema(spec.input_schema, spec.name)
        # Directory inspectors also list resources; a fresh library is empty, not unavailable.
        send(dict(id=3, method="resources/list"))
        assert receive(3)["resources"] == []
        print(f"PASS: initialize and tools/list returned all {len(names)} registry tools without a helper; "
              "resources/list returned an empty library")
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
    assert child.returncode == 0, errors[-5:]


if __name__ == "__main__":
    main()
