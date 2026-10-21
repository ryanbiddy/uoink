"""Exercise only the built payload from a relocated path and disposable profile."""
from __future__ import annotations

import argparse
import ast
from contextlib import nullcontext
import json
import os
from pathlib import Path
import queue
import plistlib
import shutil
import signal
import sys
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
import wave

from build_bundle import ROOT, PYTHON_EXECUTABLE, tree_inventory
from qualify_deps import write_json
from ffmpeg_bundle import probe_torchcodec
from import_smoke import COCOA_IMPORT


def environment(scratch: Path, port: int) -> dict:
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("DYLD_"):
            env.pop(key)
    for key in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE",
                "PYTHONEXECUTABLE", "UOINK_ISOLATED_APP_DIR"):
        env.pop(key, None)
    for key, relative in (("HOME", "home"), ("USERPROFILE", "home"), ("APPDATA", "roaming"),
                          ("LOCALAPPDATA", "local"), ("XDG_DATA_HOME", "data"),
                          ("XDG_CONFIG_HOME", "config"), ("XDG_CACHE_HOME", "cache"),
                          ("UOINK_ISOLATED_PROFILE", "profile"), ("UOINK_OUTPUT_DIR", "output"),
                          ("TMPDIR", "tmp"), ("TMP", "tmp"), ("TEMP", "tmp")):
        path = scratch / relative
        path.mkdir(exist_ok=True)
        env[key] = str(path)
    env.update(PATH="/usr/bin:/bin:/usr/sbin:/sbin",
               UOINK_ISOLATED_PORT=str(port), YOINK_OUTPUT_DIR=env["UOINK_OUTPUT_DIR"],
               PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", HF_HUB_OFFLINE="1",
               TRANSFORMERS_OFFLINE="1", PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    return env


def stop(proc):
    if proc is None:
        return
    # Each process was started in a new session; never terminate by name.
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except PermissionError:
        # macOS refuses signals to a group whose leader exited unreaped.
        if proc.poll() is None:
            raise
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=10)


def expected_tools() -> dict:
    tree = ast.parse((ROOT / "tests/test_c01_mcp_stdio.py").read_text(encoding="utf-8"))
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"CORE_STDIO_TOOLS", "CANONICAL_STDIO_TOOLS"}:
                    values[target.id] = set(ast.literal_eval(node.value))
    assert len(values["CORE_STDIO_TOOLS"]) == 35 and len(values["CANONICAL_STDIO_TOOLS"]) == 91
    return {"core": values["CORE_STDIO_TOOLS"], "full": values["CANONICAL_STDIO_TOOLS"]}


