"""Product wire clients. No SDK imports or SDK handler access.

Callers own a disposable directory. The subprocess runs the real entry point;
the HTTP fixture runs the real Handler without starting resident background jobs.
"""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
LEGACY_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")
_USER_HOME = Path.home()
_USER_DATA_ROOTS = (
    _USER_HOME / "AppData/Local/Uoink",
    _USER_HOME / "Library/Application Support/Uoink",
    _USER_HOME / ".local/share/Uoink",
    Path(os.environ.get("LOCALAPPDATA", _USER_HOME / "AppData/Local")) / "Uoink",
    Path(os.environ.get("XDG_DATA_HOME", _USER_HOME / ".local/share")) / "Uoink",
)


def _assert_disposable_env(env):
    """Accept explicit profiles and redirected user roots, never live state.

    A temporary HOME is intentional in the read-only app and restart tests:
    keep that normal platform layout rather than changing the child's profile.
    Those stdio-only reads need no helper port. If a port is supplied, validate
    it even in a temporary-home environment.
    """
    forbidden = list(_USER_DATA_ROOTS)
    for source in (os.environ, env):
        live_index = source.get("IG_FORBIDDEN_LIVE")
        if live_index:
            forbidden.append(Path(live_index.replace("\\", "/")).parent)

    def disposable(value):
        assert value and Path(value).is_absolute(), "test root must be absolute"
        path = Path(value).resolve()
        assert path != _USER_HOME.resolve(), "refusing the real user home"
        for live in forbidden:
            assert not path.is_relative_to(live.resolve()), "refusing the live data root"
        return path

    profile = env.get("UOINK_ISOLATED_PROFILE")
    port = env.get("UOINK_ISOLATED_PORT")
    if port is not None:
        try:
            number = int(port)
        except (TypeError, ValueError):
            raise AssertionError("test port must be an integer") from None
        assert 0 < number <= 65535 and number != 5179, "refusing unsafe test port"
    if profile:
        disposable(profile)
        assert port is not None, "isolated profile requires a test port"
    else:
        assert port is None, "isolated port requires a profile"
        # Match the platform's effective root, including environment precedence.
        # A safe HOME alone cannot rescue a live LOCALAPPDATA or XDG_DATA_HOME.
        home = env.get("USERPROFILE" if sys.platform == "win32" else "HOME")
        if sys.platform == "win32":
            base = env.get("LOCALAPPDATA")
            root = (disposable(base) if base else disposable(home) / "AppData/Local") / "Uoink"
        elif sys.platform == "darwin":
            root = disposable(home) / "Library/Application Support/Uoink"
        else:
            base = env.get("XDG_DATA_HOME")
            root = (disposable(base) if base else disposable(home) / ".local/share") / "Uoink"
        disposable(root)
    # APP_DIR is optional in supported isolated installs, but cannot name live state.
    if env.get("UOINK_ISOLATED_APP_DIR"):
        disposable(env["UOINK_ISOLATED_APP_DIR"])


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    assert port != 5179
    return port


