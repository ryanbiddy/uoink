"""3.18.1: an idle helper loads no speech, search or shelving model.

On 3.17.0 the helper sat at about 5.3 GB committed memory while idle after
loading an ML checkpoint at startup. 3.18.0 moved transcription into child
processes and made the other models load on first use. This test starts the
real helper (server.main) in a child process on an isolated profile and a free
loopback port, waits for /health, lets the startup threads run, reads the
routes the dashboard opens with, and then checks that no heavy ML module was
imported. It records import attempts with an audit hook, so it also catches an
attempt for a package this machine does not have installed.

Nothing here touches the network (non-loopback connects are refused), the
owner's library, or port 5179.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Top-level packages that carry model runtimes or weights. Any of them in the
# idle helper means memory that is not given back until the process exits.
HEAVY = ("torch", "torchaudio", "whisperx", "pyannote", "lightning", "pytorch_lightning",
         "faster_whisper", "ctranslate2", "onnxruntime", "tokenizers", "transformers",
         "sentence_transformers", "model2vec", "numpy", "av", "scipy", "sklearn")

CHILD = textwrap.dedent('''
    import json, os, sys, threading, time, urllib.request
    HEAVY = set(json.loads(os.environ["UOINK_TEST_HEAVY"]))
    attempts, blocked, worker_starts = [], [], []

    def audit(event, args):
        if event == "import" and str(args[0]).split(".")[0] in HEAVY:
            attempts.append(str(args[0]).split(".")[0])
        elif event == "subprocess.Popen" and (args[3] or {}).get("UOINK_ASR_CHILD") == "1":
            worker_starts.append("asr_worker")
            raise RuntimeError("idle fixture attempted to launch a transcription worker")
        elif event == "socket.connect":
            address = args[1]
            host = address[0] if isinstance(address, tuple) else str(address)
            if host not in ("127.0.0.1", "::1", "localhost"):
                blocked.append(str(host))
                raise ConnectionRefusedError("tests never leave this computer")
    sys.addaudithook(audit)
    sys.path.insert(0, os.environ["UOINK_TEST_REPO"])
    import helper._version
    helper._version.__version__ = "3.18.1-rc.1"
    import server
    assert server.PORT == int(os.environ["UOINK_ISOLATED_PORT"]) != 5179
    after_import = sorted(set(attempts))

    threading.Thread(target=server.main, kwargs={"quiet": True}, daemon=True).start()
    base = "http://127.0.0.1:%d" % server.PORT
    deadline = time.monotonic() + 90
    health = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(base + "/health", timeout=5) as r:
                health = json.loads(r.read())
                break
        except OSError:
            time.sleep(0.25)
    assert health and health.get("ok"), "helper never answered /health"
    # What the dashboard reads when it opens, with the helper's own token.
    routes = {}
    for path in ("/health", "/asr/models", "/library/transcript-backfill"):
        request = urllib.request.Request(base + path, headers={"X-Uoink-Token": server.TOKEN})
        try:
            with urllib.request.urlopen(request, timeout=30) as r:
                routes[path] = r.status
        except urllib.error.HTTPError as exc:
            routes[path] = exc.code
    # Let the startup threads (index backfill from disk, schedulers) run.
    time.sleep(float(os.environ.get("UOINK_TEST_IDLE_SECONDS", "4")))
    loaded = sorted(name for name in sys.modules if name.split(".")[0] in HEAVY)
    print("RESULT " + json.dumps({
        "after_import": after_import, "attempts": sorted(set(attempts)),
        "loaded": loaded, "blocked": blocked, "routes": routes,
        "worker_starts": worker_starts, "worker": server.asr_worker.status(),
        "version": health.get("version")}), flush=True)
    os._exit(0)
''')


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert port != 5179
    return port


def _seed_one_save(output: Path) -> None:
    """One ordinary saved post, so the index backfill thread has work at startup."""
    folder = output / "AI" / "a-saved-post"
    folder.mkdir(parents=True)
    sidecar = {"url": "https://example.com/post/1", "source_type": "page", "platform": "web",
               "title": "A saved post", "video_id": "example-post-0001",
               "yoinked_at": "2026-11-01T10:00:00", "text": "just words"}
    (folder / "a-saved-post.json").write_text(json.dumps(sidecar), encoding="utf-8")
    (folder / "a-saved-post.md").write_text("# A saved post\n\njust words\n", encoding="utf-8")


def test_idle_helper_loads_no_model_runtime(tmp_path):
    profile = tmp_path / "profile"
    home = tmp_path / "home"
    for path in (profile, home, tmp_path / "local", tmp_path / "roaming", tmp_path / "tmp"):
        path.mkdir(parents=True, exist_ok=True)
    _seed_one_save(profile / "output")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("UOINK_") and k not in ("ANTHROPIC_API_KEY", "HF_TOKEN")}
    env.update(
        UOINK_ISOLATED_PROFILE=str(profile), UOINK_ISOLATED_PORT=str(_free_port()),
        UOINK_DISABLE_AVAILABILITY_CHECK="1", UOINK_USAGE_SHARING="0",
        UOINK_TEST_REPO=str(ROOT), UOINK_TEST_HEAVY=json.dumps(HEAVY),
        LOCALAPPDATA=str(tmp_path / "local"), APPDATA=str(tmp_path / "roaming"),
        XDG_DATA_HOME=str(tmp_path / "local"), USERPROFILE=str(home), HOME=str(home),
        TMP=str(tmp_path / "tmp"), TEMP=str(tmp_path / "tmp"), TMPDIR=str(tmp_path / "tmp"),
        PYTHONDONTWRITEBYTECODE="1")
    # Moving HOME and APPDATA hides a per-user site-packages. Keep this
    # interpreter's packages importable, so a guarded "import it if it is
    # installed" path really runs, and the sys.modules check means something.
    import site
    user_site = site.getusersitepackages() if site.ENABLE_USER_SITE else None
    extra = [p for p in (user_site, os.environ.get("PYTHONPATH")) if p]
    if extra:
        env["PYTHONPATH"] = os.pathsep.join(extra)
    proc = subprocess.run([sys.executable, "-B", "-c", CHILD], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=180)
    lines = [line for line in proc.stdout.splitlines() if line.startswith("RESULT ")]
    assert proc.returncode == 0 and lines, (proc.returncode, proc.stdout[-2000:], proc.stderr[-4000:])
    result = json.loads(lines[-1][len("RESULT "):])
    assert result["blocked"] == [], result
    assert result["routes"] == {path: 200 for path in
                               ("/health", "/asr/models", "/library/transcript-backfill")}, result
    assert result["worker_starts"] == [], result
    worker = result["worker"]
    assert worker["state"] == "not_loaded" and worker["pid"] is None
    assert worker["jobs_run"] == 0 and worker["last_exit"] is None
    assert result["version"] == "3.18.1-rc.1"
    assert result["after_import"] == [], f"importing server pulled in {result['after_import']}"
    assert result["attempts"] == [], f"the idle helper tried to import {result['attempts']}"
    assert result["loaded"] == [], f"the idle helper holds {result['loaded']}"
    # The isolated profile, never the owner's library, was used.
    assert (profile / "index.db").exists()