def stdio(python: Path, resources: Path, scratch: Path, env: dict, mode: str, output: Path):
    proc = None
    with (output / f"mcp-{mode}-stderr.txt").open("w") as log:
        try:
            proc = subprocess.Popen([str(python), "-B", "-s", str(resources / "uoink_mcp.py")],
                                    cwd=scratch, env={**env, "UOINK_MCP_TOOLSET": mode}, text=True,
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                                    start_new_session=True)
            replies = queue.Queue()
            threading.Thread(target=lambda: [replies.put(line) for line in proc.stdout], daemon=True).start()

            def exchange(message):
                proc.stdin.write(json.dumps(message) + "\n")
                proc.stdin.flush()
                if "id" not in message:
                    return None
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    try:
                        reply = json.loads(replies.get(timeout=1))
                    except queue.Empty:
                        if proc.poll() is not None:
                            raise AssertionError(f"MCP {mode} exited: {proc.returncode}")
                        continue
                    if reply.get("id") == message["id"]:
                        return reply
                raise AssertionError(f"MCP {mode} timed out")

            init = exchange({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "bundle-smoke", "version": "1"}}})
            assert init["result"]["serverInfo"]["version"] == (resources / "VERSION").read_text().strip()
            assert "library_mirror_unavailable_macos" in init["result"]["instructions"]
            assert "media_requires_ffmpeg" not in init["result"]["instructions"]
            exchange({"jsonrpc": "2.0", "method": "notifications/initialized"})
            listed = exchange({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            names = [row["name"] for row in listed["result"]["tools"]]
            assert len(names) == len(set(names)) and set(names) == expected_tools()[mode]
            write_json(output / f"tools-{mode}.json", listed)
            activity = exchange({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                 "params": {"name": "get_library_activity", "arguments": {}}})
            text = activity["result"]["content"][0]["text"]
            if "<untrusted_uoink_library_context>\n" in text:
                text = text.split("<untrusted_uoink_library_context>\n", 1)[1].split("\n</untrusted_uoink_library_context>", 1)[0]
            envelope = json.loads(text)
            assert envelope["capabilities"]["library_mirror"]["code"] == "library_mirror_unavailable_macos"
            return {"toolset": mode, "count": len(names), "ok": True}
        finally:
            stop(proc)


def media_smoke(contents: Path, scratch: Path, env: dict) -> dict:
    """Use generated local fixtures; every command names the relocated binary."""
    ffmpeg, ffprobe = [str(contents / "Helpers" / name) for name in ("ffmpeg", "ffprobe")]

    def run(command):
        try:
            return subprocess.run(command, cwd=scratch, env=env, check=True,
                                  capture_output=True, text=True, timeout=60).stdout
        except subprocess.CalledProcessError as error:
            print(f"media smoke command failed: {command[:3]}\n{error.stderr}", file=sys.stderr, flush=True)
            raise

    report = {name: run([binary, "-version"]) for name, binary in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe))}
    source, decoded = scratch / "input.wav", scratch / "decoded.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setparams((2, 2, 8000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\x10\x00\x20\x00" * 8000)
    run([ffmpeg, "-v", "error", "-nostdin", "-i", str(source), "-ar", "16000", "-ac", "1",
         "-c:a", "pcm_s16le", str(decoded)])
    with wave.open(str(decoded), "rb") as audio:
        assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth(), audio.getnframes()) == (16000, 1, 2, 16000)
        assert any(audio.readframes(16000))
    probe = json.loads(run([ffprobe, "-v", "error", "-show_streams", "-of", "json", str(decoded)]))
    assert probe["streams"][0]["sample_rate"] == "16000"
    # Native PPM -> MJPEG/MOV needs no video encoder library or fixture download.
    image = scratch / "input.ppm"
    image.write_bytes(b"P6\n16 16\n255\n" + b"\xff\x40\x20" * 256)
    video, frame = scratch / "generated.mov", scratch / "frame.jpg"
    run([ffmpeg, "-v", "error", "-nostdin", "-loop", "1", "-i", str(image), "-t", "1",
         "-c:v", "mjpeg", "-pix_fmt", "yuvj420p", str(video)])
    run([ffmpeg, "-v", "error", "-nostdin", "-i", str(video), "-vf", "fps=1,scale=16:16",
         "-pix_fmt", "yuvj420p", "-q:v", "2", "-frames:v", "1", "-update", "1", str(frame)])
    assert frame.read_bytes().startswith(b"\xff\xd8")
    report.update(audio="16000 Hz mono PCM WAV", frame="MJPEG/MOV -> JPEG")
    python = contents.parent / PYTHON_EXECUTABLE
    qualification = json.loads((contents / "Resources/notices/torchcodec.json").read_text())
    if qualification["available"]:
        report["torchcodec"] = probe_torchcodec(python, contents / "Frameworks/FFmpeg7", scratch, env)
    else:
        assert not (contents / "Frameworks/FFmpeg7").exists()
        report["torchcodec"] = qualification
    # Test the resolver and actual cached self-test in the bundled interpreter.
    run([str(python), "-B", "-s", "-c", "import sys; sys.path.insert(0, sys.argv[1]); "
         "import _platform; from pathlib import Path; "
         "assert Path(_platform.media_binary('ffmpeg')).resolve() == Path(sys.argv[2]).resolve(), (_platform.media_binary('ffmpeg'), sys.argv[2]); "
         "assert _platform.media_capability()['available']; "
         "assert _platform.alignment_capability()['available'] == (sys.argv[3] == 'True')",
         str(contents / "Resources"), ffmpeg, str(qualification["available"])])
    return report