def isolated_env(directory, *, port=None, toolset="full"):
    directory = Path(directory).resolve()
    profile = directory / "profile"
    profile.mkdir(parents=True, exist_ok=True)
    app = directory / "app"
    app.mkdir(exist_ok=True)
    env = dict(os.environ)
    env.update(UOINK_ISOLATED_PROFILE=str(profile), UOINK_ISOLATED_APP_DIR=str(app),
               UOINK_ISOLATED_PORT=str(port or unused_port()),
               LOCALAPPDATA=str(directory / "appdata"), XDG_DATA_HOME=str(directory / "xdg"),
               UOINK_OUTPUT_DIR=str(directory / "out"), UOINK_MCP_TOOLSET=toolset,
               PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1",
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    return env


def rpc(request_id, method, params=None):
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def initialize_request(version, request_id=1):
    return rpc(request_id, "initialize", {
        "protocolVersion": version, "capabilities": {},
        "clientInfo": {"name": "uoink-wire-characterization", "version": "1"}})


class StdioClient:
    """Strict JSON lines, retained out-of-order replies, finite per-read waits."""

    def __init__(self, cmd, cwd, env, timeout=30):
        _assert_disposable_env(env)
        self.timeout = timeout
        self.proc = subprocess.Popen(
            cmd, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8",
            creationflags=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
        self.lines = queue.Queue()
        self.raw_stdout_lines = []
        self.stderr_lines = []
        self.transcript = []
        self.pending = []
        self._threads = [threading.Thread(target=self._drain_stdout, daemon=True),
                         threading.Thread(target=self._drain_stderr, daemon=True)]
        for thread in self._threads:
            thread.start()

    @classmethod
    def launch(cls, directory, *, toolset="full", env=None):
        return cls([sys.executable, "-B", "-P", str(ROOT / "uoink_mcp.py")],
                   directory, env or isolated_env(directory, toolset=toolset))

    def _drain_stdout(self):
        for line in self.proc.stdout:
            self.raw_stdout_lines.append(line)
            self.lines.put(line)
        self.lines.put(None)

    def _drain_stderr(self):
        for line in self.proc.stderr:
            self.stderr_lines.append(line.rstrip())

    def send_raw(self, line):
        self.transcript.append({"direction": "client", "line": line})
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def send(self, message):
        self.send_raw(json.dumps(message, ensure_ascii=False, allow_nan=False))

    def receive(self, timeout=None):
        try:
            line = self.lines.get(timeout=self.timeout if timeout is None else timeout)
        except queue.Empty:
            raise AssertionError("Timed out waiting for MCP output: " +
                                 "\n".join(self.stderr_lines[-6:])) from None
        assert line is not None, (self.proc.poll(), self.stderr_lines[-6:])
        self.transcript.append({"direction": "server", "line": line.rstrip("\r\n")})
        message = json.loads(line)  # Never discard polluted stdout.
        assert isinstance(message, dict) and message.get("jsonrpc") == "2.0", message
        return message

    def wait_for(self, request_id, timeout=None):
        for i, message in enumerate(self.pending):
            if "id" in message and message["id"] == request_id:
                return self.pending.pop(i)
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while True:
            message = self.receive(max(0, deadline - time.monotonic()))
            if "id" in message and message["id"] == request_id:
                return message
            self.pending.append(message)

    def request(self, request_id, method, params=None):
        self.send(rpc(request_id, method, params))
        return self.wait_for(request_id)

    def initialize(self, version="2025-11-25"):
        self.send(initialize_request(version))
        result = self.wait_for(1)
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return result

    def assert_quiet(self, timeout=0.15):
        assert not self.pending, self.pending
        try:
            line = self.lines.get(timeout=timeout)
        except queue.Empty:
            return
        raise AssertionError(f"Unexpected stdout after notification: {line!r}")

    def save(self, path):
        path = Path(path).resolve()
        assert path.is_relative_to(ROOT / "_scratch"), path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n"
                                for row in self.transcript), encoding="utf-8")

    def close(self):
        if not self.proc.stdin.closed:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
        for thread in self._threads:
            thread.join(timeout=2)
        self.proc.stdout.close()
        self.proc.stderr.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class HttpClient:
    TOKEN = "synthetic-m2-wire-token"

    def __init__(self, directory):
        self.port = unused_port()
        env = isolated_env(directory, port=self.port)
        self.child = StdioClient(
            [sys.executable, "-B", str(ROOT / "tests/mcp_http_server.py")], directory, env)
        try:
            ready = self.child.receive()
            assert ready == {"jsonrpc": "2.0", "method": "fixture/ready", "params": {"port": self.port}}
        except BaseException:
            self.child.close()
            raise
        self.transcript = []

    def post(self, message, *, path="/mcp/v1", token=TOKEN, host=None):
        headers = {"Content-Type": "application/json", "Host": host or f"127.0.0.1:{self.port}"}
        if token is not None:
            headers["X-Uoink-Token"] = token
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("POST", path, json.dumps(message).encode(), headers)
            response = conn.getresponse()
            raw = response.read()
            body = json.loads(raw) if raw else None
            self.transcript.append({"path": path, "request": message,
                                    "token": "valid" if token == self.TOKEN else "missing-or-invalid",
                                    "host": host or "loopback", "status": response.status, "body": body})
            return response.status, body
        finally:
            conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.child.close()


def registry_golden(toolset="full", *, structured_results=False):
    """Derive the complete expected inventory afresh, without SDK conversion."""
    import uoink_mcp_tools as tools
    registry = {tool["name"]: tool for tool in tools.list_tools(structured_results=structured_results)}
    return [dict(registry[name], inputSchema=tools.client_input_schema(registry[name]["inputSchema"], name))
            for name in tools.stdio_tool_names(toolset)]
