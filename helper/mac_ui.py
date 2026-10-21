"""Darwin UI subprocesses, folder selection and text clipboard support.

No AppKit or Tk calls run in the HTTP helper. Each GUI owns its main thread.
"""
from __future__ import annotations

import atexit
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

_children = []
_children_lock = threading.Lock()
_menu = None
_connected_at = None


def child_environment() -> dict:
    import uoink_install_isolation as isolation
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("DYLD_") and key not in {
               "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE",
               "PYTHONEXECUTABLE", "UOINK_UI_LIFELINE"}}
    env.update(isolation.child_environ())
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    return env


def spawn(module: str, *args: str):
    """Use only the running bundle's Python. A pipe binds UI life to its owner."""
    import _platform
    if sys.platform != "darwin":
        raise RuntimeError("Mac UI requires Darwin")
    contents = _platform.mac_bundle_contents()
    if contents is None:
        raise RuntimeError("Mac UI requires the bundled interpreter")
    python = contents / _platform.MAC_BUNDLE_PYTHON
    if not python.is_file():
        raise RuntimeError("Bundled Python is missing")
    read_fd, write_fd = os.pipe()
    try:
        env = child_environment()
        env["UOINK_UI_LIFELINE"] = str(read_fd)
        proc = subprocess.Popen([str(python), "-B", "-s", "-m", module, *map(str, args)],
                                cwd=contents / "Resources", env=env,
                                pass_fds=(read_fd,), close_fds=True)
    except BaseException:
        os.close(write_fd)
        raise
    finally:
        os.close(read_fd)
    with _children_lock:
        # Reap dismissed windows and release their writers on the next launch.
        for old, writer in list(_children):
            if old.poll() is not None:
                os.close(writer)
                _children.remove((old, writer))
        _children.append((proc, write_fd))
    return proc


def close_children() -> None:
    with _children_lock:
        children = list(_children)
        _children.clear()
    for _, writer in children:
        os.close(writer)
    for proc, _ in children:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def watch_parent() -> None:
    """EOF also works after SIGKILL, without PID reuse or HTTP timeout guesses."""
    value = os.environ.pop("UOINK_UI_LIFELINE", None)
    if value is None:
        return
    descriptor = int(value)

    def watch():
        try:
            while os.read(descriptor, 1):
                pass
        finally:
            # The Cocoa loop can be stalled by a modal dialog. End this owned
            # process even then. Its own child lifelines close in the kernel.
            os._exit(0)

    threading.Thread(target=watch, name="uoink-ui-lifeline", daemon=True).start()


def start_menu(*, host, port, version, token_path, output_dir, data_root):
    global _menu, _connected_at
    # One launch attempt per helper, never a restart loop after UI failure.
    if _menu is None:
        _connected_at = None
        _menu = spawn("helper.mac_menubar", "--host", host, "--port", str(port),
                      "--version", version, "--token-path", str(token_path),
                      "--output-dir", str(output_dir), "--data-root", str(data_root))
    return _menu


def menu_state() -> dict:
    alive = _menu is not None and _menu.poll() is None
    return {"pid": _menu.pid if _menu is not None else None, "alive": alive,
            "connected": alive and _connected_at is not None,
            "connected_at": _connected_at, "helper_pid": os.getpid()}


def menu_connected(pid: int) -> bool:
    global _connected_at
    if _menu is None or _menu.poll() is not None or pid != _menu.pid:
        return False
    _connected_at = time.time()
    return True


def copy_text(text: str) -> bool:
    if sys.platform != "darwin" or not isinstance(text, str):
        return False
    try:
        # Markdown with data:image links is still plain UTF-8 text. Never place
        # large corpora on the command line or interpolate them into a shell.
        subprocess.run(["/usr/bin/pbcopy"], input=text.encode("utf-8"),
                       capture_output=True, timeout=5, check=True,
                       env={**child_environment(), "LC_ALL": "en_US.UTF-8", "LC_CTYPE": "en_US.UTF-8"})
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def dashboard_html(body: bytes) -> bytes:
    """Only the Darwin HTTP response uses the native clipboard bridge."""
    html = body.decode("utf-8")
    html = html.replace("navigator.clipboard.writeText(", "window.uoinkMacCopyText(")
    bridge = '''<script>
    window.uoinkMacCopyText = async function (text) {
      const api = window.pywebview && window.pywebview.api;
      if (api && api.copy_text) {
        if (!await api.copy_text(String(text))) throw new Error("Clipboard copy failed. Please try again.");
        return;
      }
      return navigator.clipboard.writeText(text);
    };
    </script>'''
    return html.replace("</head>", bridge + "</head>", 1).encode("utf-8")


def pick_folder(initial_dir: Path | None = None) -> dict:
    if sys.platform != "darwin":
        raise RuntimeError("Mac folder picker requires Darwin")
    # Pass the starting path as argv, never AppleScript source. choose folder
    # runs in osascript's own process, not an HTTP worker or a Tk thread.
    script = '''on run argv
        activate
        if (count argv) > 0 and item 1 of argv is not "" then
            set chosen to choose folder with prompt "Choose where Uoink saves new sources" default location (POSIX file (item 1 of argv))
        else
            set chosen to choose folder with prompt "Choose where Uoink saves new sources"
        end if
        return POSIX path of chosen
    end run'''
    try:
        result = subprocess.run(["/usr/bin/osascript", "-e", script, str(initial_dir or "")],
                                capture_output=True, text=True, timeout=120, check=False,
                                env=child_environment())
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": "folder_picker_timeout",
                "error": "Folder selection timed out. Your output folder has not changed."}
    except OSError:
        return {"ok": False, "code": "folder_picker_unavailable",
                "error": "The folder picker could not open. Your output folder has not changed."}
    if result.returncode == 0 and result.stdout.strip():
        return {"ok": True, "path": result.stdout.strip()}
    if "(-128)" in result.stderr or (result.returncode == 0 and not result.stdout.strip()):
        return {"ok": False, "cancelled": True, "code": "folder_picker_cancelled",
                "error": "No folder selected. Your output folder has not changed."}
    return {"ok": False, "code": "folder_access_denied",
            "error": "macOS could not open that folder. Allow Uoink access in System Settings > "
                     "Privacy & Security > Files and Folders, or choose another folder. "
                     "Your output folder has not changed."}


atexit.register(close_children)