def smoke(app: Path, output: Path, *, scratch: Path | None = None,
          env: dict | None = None, observer=None) -> dict:
    """Receipt callers keep the installed path/profile and observe live processes."""
    output.mkdir(parents=True)
    report = {"ok": False, "mcp": []}
    checks_passed = False
    relocate = scratch is None
    context = tempfile.TemporaryDirectory(prefix="uoink-bundle-smoke-") if relocate else nullcontext(scratch)
    with context as temporary:
        scratch = Path(temporary)
        # Move, then restore, to prove the loader does not depend on build paths.
        relocated = scratch / "Relocated App With Spaces" / "Uoink.app" if relocate else app
        if relocate:
            relocated.parent.mkdir()
            shutil.move(str(app), relocated)
        before = tree_inventory(relocated)
        helper = None
        try:
            if env is None:
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0))
                    port = sock.getsockname()[1]
                env = environment(scratch, port)
            port = int(env["UOINK_ISOLATED_PORT"])
            assert port != 5179
            contents = relocated / "Contents"
            python = relocated / PYTHON_EXECUTABLE
            resources = contents / "Resources"
            launcher = contents / "MacOS/Uoink"
            cli = contents / "Helpers/uoink"
            # Exercise a PATH-style symlink as well as the bundle's direct shim.
            cli_link = scratch / "uoink"
            cli_link.symlink_to(cli)
            connection = subprocess.run([str(cli_link), "connect", "claude-desktop"],
                                        env=env, cwd=scratch, capture_output=True, text=True,
                                        check=True, timeout=90)
            entry = json.loads(connection.stdout)["mcpServers"]["uoink"]
            # /var is a symlink to /private/var on macOS; compare real locations.
            def same_file(printed: str, expected: Path) -> bool:
                return Path(printed).resolve() == expected.resolve()
            assert same_file(entry["command"], python), ("connect command", entry, str(python))
            assert entry["args"][:2] == ["-B", "-s"], ("connect args", entry)
            assert same_file(entry["args"][2], resources / "uoink_mcp.py"), ("connect script", entry)
            assert str(Path(env["HOME"]) / "Library/Application Support/Claude/claude_desktop_config.json") in connection.stderr
            report["connect"] = entry
            agent = subprocess.run([str(python), "-B", "-s", "-m", "helper.mac_lifecycle", "plist", str(relocated)],
                                   env=env, cwd=resources, capture_output=True, check=True, timeout=30)
            agent_path = Path(env["HOME"]) / "Library/LaunchAgents/com.ryanbiddy.uoink.plist"
            agent_path.parent.mkdir(parents=True)
            agent_path.write_bytes(agent.stdout)
            config = plistlib.loads(agent.stdout)
            program = config["ProgramArguments"]
            assert len(program) == 2 and program[1] == "--helper", ("launchagent args", program)
            assert same_file(program[0], launcher), ("launchagent program", program, str(launcher))
            assert config["KeepAlive"] is False and config["RunAtLoad"] is True
            logs = (Path(env["HOME"]) / "Library/Logs/Uoink").resolve()
            for key in ("StandardOutPath", "StandardErrorPath"):
                if key == "StandardErrorPath" and key not in config:
                    continue
                assert Path(config[key]).resolve().is_relative_to(logs), ("launchagent log path", key, config[key])
            report["launchagent"] = {"generated": True, "bootstrapped": False}
            report["media"] = media_smoke(contents, scratch, env)
            cocoa = subprocess.run([str(python), "-B", "-s", "-c", COCOA_IMPORT],
                                   cwd=scratch, env=env, capture_output=True, text=True,
                                   check=True, timeout=60)
            report["cocoa"] = {"import_only": True, "stdout": cocoa.stdout}
            # The runner proves the menu run loop, not a visible WebKit window.
            # A current sentinel suppresses first-run UI only in this test profile.
            (Path(env["UOINK_ISOLATED_PROFILE"]) / ".first-run-done").write_text(
                (resources / "VERSION").read_text(), encoding="utf-8")
            report["splash"] = "suppressed in disposable smoke profile; interactive acceptance required"
            with (output / "helper.txt").open("w") as log:
                helper = subprocess.Popen([str(launcher), "--helper"], cwd=scratch, env=env,
                                          stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    if helper.poll() is not None:
                        raise AssertionError(f"Helper exited: {helper.returncode}")
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                            health = json.load(response)
                        assert health["ok"] is True
                        assert health["capabilities"]["library_mirror"]["code"] == "library_mirror_unavailable_macos"
                        assert health["capabilities"]["media"]["available"] is True
                        assert health["capabilities"]["media"]["code"] is None
                        report["health"] = health
                        break
                    except OSError:
                        time.sleep(0.2)
                else:
                    raise AssertionError("Bundled helper health timed out")
                base = f"http://127.0.0.1:{port}"
                # Obtain a fixture token via the normal local-UI handshake. Do
                # not read or log credential files or persist this response.
                request = urllib.request.Request(base + "/token", headers={
                    "X-Uoink-Client": "uoink-extension", "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty"})
                with urllib.request.urlopen(request, timeout=3) as response:
                    token = json.load(response)["token"]

                def ui_request(path, body=None):
                    headers = {"X-Uoink-Token": token, "Content-Type": "application/json"}
                    request = urllib.request.Request(base + path, headers=headers,
                        data=None if body is None else json.dumps(body).encode())
                    with urllib.request.urlopen(request, timeout=5) as response:
                        return json.load(response)

                def wait_menu():
                    deadline = time.monotonic() + 45
                    while time.monotonic() < deadline:
                        state = ui_request("/helper/ui")
                        if state["alive"] and state["connected"]:
                            return state
                        time.sleep(.25)
                    raise AssertionError("Installed AppKit menu did not connect: " + str(state))

                menu = wait_menu()
                if observer:
                    observer("connected", helper, menu)
                menu_pid = menu["pid"]
                command = subprocess.run(["/bin/ps", "-p", str(menu_pid), "-o", "command="],
                                         capture_output=True, text=True, check=True).stdout
                assert "-m helper.mac_menubar" in command, command
                assert str(python) in command or str(python.resolve()) in command, command
                report["menubar"] = {**menu, "bundled_command": command.strip()}

                def menu_pids():
                    listing = subprocess.run(["/bin/ps", "-axo", "pid=,command="],
                                             capture_output=True, text=True, check=True).stdout
                    return [int(line.strip().split(None, 1)[0]) for line in listing.splitlines()
                            if "-m helper.mac_menubar" in line
                            and str(Path(env["UOINK_ISOLATED_PROFILE"]).resolve()) in line]

                duplicate = subprocess.run([str(launcher), "--helper"], cwd=scratch, env=env,
                                           capture_output=True, text=True, timeout=45)
                assert duplicate.returncode == 0, duplicate.stderr
                assert wait_menu()["pid"] == menu_pid
                time.sleep(2)
                assert ui_request("/helper/ui")["alive"]
                assert menu_pids() == [menu_pid]
                report["menubar"]["duplicate_launch_same_pid"] = True
                status = subprocess.run([str(cli_link), "status"], cwd=scratch, env=env,
                                        capture_output=True, text=True, timeout=90)
                assert status.returncode == 0, status.stderr
                report["status"] = json.loads(status.stdout)
                assert report["status"]["ok"] is True
                assert report["status"]["helper_running"] is True
                assert report["status"]["capabilities"]["media"]["available"] is True
                mirror = subprocess.run([str(launcher), "mirror", "status"], cwd=scratch, env=env,
                                        capture_output=True, text=True, timeout=90)
                assert mirror.returncode == 1, mirror.stderr
                report["mirror"] = json.loads(mirror.stdout)
                assert report["mirror"]["ok"] is False
                assert report["mirror"]["code"] == "library_mirror_unavailable_macos"
                for mode in ("full", "core"):
                    report["mcp"].append(stdio(python, resources, scratch, env, mode, output))
                # A native Pillow operation with an output file outside the app.
                subprocess.run([str(python), "-B", "-c", "from PIL import Image; "
                                "im=Image.new('RGB',(8,8)); im.save('pillow.png'); "
                                "assert Image.open('pillow.png').size == (8,8)"],
                               cwd=scratch, env=env, check=True, timeout=60)
                report["pillow"] = "passed"
                assert ui_request("/helper/quit", {})["ok"]
                helper.wait(timeout=20)

                def assert_menu_gone(pid):
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        check = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "stat="],
                                               capture_output=True, text=True)
                        if check.returncode != 0 or check.stdout.strip().startswith("Z"):
                            return
                        time.sleep(.1)
                    raise AssertionError(f"Menu process survived helper exit: {pid}")

                assert_menu_gone(menu_pid)
                assert menu_pids() == []
                report["menubar"]["quit_no_survivor"] = True
                if observer:
                    observer("quit", helper, menu)
                # A second helper must acquire the released lock. Kill only
                # this test's direct child to exercise kernel-close of its pipe.
                helper = subprocess.Popen([str(launcher), "--helper"], cwd=scratch, env=env,
                                          stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    try:
                        restarted = wait_menu()
                        break
                    except OSError:
                        if helper.poll() is not None:
                            raise AssertionError(f"Relaunched helper exited with {helper.returncode}; see helper.txt")
                        time.sleep(.2)
                else:
                    raise AssertionError("Menu did not reconnect after relaunch")
                assert restarted["pid"] != menu_pid
                if observer:
                    observer("relaunch", helper, restarted)
                report["menubar"]["relaunch_connected"] = True
                helper.kill()
                helper.wait(timeout=10)
                assert_menu_gone(restarted["pid"])
                assert menu_pids() == []
                report["menubar"]["helper_death_no_survivor"] = True
                if observer:
                    observer("helper_death", helper, restarted)
                checks_passed = True
        finally:
            stop(helper)
            after = tree_inventory(relocated)
            report["bundle_unchanged"] = before == after
            report["ok"] = checks_passed and report["bundle_unchanged"]
            write_json(output / "tree-before.json", before)
            write_json(output / "tree-after.json", after)
            write_json(output / "smoke.json", report)
            if relocate:
                shutil.move(str(relocated), app)
            if before != after:
                raise AssertionError("Bundle changed during smoke")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    smoke(args.app.resolve(), args.output.resolve())
