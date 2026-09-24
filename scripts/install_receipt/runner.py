"""Fail-closed operator runner. Records every command; never overwrites."""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .constants import (
    CAPTURE_PROFILE_NAMES,
    FORBIDDEN_PORT,
    INNO_NOCLOSE_FLAG,
    INNO_NORESTARTAPPS_FLAG,
    REQUIRED_OPERATOR_INPUTS,
    SCENARIO_IDS,
)
from .hashes import file_record, omit_raw_bytes, sha256_file
from .manifest import load_candidate_package_02, load_manifest, require_sealed_package_hash
from .process_identity import identity_for_pid
from .validation import (
    C22ValidationError,
    as_absolute,
    forbidden_live_path_string,
    ordinary_userprofile,
    validate_inno_argv,
    validate_installed_app,
    validate_isolated_profile,
    validate_not_ordinary_user,
    validate_package,
    validate_port,
    validate_receipt_root,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OperatorRunner:
    def __init__(self, receipt_root: Path, *, synthetic: bool = False):
        self.receipt_root = Path(receipt_root)
        self.synthetic = synthetic
        self.journal_path = self.receipt_root / "journal.jsonl"
        self.summary_path = self.receipt_root / "runner.json"
        self.commands_dir = self.receipt_root / "commands"
        self.artifacts_dir = self.receipt_root / "artifacts"

    @classmethod
    def create(cls, *, receipt_root: str | Path, installed_app_path: str | Path,
               package_path: str | Path, package_sha256: str,
               isolated_profile: str | Path, isolated_port: Any,
               manifest_path: str | Path | None = None,
               synthetic: bool = False,
               require_space: bool = True,
               require_bundled_python: bool = True,
               skip_ordinary_user_check: bool = False) -> "OperatorRunner":
        root = validate_receipt_root(receipt_root)
        root.mkdir(parents=True, exist_ok=False)
        runner = cls(root, synthetic=synthetic)
        runner.commands_dir.mkdir()
        runner.artifacts_dir.mkdir()
        (root / "profiles").mkdir()
        (root / "injection").mkdir()
        (root / "evidence").mkdir()
        (root / "fixtures").mkdir()
        try:
            if not synthetic and not skip_ordinary_user_check:
                validate_not_ordinary_user()
            manifest = load_manifest(manifest_path)
            if not synthetic:
                sealed = require_sealed_package_hash(manifest)
                if sealed != package_sha256.strip().lower():
                    raise C22ValidationError(
                        "operator package_sha256 does not match the sealed "
                        "manifest digest")
            package = validate_package(package_path, package_sha256)
            app = validate_installed_app(
                installed_app_path, require_space=require_space,
                require_bundled_python=require_bundled_python)
            profile = validate_isolated_profile(
                isolated_profile, receipt_root=root)
            port = validate_port(isolated_port)
            inputs = {
                "schema": "c22-runner-inputs-v1",
                "created_utc": utc_now(),
                "synthetic": synthetic,
                "userprofile": ordinary_userprofile(),
                "live_index_forbidden": forbidden_live_path_string(),
                "opened_live_index": False,
                "hashed_live_index": False,
                "installed_app": app,
                "package": package,
                "isolated_profile": str(profile),
                "isolated_port": port,
                "manifest": {
                    "path": str(manifest_path) if manifest_path else None,
                    "sealed_by": manifest.get("sealed_by"),
                    "expected_package_sha256": manifest.get(
                        "expected_package_sha256"),
                    "candidate_sha": manifest.get("candidate_sha"),
                    "installer_source_sha": manifest.get("installer_source_sha"),
                },
            }
            (root / "inputs.json").write_text(
                json.dumps(inputs, indent=2) + "\n", encoding="utf-8")
            (root / "manifest.used.json").write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            runner._write_summary(status="prepared", inputs=inputs)
            runner.record_event("prepared", inputs=inputs)
        except BaseException as exc:
            runner.record_event("prepare_failed", error=f"{type(exc).__name__}: {exc}")
            runner._write_summary(status="prepare_failed",
                                  error=f"{type(exc).__name__}: {exc}")
            raise
        return runner

    @classmethod
    def prepare_before_install(
            cls, *, receipt_root: str | Path,
            intended_app_path: str | Path,
            package_path: str | Path, package_sha256: str,
            isolated_profile: str | Path, isolated_port: Any,
            manifest_path: str | Path | None = None,
            synthetic: bool = False,
            require_space: bool = True,
            skip_ordinary_user_check: bool = False) -> "OperatorRunner":
        """Create a receipt before the app exists. Does not overwrite later."""
        root = validate_receipt_root(receipt_root)
        root.mkdir(parents=True, exist_ok=False)
        runner = cls(root, synthetic=synthetic)
        runner.commands_dir.mkdir()
        runner.artifacts_dir.mkdir()
        (root / "profiles").mkdir()
        (root / "injection").mkdir()
        (root / "evidence").mkdir()
        (root / "fixtures").mkdir()
        try:
            if not synthetic and not skip_ordinary_user_check:
                validate_not_ordinary_user()
            manifest = load_manifest(manifest_path)
            if not synthetic:
                sealed = require_sealed_package_hash(manifest)
                if sealed != package_sha256.strip().lower():
                    raise C22ValidationError(
                        "operator package_sha256 does not match the sealed "
                        "manifest digest")
            package = validate_package(package_path, package_sha256)
            intended = validate_installed_app(
                intended_app_path, require_space=require_space,
                require_bundled_python=False, require_exists=False)
            profile = validate_isolated_profile(
                isolated_profile, receipt_root=root)
            port = validate_port(isolated_port)
            for name in CAPTURE_PROFILE_NAMES:
                (root / "profiles" / name).mkdir(parents=True, exist_ok=True)
            sealed = None
            if not synthetic:
                sealed = load_candidate_package_02()
                if package["sha256"] != sealed["package_sha256"]:
                    raise C22ValidationError(
                        "package sha256 does not match candidate-package-02")
                if package["bytes"] != sealed["package_bytes"]:
                    raise C22ValidationError(
                        "package bytes do not match candidate-package-02")
            inputs = {
                "schema": "c22-runner-inputs-v1",
                "created_utc": utc_now(),
                "synthetic": synthetic,
                "prepare_before_install": True,
                "userprofile": ordinary_userprofile(),
                "live_index_forbidden": forbidden_live_path_string(),
                "opened_live_index": False,
                "hashed_live_index": False,
                "installed_app": intended,
                "package": package,
                "isolated_profile": str(profile),
                "isolated_port": port,
                "mode": "source_runtime_synthetic" if synthetic else "installed",
                "profile_dirs_prepared": True,
                "candidate_package_02": None if synthetic else {
                    "installer_source_sha": sealed["installer_source_sha"],
                    "package_sha256": sealed["package_sha256"],
                    "package_bytes": sealed["package_bytes"],
                    "invented": False,
                },
                "manifest": {
                    "path": str(manifest_path) if manifest_path else None,
                    "sealed_by": manifest.get("sealed_by"),
                    "expected_package_sha256": manifest.get(
                        "expected_package_sha256"),
                    "candidate_sha": manifest.get("candidate_sha"),
                    "installer_source_sha": manifest.get("installer_source_sha"),
                },
            }
            (root / "inputs.json").write_text(
                json.dumps(inputs, indent=2) + "\n", encoding="utf-8")
            (root / "manifest.used.json").write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            runner._write_summary(status="prepared_before_install", inputs=inputs)
            runner.record_event("prepared_before_install", inputs=inputs)
        except BaseException as exc:
            runner.record_event("prepare_failed", error=f"{type(exc).__name__}: {exc}")
            runner._write_summary(status="prepare_failed",
                                  error=f"{type(exc).__name__}: {exc}")
            raise
        return runner

    @classmethod
    def continue_existing(
            cls, *, receipt_root: str | Path,
            installed_app_path: str | Path | None = None,
            package_path: str | Path | None = None,
            package_sha256: str | None = None,
            isolated_profile: str | Path | None = None,
            isolated_port: Any = None,
            synthetic: bool | None = None,
            require_space: bool = True,
            require_bundled_python: bool = True) -> "OperatorRunner":
        """Reuse a prepared receipt. Bindings must match; completed scenarios stay."""
        root = as_absolute(receipt_root, label="receipt_root")
        inputs_path = root / "inputs.json"
        if not inputs_path.is_file():
            raise C22ValidationError(
                f"cannot continue: receipt inputs.json missing at {root}")
        stored = json.loads(inputs_path.read_text(encoding="utf-8"))
        stored_synthetic = bool(stored.get("synthetic"))
        if synthetic is not None and bool(synthetic) != stored_synthetic:
            raise C22ValidationError(
                "refusing to promote or demote a receipt between synthetic "
                "and installed modes")
        stored_user = stored.get("userprofile")
        current_user = ordinary_userprofile()
        if stored_user and os.path.normcase(str(stored_user)) != os.path.normcase(
                str(current_user)):
            raise C22ValidationError(
                "continue-existing-receipt user mismatch: "
                f"receipt={stored_user!r} current={current_user!r}")
        stored_mode = stored.get("mode")
        expected_mode = "source_runtime_synthetic" if stored_synthetic else "installed"
        if stored_mode and stored_mode != expected_mode:
            raise C22ValidationError(
                f"continue-existing-receipt mode mismatch: {stored_mode}")
        runner = cls(root, synthetic=stored_synthetic)
        runner.commands_dir.mkdir(exist_ok=True)
        runner.artifacts_dir.mkdir(exist_ok=True)
        (root / "profiles").mkdir(exist_ok=True)
        (root / "evidence").mkdir(exist_ok=True)

        def _must_match(label: str, expected: Any, actual: Any) -> None:
            if actual is None:
                return
            if str(expected) != str(actual):
                raise C22ValidationError(
                    f"continue-existing-receipt binding mismatch for {label}: "
                    f"receipt={expected!r} supplied={actual!r}")

        if package_sha256 is not None:
            _must_match("package_sha256",
                        (stored.get("package") or {}).get("sha256"),
                        package_sha256.strip().lower())
        if package_path is not None:
            stored_pkg = stored.get("package") or {}
            _must_match("package_path",
                        stored_pkg.get("path"),
                        str(as_absolute(package_path, label="package_path")))
            again = validate_package(
                package_path, stored_pkg.get("sha256") or package_sha256)
            if stored_pkg.get("bytes") is not None and again["bytes"] != stored_pkg.get("bytes"):
                raise C22ValidationError("package bytes changed since prepare")
            if stored_pkg.get("sha256") and again["sha256"] != stored_pkg.get("sha256"):
                raise C22ValidationError("package content hash changed since prepare")
        if isolated_profile is not None:
            _must_match("isolated_profile",
                        stored.get("isolated_profile"),
                        str(as_absolute(isolated_profile, label="isolated_profile")))
        if isolated_port is not None:
            _must_match("isolated_port",
                        stored.get("isolated_port"),
                        validate_port(isolated_port))
        if installed_app_path is not None:
            stored_app = stored.get("installed_app") or {}
            app_path = Path(installed_app_path)
            app_now_present = app_path.is_dir() and (app_path / "server.py").is_file()
            need_bundled = require_bundled_python
            if app_now_present and not stored_synthetic:
                need_bundled = True
            supplied = validate_installed_app(
                installed_app_path, require_space=require_space,
                require_bundled_python=need_bundled,
                require_exists=app_now_present or not stored.get(
                    "prepare_before_install"),
            )
            _must_match("installed_app_path",
                        stored_app.get("path"),
                        supplied["path"])
            if supplied.get("present"):
                from .launcher import inventory_installed
                inventory = inventory_installed(Path(supplied["path"]))
                if not (inventory.get("files") or {}).get("server.py", {}).get("present"):
                    raise C22ValidationError(
                        "installed server.py missing on continue")
                stored["installed_app"] = supplied
                stored["installed_inventory"] = inventory
                inputs_path.write_text(
                    json.dumps(stored, indent=2) + "\n", encoding="utf-8")
        runner.record_event("continued_existing_receipt",
                            receipt_root=str(root),
                            completed_scenarios=runner.completed_scenario_ids())
        return runner

    def completed_scenario_ids(self) -> list[str]:
        evidence = self.receipt_root / "evidence"
        found = []
        if not evidence.is_dir():
            return found
        for scenario_id in SCENARIO_IDS:
            path = evidence / f"{scenario_id}.json"
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("id") == scenario_id and data.get("status"):
                found.append(scenario_id)
        return found

    def load_inputs(self) -> dict[str, Any]:
        return json.loads((self.receipt_root / "inputs.json").read_text(
            encoding="utf-8"))

    def record_event(self, kind: str, **payload: Any) -> dict[str, Any]:
        event = {"utc": utc_now(), "kind": kind, **omit_raw_bytes(payload)}
        with self.journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, default=str) + "\n")
        return event

    def run_command(self, argv: list[str], *, name: str,
                    env: Mapping[str, str] | None = None,
                    cwd: str | Path | None = None,
                    timeout: float | None = None,
                    text: bool = True,
                    input_bytes: bytes | None = None,
                    check_isolation_flags: bool = False) -> dict[str, Any]:
        if any(str(FORBIDDEN_PORT) == part for part in argv):
            raise C22ValidationError("refusing a command that names port 5179")
        stamp = utc_now().replace(":", "").replace("+00:00", "Z")
        prefix = self.commands_dir / f"{stamp}-{name}"
        stdout_path = prefix.with_suffix(".stdout.log")
        stderr_path = prefix.with_suffix(".stderr.log")
        record: dict[str, Any] = {
            "name": name,
            "argv": list(argv),
            "cwd": str(cwd or self.receipt_root),
            "started_utc": utc_now(),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "synthetic": self.synthetic,
        }
        merged = os.environ.copy()
        merged.pop("ANTHROPIC_API_KEY", None)
        if env:
            merged.update(env)
            merged.pop("ANTHROPIC_API_KEY", None)
        try:
            started = time.time()
            with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
                proc = subprocess.Popen(
                    argv, cwd=str(cwd or self.receipt_root), env=merged,
                    stdout=out, stderr=err,
                    stdin=subprocess.PIPE if input_bytes is not None else None)
                record["child"] = identity_for_pid(proc.pid)
                try:
                    proc.communicate(input=input_bytes, timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
                    record["timeout"] = True
                record["exit"] = proc.returncode
                record["finished_utc"] = utc_now()
                record["wall_seconds"] = round(time.time() - started, 3)
        except BaseException as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            record["finished_utc"] = utc_now()
            record["exit"] = None
            self.record_event("command_failed", **record)
            self._hash_command_logs(record, stdout_path, stderr_path)
            (prefix.with_suffix(".json")).write_text(
                json.dumps(record, indent=2, default=str) + "\n",
                encoding="utf-8")
            raise
        self._hash_command_logs(record, stdout_path, stderr_path)
        (prefix.with_suffix(".json")).write_text(
            json.dumps(record, indent=2, default=str) + "\n", encoding="utf-8")
        self.record_event("command", **record)
        return record

    def plan_inno(self, manifest: dict[str, Any], *,
                  execute: bool = False) -> dict[str, Any]:
        inputs = self.load_inputs()
        package = inputs["package"]["path"]
        app = inputs["installed_app"]["path"]
        profile = inputs["isolated_profile"]
        port = inputs["isolated_port"]
        template = list(manifest.get("inno_isolated_args_template") or [])
        formatted = []
        for part in template:
            formatted.append(part.format(
                installed_app_path=app,
                isolated_profile=profile,
                isolated_port=port,
            ))
        extra = []
        joined = " ".join(formatted).upper()
        if INNO_NOCLOSE_FLAG not in joined:
            extra.append(INNO_NOCLOSE_FLAG)
        if INNO_NORESTARTAPPS_FLAG not in joined:
            extra.append(INNO_NORESTARTAPPS_FLAG)
        argv = [package, *formatted, *extra]
        validate_inno_argv(argv)
        plan = {
            "argv": argv,
            "execute": False,
            "reason": "Inno is an operator step; this kit does not auto-run it",
            "required_close_switches": [INNO_NOCLOSE_FLAG, INNO_NORESTARTAPPS_FLAG],
        }
        self.record_event("inno_plan", **plan)
        if execute:
            if self.synthetic:
                raise C22ValidationError(
                    "refusing Inno execution during a synthetic instrument check")
            raise C22ValidationError(
                "Inno execution is reserved for Ryan's throwaway session after "
                "Astra seals the kit. This worker/run must not start the installer.")
        return plan

    def refuse_default_helper(self, path: str | Path) -> None:
        name = Path(path).name.lower()
        if name in {"start_server.ps1", "start_server.bat", "launch.bat"}:
            raise C22ValidationError(
                f"refusing production default helper {name}")

    def hash_tree(self, root: Path, *, name: str) -> dict[str, Any]:
        files = []
        for path in sorted(Path(root).rglob("*")):
            if path.is_file():
                files.append(file_record(path, root=root))
        payload = {"root": str(root), "files": files, "name": name,
                   "utc": utc_now()}
        dest = self.artifacts_dir / f"{name}.files.json"
        dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        payload["manifest_sha256"] = sha256_file(dest)
        self.record_event("tree_hash", name=name, path=str(dest),
                          manifest_sha256=payload["manifest_sha256"],
                          file_count=len(files))
        return payload

    def _hash_command_logs(self, record: dict[str, Any],
                           stdout_path: Path, stderr_path: Path) -> None:
        for key, path in (("stdout", stdout_path), ("stderr", stderr_path)):
            if path.is_file():
                record[f"{key}_sha256"] = sha256_file(path)
                record[f"{key}_bytes"] = path.stat().st_size
            else:
                record[f"{key}_sha256"] = None
                record[f"{key}_bytes"] = 0

    def _write_summary(self, **payload: Any) -> None:
        current: dict[str, Any] = {}
        if self.summary_path.exists():
            try:
                current = json.loads(self.summary_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                current = {"corrupt_previous": True}
        current.update(payload)
        current["updated_utc"] = utc_now()
        current["receipt_root"] = str(self.receipt_root)
        self.summary_path.write_text(
            json.dumps(current, indent=2, default=str) + "\n", encoding="utf-8")


def missing_required(data: Mapping[str, Any]) -> list[str]:
    return [key for key in REQUIRED_OPERATOR_INPUTS if not data.get(key)]
