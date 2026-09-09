"""Verify recorder byte forwarding/lifecycle against a stdlib-only fake child.

This never launches uoink or a model. A passing result validates instrumentation,
not MCP, real-client behavior, source retrieval, or a phase acceptance gate.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(exist_ok=False)
    (root / "records").mkdir()
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    for key in ("LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "UOINK_OUTPUT_DIR"):
        directory = root / key.lower()
        directory.mkdir()
        env[key] = str(directory)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    tap = Path(__file__).with_name("stdio_tap.py").resolve()
    child = root / "fake_child.py"
    child.write_text('''import json,sys
for line in sys.stdin.buffer:
    value=json.loads(line)
    if value.get("method")=="die":
        sys.stderr.buffer.write(b"fixture child exit\\n");sys.stderr.buffer.flush()
        raise SystemExit(7)
    answer={"jsonrpc":"2.0","id":value["id"],"result":value["params"]}
    sys.stdout.buffer.write((json.dumps(answer,ensure_ascii=False)+"\\n").encode("utf-8"))
    sys.stdout.buffer.flush()
sys.stderr.buffer.write(b"fixture diagnostic\\n");sys.stderr.buffer.flush()
''', encoding="utf-8")
    command = [sys.executable, "-B", str(tap), "--fixture-root", str(root),
               "--record-dir", str(root / "records" / "case"), "--cwd", str(root),
               "--", sys.executable, "-B", str(child)]
    payloads = [{"text": "Unicode 🔑 café 中文; \\ and \"quotes\"\nline"},
                {"text": "complete payload " * 5000}, {"empty": [], "null": None}]
    requests = [{"jsonrpc": "2.0", "id": i, "method": "echo", "params": p}
                for i, p in enumerate(payloads)]
    raw = b"".join((json.dumps(r, ensure_ascii=False) + "\n").encode("utf-8") for r in requests)
    result = subprocess.run(command, input=raw, env=env, capture_output=True, timeout=15)
    assert result.returncode == 0, (result.returncode, result.stderr)
    expected = b"".join((json.dumps({"jsonrpc": "2.0", "id": i, "result": p}, ensure_ascii=False)
                         + "\n").encode("utf-8") for i, p in enumerate(payloads))
    assert result.stdout == expected
    assert result.stderr == b"fixture diagnostic\n"
    first = next((root / "records").glob("case-*")) / "events.jsonl"
    events = [json.loads(line) for line in first.read_text(encoding="utf-8").splitlines()]
    def frames(direction):
        return [e for e in events if e["kind"] == "frame" and e["direction"] == direction]
    for direction, expected_bytes in (("client_to_server", raw), ("server_to_client", expected),
                                       ("server_stderr", b"fixture diagnostic\n")):
        observed = frames(direction)
        assert b"".join(base64.b64decode(e["base64"]) for e in observed) == expected_bytes
        for event in observed:
            data = base64.b64decode(event["base64"])
            assert len(data) == event["bytes"]
            assert hashlib.sha256(data).hexdigest() == event["sha256"]
    assert len(frames("server_to_client")) == 3
    assert all(e["elapsed_ms"] >= 0 for e in frames("server_to_client"))
    ended = next(e for e in events if e["kind"] == "child_exit")
    assert ended["exit_code"] == 0 and ended["incomplete_requests"] == []
    assert ended["output_drain_complete"] and not ended["forwarding_failed"]
    dead = subprocess.run(command, input=b'{"jsonrpc":"2.0","id":99,"method":"die"}\n',
                          env=env, capture_output=True, timeout=15)
    assert dead.returncode == 7 and dead.stdout == b""
    second = next(p for p in (root / "records").glob("case-*/events.jsonl") if p != first)
    dead_events = [json.loads(line) for line in second.read_text(encoding="utf-8").splitlines()]
    dead_end = next(e for e in dead_events if e["kind"] == "child_exit")
    assert dead_end["exit_code"] == 7
    assert any(e["id_json"] == "99" and e["method"] == "die" for e in dead_end["incomplete_requests"])
    unsafe = dict(env, LOCALAPPDATA=str(root.parent))
    refusal = subprocess.run(command, input=b"", env=unsafe, capture_output=True, timeout=15)
    assert refusal.returncode == 2 and b"LOCALAPPDATA must resolve inside" in refusal.stderr
    receipt = {"instrumentation_only": True, "model_launched": False,
               "uoink_launched": False, "checks_passed": ["lossless_three_requests",
                   "full_stdout_and_stderr", "per_request_timings", "child_exit_identity",
                   "dead_child_retains_unanswered_request", "unsafe_profile_refused"],
               "input_bytes": len(raw), "output_bytes": len(expected),
               "files": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (first, second)}}
    (root / "verification.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
