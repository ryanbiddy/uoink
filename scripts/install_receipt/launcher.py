"""Launch original installed/source-runtime server.py with isolation flags.

Never uses start_server.ps1 / launch.bat. Never copies a stub over production
server.py for the final integration check. Synthetic instrument launches are
labeled and require C22_ALLOW_SYNTHETIC=1. Owned stop uses the Popen handle.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_HELPER_NAMES,
    FORBIDDEN_PORT,
    ISOLATED_FROM_INSTALL_FLAG,
    ISOLATED_PORT_FLAG,
    ISOLATED_PROFILE_FLAG,
    MARKER_FILENAME,
    SYNTHETIC_HOSTNAME,
    TOKEN_FILENAME,
)
from .guards import (
    bundled_pth_path,
    guard_env,
    inspect_bundled_pth,
    install_into_bundled_python,
    prove_guard_rejects_canary,
    require_automatic_site_loading,
    restore_guard_install,
    write_sitecustomize,
)
from .hashes import omit_raw_bytes, sha256_file
from .oracles import live_index_guard
from .owned_stop import (
    require_owned_handle,
    terminate_held_popen,
    wait_port_freed,
)
from .process_identity import exact_identity_on_handle, identity_from_popen, liveness
from .runner import OperatorRunner
from .source_runtime import write_install_marker
from .validation import (
    C22ValidationError,
    assert_isolation_flags,
    child_env_forbidden_resolution,
    forbidden_live_path_string,
    port_is_open,
    validate_port,
)


def resolve_interpreter(installed_app: Path, *, synthetic: bool) -> Path:
    python_exe = installed_app / "python" / "python.exe"
    if python_exe.is_file():
        return python_exe
    if synthetic:
        return Path(sys.executable)
    raise C22ValidationError(
        f"bundled python.exe missing under {installed_app}; "
        "refusing PATH/checkout fallback")


def launch_argv(installed_app: Path, *, isolated_profile: Path,
                isolated_port: int, synthetic: bool = False,
                include_from_install: bool = True) -> list[str]:
    validate_port(isolated_port)
    server = installed_app / "server.py"
    if not server.is_file():
        raise C22ValidationError(f"installed server.py missing: {server}")
    interpreter = resolve_interpreter(installed_app, synthetic=synthetic)
    argv = [
        str(interpreter), "-B", "-s", str(server),
        ISOLATED_PROFILE_FLAG, str(isolated_profile),
        ISOLATED_PORT_FLAG, str(isolated_port),
    ]
    marker = installed_app / MARKER_FILENAME
    isolation_mod = installed_app / "uoink_install_isolation.py"
    include = include_from_install
    if include and marker.is_file():
        try:
            marker_data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            marker_data = {}
        marked_profile = str(marker_data.get("profile") or "")
        marked_port = marker_data.get("port")
        if (marked_profile != str(isolated_profile)
                or int(marked_port or -1) != int(isolated_port)):
            # Documented CLI binding: do not consume a marker bound to a
            # different profile, and do not rewrite it.
            include = False
    if include and marker.is_file() and isolation_mod.is_file():
        argv.extend([ISOLATED_FROM_INSTALL_FLAG, str(installed_app)])
    assert_isolation_flags(argv)
    for name in DEFAULT_HELPER_NAMES:
        if name in {Path(part).name.lower() for part in argv}:
            raise C22ValidationError(f"default helper {name} leaked into argv")
    return argv


PROVENANCE_CODE = (
    "import hashlib, importlib, importlib.metadata, json, pathlib, sys, sysconfig\n"
    "required = ('server','source_subscriptions','index','uoink_mcp',"
    "'source_manifest','podcasts','library_work')\n"
    "modules = {}\n"
    "errors = []\n"
    "for name in required:\n"
    "    try:\n"
    "        mod = importlib.import_module(name)\n"
    "        path = pathlib.Path(getattr(mod, '__file__', '') or '')\n"
    "        resolved = str(path.resolve()) if path else None\n"
    "        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None\n"
    "        modules[name] = {'ok': True, 'file': resolved, 'sha256': digest}\n"
    "    except Exception as exc:\n"
    "        errors.append({'module': name, 'type': type(exc).__name__,"
    " 'message': str(exc)})\n"
    "        modules[name] = {'ok': False, 'error': type(exc).__name__}\n"
    "mcp_version = None\n"
    "try:\n"
    "    import mcp\n"
    "    mcp_version = importlib.metadata.version('mcp')\n"
    "except Exception as exc:\n"
    "    errors.append({'module': 'mcp', 'type': type(exc).__name__,"
    " 'message': str(exc)})\n"
    "usersite = ''\n"
    "try:\n"
    "    usersite = sysconfig.get_path('purelib', scheme='nt_user') if sys.platform=='win32' else ''\n"
    "except Exception:\n"
    "    usersite = ''\n"
    "report = {\n"
    "    'schema': 'c22-provenance-v1',\n"
    "    'executable': str(pathlib.Path(sys.executable).resolve()),\n"
    "    'version': sys.version.split()[0],\n"
    "    'nousersite': bool(sys.flags.no_user_site),\n"
    "    'prefix': sys.prefix,\n"
    "    'path': [str(p) for p in sys.path],\n"
    "    'usersite_scheme': usersite,\n"
    "    'usersite_on_path': bool(usersite and any("
    "str(p).lower().startswith(str(usersite).lower()) for p in sys.path)),\n"
    "    'modules': modules,\n"
    "    'mcp_version': mcp_version,\n"
    "    'import_errors': errors,\n"
    "}\n"
    "print(json.dumps(report))\n"
    "raise SystemExit(0 if not errors else 2)\n"
)


def provenance_argv(installed_app: Path, *, synthetic: bool = False) -> list[str]:
    interpreter = resolve_interpreter(installed_app, synthetic=synthetic)
    code = ("import pathlib, sys\n"
            "sys.path.insert(0, str(pathlib.Path(sys.argv[1]).resolve(strict=True)))\n"
            + PROVENANCE_CODE)
    return [str(interpreter), "-B", "-s", "-c", code, str(installed_app)]


class InstalledHelperLauncher:
    def __init__(self, runner: OperatorRunner, *,
                 fixture_ports: list[int] | None = None,
                 inject: str = ""):
        self.runner = runner
        self.fixture_ports = list(fixture_ports or [])
        self.inject = inject
        self.proc_record: dict[str, Any] | None = None
        self.live_before: dict[str, Any] | None = None
        self.guard_install: dict[str, Any] | None = None
        self.guard_original: dict[str, Any] | None = None
        self.canary_root: Path | None = None
        self.owned_child_records: list[dict[str, Any]] = []

    def _descendant_liveness(self) -> dict[str, Any]:
        """Registered and unregistered descendants. Unknown is a failure."""
        unknown = []
        alive = []
        dead = []
        for rec in self.owned_child_records:
            pid = rec.get("pid")
            created = rec.get("created_ms")
            if type(pid) is not int or pid <= 0:
                unknown.append(rec)
                continue
            live = liveness(pid, created if type(created) is int else None)
            rec = {**rec, "liveness": live}
            if live == "unknown":
                unknown.append(rec)
            elif live == "alive":
                alive.append(rec)
            else:
                dead.append(rec)
        return {
            "unknown": unknown,
            "alive": alive,
            "dead": dead,
            "stopped": not unknown and not alive,
            "unknown_is_failure": bool(unknown),
        }

    def _owned_children_stopped(self) -> bool:
        proc = (self.proc_record or {}).get("popen")
        if proc is not None and proc.poll() is None:
            return False
        state = self._descendant_liveness()
        if state["unknown_is_failure"]:
            return False
        return state["stopped"]

    def register_descendant(self, child: dict[str, Any] | None) -> None:
        if not isinstance(child, dict):
            return
        pid = child.get("pid")
        if type(pid) is not int or pid <= 0:
            return
        for existing in self.owned_child_records:
            if existing.get("pid") == pid and existing.get("created_ms") == child.get("created_ms"):
                existing.update(child)
                return
        self.owned_child_records.append(dict(child))

    def prepare_guards(self, *, isolated_profile: Path,
                       isolated_port: int) -> dict[str, Any]:
        inputs = self.runner.load_inputs()
        injection = self.runner.receipt_root / "injection"
        written = write_sitecustomize(injection)
        allowed = [isolated_port, *self.fixture_ports]
        fixture_loopback = None
        if self.fixture_ports:
            fixture_loopback = f"http://127.0.0.1:{self.fixture_ports[0]}"
        ig = forbidden_live_path_string()
        env = guard_env(
            isolated_profile=isolated_profile,
            allowed_ports=allowed,
            forbidden_live=ig,
            inject=self.inject,
            synthetic=self.runner.synthetic,
            audio_path=self.runner.receipt_root / "fixtures" / "synthetic-audio.bin",
            transcript_path=self.runner.receipt_root / "fixtures" / "synthetic-transcript.json",
            synthetic_host=SYNTHETIC_HOSTNAME,
            fixture_loopback=fixture_loopback,
        )
        env["PYTHONPATH"] = str(injection)
        env["C22_EVENTS_PATH"] = str(isolated_profile / "c22-guard-events.jsonl")
        checkout = Path(__file__).resolve().parents[2]
        child_env_forbidden_resolution(env, checkout=checkout)
        canary = self.runner.receipt_root / "guard-canary" / "index.canary"
        app = Path(inputs["installed_app"]["path"])
        interpreter = resolve_interpreter(app, synthetic=self.runner.synthetic)
        bundled = None
        site = app / "python" / "Lib" / "site-packages"
        pth_info = inspect_bundled_pth(app)
        if site.is_dir() and (app / "python" / "python.exe").is_file():
            require_automatic_site_loading(app)
            dest = site / "sitecustomize.py"
            preexisting = dest.read_bytes() if dest.is_file() else None
            already = self.guard_install and Path(self.guard_install.get("path") or "").is_file()
            if already:
                bundled = self.guard_install
            else:
                descendant_state = self._descendant_liveness()
                if descendant_state["unknown_is_failure"]:
                    raise C22ValidationError(
                        "refusing bundled guard install: descendant liveness is unknown")
                if not self._owned_children_stopped():
                    raise C22ValidationError(
                        "refusing bundled guard install while owned children "
                        "or descendants are running")
                bundled = install_into_bundled_python(
                    app, source=Path(written["path"]),
                    children_stopped=True,
                    original_restore=self.guard_original,
                )
                if self.guard_original is None:
                    self.guard_original = {
                        "path": bundled["path"],
                        "previous_absent": bundled.get("previous_absent", True),
                        "previous_sha256": bundled.get("previous_sha256"),
                        "previous_bytes": preexisting,
                        "owned_sha256": bundled.get("sha256"),
                        "pth_path": pth_info.get("path"),
                        "pth_sha256": pth_info.get("sha256"),
                    }
                self.guard_install = bundled
            proof = prove_guard_rejects_canary(
                injection=injection, canary_file=canary,
                extra_env={"IG_FORBIDDEN_LIVE": env["IG_FORBIDDEN_LIVE"]},
                interpreter=interpreter,
                bundled_app=app,
            )
        else:
            proof = prove_guard_rejects_canary(
                injection=injection, canary_file=canary,
                extra_env={"IG_FORBIDDEN_LIVE": env["IG_FORBIDDEN_LIVE"]},
                interpreter=interpreter,
            )
        result = {
            "sitecustomize": written,
            "env": env,
            "bundled": bundled,
            "canary_proof": proof,
            "forbidden_live": ig,
            "opened_live_index": False,
            "hashed_live_index": False,
            "guard_original": omit_raw_bytes(self.guard_original),
            "pth": pth_info,
            "target_interpreter": str(interpreter),
        }
        (self.runner.receipt_root / "guards.json").write_text(
            json.dumps(omit_raw_bytes({
                k: v for k, v in result.items() if k != "env"
            } | {
                "env_keys": sorted(env),
                "allowed_ports": allowed,
                "ig_forbidden_live": env.get("IG_FORBIDDEN_LIVE"),
                "c22_forbidden_live": env.get("C22_FORBIDDEN_LIVE"),
            }), indent=2) + "\n", encoding="utf-8")
        return result

    def start(self, *, profile_name: str, isolated_profile: Path,
              isolated_port: int, wait_seconds: float = 25.0) -> dict[str, Any]:
        isolated_profile = Path(isolated_profile)
        isolated_profile.mkdir(parents=True, exist_ok=True)
        isolated_port = validate_port(isolated_port)
        if port_is_open("127.0.0.1", isolated_port):
            raise C22ValidationError(
                f"isolated port {isolated_port} is already occupied")
        forbidden = forbidden_live_path_string()
        self.live_before = live_index_guard(Path(forbidden))
        inputs = self.runner.load_inputs()
        app = Path(inputs["installed_app"]["path"])
        marker_path = app / MARKER_FILENAME
        if marker_path.is_file():
            try:
                existing_marker = json.loads(
                    marker_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise C22ValidationError(
                    f"isolated-install.json is unreadable; refusing: {exc}") from exc
            same_binding = (
                str(existing_marker.get("profile") or "") == str(isolated_profile)
                and int(existing_marker.get("port") or -1) == int(isolated_port)
            )
            if same_binding:
                marker_note = {
                    "path": str(marker_path),
                    "unchanged": True,
                    "payload": existing_marker,
                }
            else:
                marker_note = {
                    "path": str(marker_path),
                    "unchanged": True,
                    "preserved_installer_ownership": True,
                    "cli_binding": True,
                    "marker_profile": existing_marker.get("profile"),
                    "requested_profile": str(isolated_profile),
                }
        else:
            marker_note = write_install_marker(
                app, profile=isolated_profile, port=isolated_port,
                overwrite=False)
        argv = launch_argv(
            app, isolated_profile=isolated_profile,
            isolated_port=isolated_port, synthetic=self.runner.synthetic)
        guards = None
        record = None
        try:
            guards = self.prepare_guards(
                isolated_profile=isolated_profile, isolated_port=isolated_port)
        except BaseException:
            self._restore_guard_after_failed_prepare()
            raise
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        ig_retained = (os.environ.get("IG_FORBIDDEN_LIVE") or forbidden)
        env.update(guards["env"])
        # Declared profile is the data root. Do not silently nest Uoink by
        # substituting LOCALAPPDATA=profile. Protect the live path first by
        # pointing Windows per-user dirs at a canary, not the live library.
        canary = self.runner.receipt_root / "canary-localappdata"
        canary.mkdir(parents=True, exist_ok=True)
        self.canary_root = canary
        env["UOINK_OUTPUT_DIR"] = str(isolated_profile / "output")
        env["LOCALAPPDATA"] = str(canary)
        env["APPDATA"] = str(canary)
        env["USERPROFILE"] = str(canary)
        env["TEMP"] = str(isolated_profile / "tmp")
        env["TMP"] = str(isolated_profile / "tmp")
        env["UOINK_ISOLATED_PROFILE"] = str(isolated_profile)
        env["UOINK_ISOLATED_PORT"] = str(isolated_port)
        env["UOINK_ISOLATED_APP_DIR"] = str(app)
        # Honor the integrator forbidden path even after LOCALAPPDATA changes.
        env["IG_FORBIDDEN_LIVE"] = ig_retained
        env["C22_FORBIDDEN_LIVE"] = ig_retained
        (isolated_profile / "tmp").mkdir(parents=True, exist_ok=True)
        (isolated_profile / "output").mkdir(parents=True, exist_ok=True)
        try:
            record = self._spawn(argv, env=env, name=f"helper-{profile_name}",
                                 cwd=app)
            self.proc_record = record
            ready = self.wait_health(
                isolated_port, timeout=wait_seconds, proc=record.get("popen"))
            record["health"] = ready
            record["token_path"] = str(isolated_profile / TOKEN_FILENAME)
            record["live_index_before"] = self.live_before
            record["canary_root"] = str(canary)
            if not ready.get("ok"):
                record["cleanup_on_failed_health"] = self._cleanup_spawn(
                    record, port=isolated_port)
            record["live_index_forbidden"] = self.live_before
            record["opened_live_index"] = False
            record["hashed_live_index"] = False
            record["marker"] = marker_note
            record["ig_forbidden_live"] = ig_retained
            record["canary_proof"] = (guards.get("canary_proof") or {})
            nested = canary / "Uoink" / "index.db"
            record["canary_used_as_data_root"] = nested.is_file()
            declared = isolated_profile / "index.db"
            record["declared_profile_is_data_root"] = declared.is_file() or ready.get("ok")
        except BaseException:
            if record is not None:
                self._cleanup_spawn(record, port=isolated_port)
            else:
                self._restore_guard_after_failed_prepare()
            raise
        (self.runner.receipt_root / f"helper-{profile_name}.json").write_text(
            json.dumps(omit_raw_bytes({k: v for k, v in record.items() if k != "popen"}),
                       indent=2, default=str) + "\n", encoding="utf-8")
        return record

    def wait_health(self, port: int, timeout: float, proc=None) -> dict[str, Any]:
        url = f"http://127.0.0.1:{port}/health"
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            if proc is not None and proc.poll() is not None:
                stderr = ""
                err_path = None
                if self.proc_record:
                    err_path = self.proc_record.get("stderr_path")
                if err_path and Path(err_path).is_file():
                    stderr = Path(err_path).read_text(
                        encoding="utf-8", errors="replace")[-4000:]
                return {
                    "ok": False, "url": url,
                    "error": last,
                    "exited": proc.returncode,
                    "stderr_tail": stderr,
                }
            try:
                with urllib.request.urlopen(url, timeout=0.5) as response:
                    body = response.read()
                    return {
                        "ok": True,
                        "status": response.status,
                        "url": url,
                        "body": body.decode("utf-8", errors="replace")[:4000],
                    }
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = str(exc)
                time.sleep(0.15)
        return {"ok": False, "url": url, "error": last}

    def stop_owned(self, *, port: int, identity: dict[str, Any],
                   token: str | None, timeout: float = 15.0,
                   record: dict[str, Any] | None = None) -> dict[str, Any]:
        target = record or self.proc_record or {}
        if target.get("_stop_result"):
            return target["_stop_result"]
        validate_port(port)
        proc = target.get("popen")
        if proc is not None and proc.poll() is None:
            if not exact_identity_on_handle(identity_from_popen(proc), identity):
                raise C22ValidationError("owned stop requires exact current helper identity before HTTP")
        result: dict[str, Any] = {
            "identity": identity,
            "quit_http": None,
            "token_present": bool(token),
        }
        if token and proc is not None and proc.poll() is None:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/helper/quit",
                data=b"{}",
                headers={
                    "Content-Type": "application/json",
                    "X-Uoink-Token": token,
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=3) as response:
                    result["quit_http"] = {
                        "status": response.status,
                        "body": response.read().decode("utf-8", errors="replace")[:1000],
                    }
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                result["quit_http"] = {"error": str(exc)}
        proc = target.get("popen")
        if proc is not None:
            deadline = time.time() + min(5.0, timeout)
            while time.time() < deadline and proc.poll() is None:
                time.sleep(0.1)
            if proc.poll() is None:
                stopped = terminate_held_popen(
                    proc, expected=identity, timeout=timeout)
                result["handle_stop"] = stopped
            result["exit"] = proc.returncode
            result["stopped"] = proc.poll() is not None
        else:
            result["refused_pid_only"] = True
            result["stopped"] = False
            result["reason"] = "no Popen handle; unknown is not dead"
        result["port_freed"] = wait_port_freed(port)
        if self.guard_install and self.guard_install.get("path"):
            deadline = time.time() + timeout
            while time.time() < deadline:
                descendant_state = self._descendant_liveness()
                if descendant_state["unknown_is_failure"]:
                    break
                if descendant_state["stopped"]:
                    break
                time.sleep(0.2)
            descendant_state = self._descendant_liveness()
            helper_alive = proc is not None and proc.poll() is None
            if helper_alive or not descendant_state["stopped"]:
                result["guard_restore_deferred"] = {
                    "helper_alive": helper_alive,
                    "descendants_alive": len(descendant_state["alive"]),
                    "descendants_unknown": len(descendant_state["unknown"]),
                }
                if descendant_state["unknown_is_failure"]:
                    result["guard_restore_unknown_failure"] = True
                    raise C22ValidationError(
                        "refusing guard restore: descendant liveness is unknown")
            else:
                original_meta = self.guard_original or {}
                result["guard_restore"] = restore_guard_install(
                    Path(self.guard_install["path"]),
                    original=original_meta.get("previous_bytes"),
                    original_sha256=original_meta.get("previous_sha256"),
                    owned_sha256=original_meta.get("owned_sha256")
                    or self.guard_install.get("sha256"),
                    children_stopped=True,
                    descendants_stopped=True,
                    descendants_unknown=False,
                )
                pth_path = original_meta.get("pth_path")
                if pth_path:
                    current_pth = inspect_bundled_pth(
                        Path(pth_path).parent.parent
                        if Path(pth_path).name.endswith("._pth")
                        else Path(self.runner.load_inputs()["installed_app"]["path"]))
                    result["pth_preserved"] = {
                        "sha256": current_pth.get("sha256"),
                        "matches_original": current_pth.get("sha256")
                        == original_meta.get("pth_sha256"),
                    }
                result["guard_original_preserved"] = {
                    "previous_absent": original_meta.get("previous_absent"),
                    "previous_sha256": original_meta.get("previous_sha256"),
                    "rewritten": False,
                }
        result["opened_live_index"] = False
        result["hashed_live_index"] = False
        if self.live_before is not None:
            result["live_index_forbidden"] = self.live_before
        self.runner.record_event("helper_stopped",
                                 **omit_raw_bytes({k: v for k, v in result.items()
                                                   if k != "popen"}))
        if result.get("stopped") and not result.get("guard_restore_deferred"):
            target["_stop_result"] = result
        return result

    def terminate_owned(self, identity: dict[str, Any],
                        record: dict[str, Any] | None = None) -> dict[str, Any]:
        target = record or self.proc_record
        if not target:
            raise C22ValidationError(
                "refusing terminate: no owned Popen handle")
        proc = require_owned_handle(target)
        stopped = terminate_held_popen(proc, expected=identity)
        return {
            "identity": identity,
            "handle_stop": stopped,
            "exit": proc.returncode,
            "stopped": proc.poll() is not None,
        }

    def _restore_guard_after_failed_prepare(self) -> None:
        if not self.guard_install or not self.guard_install.get("path"):
            return
        original_meta = self.guard_original or {}
        restore_guard_install(
            Path(self.guard_install["path"]),
            original=original_meta.get("previous_bytes"),
            original_sha256=original_meta.get("previous_sha256"),
            owned_sha256=original_meta.get("owned_sha256")
            or self.guard_install.get("sha256"),
            children_stopped=True,
            descendants_stopped=True,
            descendants_unknown=False,
        )

    def _cleanup_spawn(self, record: dict[str, Any], *, port: int) -> dict[str, Any]:
        identity = record.get("child") or {}
        return self.stop_owned(
            port=port, identity=identity, token=None, record=record)

    def _spawn(self, argv: list[str], *, env: dict[str, str],
               name: str, cwd: Path) -> dict[str, Any]:
        import subprocess
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        prefix = self.runner.commands_dir / f"{stamp}-{name}"
        stdout_path = prefix.with_suffix(".stdout.log")
        stderr_path = prefix.with_suffix(".stderr.log")
        with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
            proc = subprocess.Popen(
                argv, cwd=str(cwd), env=env, stdout=out, stderr=err)
        child = identity_from_popen(proc)
        record = {
            "name": name,
            "argv": argv,
            "cwd": str(cwd),
            "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "child": child,
            "pid": proc.pid,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "synthetic": self.runner.synthetic,
            "popen": proc,
        }
        self.runner.record_event(
            "helper_spawn",
            **{k: v for k, v in record.items() if k != "popen"})
        (prefix.with_suffix(".json")).write_text(
            json.dumps(omit_raw_bytes({k: v for k, v in record.items() if k != "popen"}),
                       indent=2, default=str) + "\n",
            encoding="utf-8")
        return record


def read_token(installed_app: Path, profile: Path) -> str | None:
    """Agreed token location is <profile>/token.txt. Install-dir tokens are
    recorded as isolation-not-applied, not silently substituted."""
    profile_token = Path(profile) / TOKEN_FILENAME
    if profile_token.is_file():
        text = profile_token.read_text(encoding="utf-8").strip()
        if text:
            return text
    return None


def read_token_with_note(installed_app: Path, profile: Path) -> dict[str, Any]:
    profile_token = Path(profile) / TOKEN_FILENAME
    install_token = Path(installed_app) / TOKEN_FILENAME
    value = read_token(installed_app, profile)
    return {
        "token": value,
        "profile_token_present": profile_token.is_file(),
        "install_token_present": install_token.is_file(),
        "agreed_path": str(profile_token),
        "isolation_not_applied": value is None and install_token.is_file(),
    }


def inventory_installed(installed_app: Path) -> dict[str, Any]:
    """Record installed provenance. Does not import product modules in a
    way that opens default data; uses file hashes only."""
    files = {}
    for rel in ("server.py", "source_subscriptions.py", "index.py",
                "uoink_mcp.py", "uoink_install_isolation.py",
                "migrations/0028_source_subscriptions.sql",
                "migrations/0030_media_depth.sql",
                "VERSION", MARKER_FILENAME):
        path = installed_app / rel
        files[rel.replace("\\", "/")] = {
            "present": path.is_file(),
            "sha256": sha256_file(path) if path.is_file() else None,
            "bytes": path.stat().st_size if path.is_file() else None,
        }
    interpreter = installed_app / "python" / "python.exe"
    return {
        "installed_app": str(installed_app),
        "interpreter": str(interpreter) if interpreter.is_file() else None,
        "files": files,
        "note": "module __file__ provenance requires the running installed child",
    }


def run_provenance_command(runner: OperatorRunner, installed_app: Path) -> dict[str, Any]:
    import subprocess
    from .manifest import load_candidate_package_02
    from .receipt_integrity import verify_installed_bindings
    from .oracles import parse_provenance_json
    inputs = runner.load_inputs()
    profile = Path(inputs["isolated_profile"])
    port = inputs["isolated_port"]
    bindings = None
    if (installed_app / "python" / "python.exe").is_file():
        bindings = verify_installed_bindings(installed_app, load_candidate_package_02())
        if not bindings["ok"]:
            raise C22ValidationError("installed compiler inputs differ: " + repr(bindings["problems"]))
    launcher = InstalledHelperLauncher(runner)
    guards = launcher.prepare_guards(isolated_profile=profile, isolated_port=port)
    env = {**os.environ, **guards["env"], "C22_PROVENANCE_ONLY": "1"}
    argv = provenance_argv(installed_app, synthetic=runner.synthetic)
    record = None
    try:
        record = launcher._spawn(argv, env=env, name="bundled-provenance", cwd=installed_app)
        launcher.proc_record = record
        try:
            record["popen"].wait(timeout=60)
        except subprocess.TimeoutExpired:
            record["timeout"] = True
            launcher.terminate_owned(record["child"], record=record)
        record["exit"] = record["popen"].poll()
    finally:
        if record is not None:
            record["cleanup"] = launcher.stop_owned(port=port, identity=record["child"], token=None, record=record)
        else:
            launcher._restore_guard_after_failed_prepare()
    stdout = Path(record["stdout_path"]).read_text(encoding="utf8", errors="replace")
    parsed = parse_provenance_json(stdout)
    record["structured"] = parsed
    record["source_bindings"] = bindings
    record["structured_ok"] = bool(parsed) and not (parsed or {}).get("import_errors") and record["exit"] == 0
    record["exit_nonzero_on_import_error"] = record["exit"] not in (0, None) if (parsed or {}).get("import_errors") else True
    result = omit_raw_bytes({k: v for k, v in record.items() if k != "popen"})
    runner.record_event("bundled_provenance_complete", **result)
    return result
