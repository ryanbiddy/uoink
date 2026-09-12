"""Ryan's guarded P4 command driver; system Python -I -S, never a model by default."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import p4_common as common
from p4_session import spawn_owned

TOOLS = {"prepare": "p4_prepare_fixture.py", "check": "p4_stdio_check.py",
         "prepare-client": "p4_prepare_client.py", "collect": "p4_collect_evidence.py"}


def child_arguments(args) -> list[str]:
    result = []
    for name in ("isolated_profile", "isolated_port", "installed_app", "installed_interpreter",
                 "package_manifest", "receipt_root", "forbid_checkout", "package_path",
                 "source_bindings", "runtime_mode"):
        value = getattr(args, name, None)
        if value is not None:
            result.extend(["--" + name.replace("_", "-"), str(value)])
    return result


def require_client_acknowledgements(args) -> None:
    if not args.subscription_confirmed or not args.usage_credits_off:
        raise common.IsolationError("Ryan must confirm subscription authentication and usage credits OFF")
    if not args.client_exe or args.client_exe.suffix.lower() != ".exe" or not args.client_exe.is_file():
        raise common.IsolationError("--client-exe must name the actual native Claude executable")
    if not args.prompt_file or not args.prompt_file.is_file():
        raise common.IsolationError("--prompt-file is required for the retained client input")
    if args.prompt_file.stat().st_size > 65536:
        raise common.IsolationError("client prompt exceeds 64 KiB")


def run(args) -> dict:
    common.require_no_api_key()
    if not sys.flags.no_site or not sys.flags.isolated:
        raise common.IsolationError("start the driver with system Python -I -S")
    if args.instrument_only or args.runtime_mode not in ("installed", "source-runtime"):
        raise common.IsolationError("driver requires explicit installed or source-runtime mode")
    if args.stage == "client":
        require_client_acknowledgements(args)
    # Only metadata is read here. The child tool validates installed provenance
    # after its automatically loaded guard is installed and proven below.
    binding = common.validate_isolation(
        isolated_profile=args.isolated_profile, isolated_port=args.isolated_port,
        receipt_root=args.receipt_root, installed_app=args.installed_app,
        installed_interpreter=args.installed_interpreter, package_manifest=args.package_manifest,
        forbid_checkout=args.forbid_checkout, runtime_mode="source-runtime", probe_runtime=False,
        package_path=args.package_path, source_bindings_path=args.source_bindings,
    )
    binding["runtime_mode"] = args.runtime_mode
    if args.runtime_mode == "installed" and any(value is None for value in
            (args.package_path, args.source_bindings, args.forbid_checkout)):
        raise common.IsolationError("installed driver requires package bytes, source bindings and forbidden checkout")
    profile = Path(binding["isolated_profile"])
    common.ensure_profile_dirs(profile)
    stage_name = args.stage + ("-" + args.client_route if args.stage == "client" else "")
    receipt_path = profile / ("operator-" + stage_name + ".json")
    out_path = profile / ("operator-" + stage_name + ".stdout")
    err_path = profile / ("operator-" + stage_name + ".stderr")
    if any(path.exists() for path in (receipt_path, out_path, err_path)):
        raise common.IsolationError("stage evidence already exists; a rerun needs a repair brief and new receipt")
    env = common.isolation_env(binding)
    command = [str(args.installed_interpreter), "-B", "-s", str(HERE / TOOLS[args.stage]),
               *child_arguments(args)] if args.stage in TOOLS else []
    cwd = profile
    if args.stage == "check":
        command.extend(["--route", "original-installed"])
    if args.stage == "collect":
        if not args.operator_json or not args.operator_json.is_file():
            raise common.IsolationError("collect requires --operator-json with actual observations or explicit empty object")
        command.extend(["--operator-json", str(args.operator_json)])
    if args.stage == "client":
        client = profile / "client"
        prep = json.loads((client / "client-config-preparation.json").read_text(encoding="utf8"))
        for name, digest in prep["hashes"].items():
            if common.sha_file(client / name) != digest:
                raise common.IsolationError("prepared client bytes changed: " + name)
        launch_file = client / ("launch-isolated.json" if args.client_route == "ordinary" else "launch-recall.json")
        launch = json.loads(launch_file.read_text(encoding="utf8"))
        from p4_prepare_client import validate_original_config
        config = json.loads((client / "mcp-client.json").read_text(encoding="utf8"))
        validate_original_config(config, binding)
        env.update(launch["environment"])
        env["CLAUDE_CONFIG_DIR"] = str(client / "claude-config")
        command = [str(args.client_exe), *launch["args"], "--print", "--verbose",
                   "--output-format", "stream-json", "--include-hook-events"]
        cwd = client
    record = {"utc": datetime.now(timezone.utc).isoformat(), "stage": stage_name,
              "runtime_mode": args.runtime_mode, "command": command, "installed_credit": False,
              "apply_enabled": False, "exit_code": None, "cleanup": None}
    guard_record = None
    owned = None
    safe_to_restore = True
    try:
        guard = common.write_guard(profile, binding)
        guard_record = common.install_guard_into_interpreter(args.installed_interpreter, guard,
                                                              installed_app=args.installed_app)
        record["guard_install"] = guard_record
        canary = common.prove_guard_canary(interpreter=args.installed_interpreter,
                                           env=env, profile=profile, cwd=profile)
        record["guard_canary"] = canary
        if not canary.get("refused"):
            raise common.IsolationError("actual interpreter did not automatically refuse the owned canary")
        with out_path.open("xb") as output, err_path.open("xb") as error:
            source = args.prompt_file.open("rb") if args.stage == "client" else open(os.devnull, "rb")
            try:
                owned = spawn_owned(command, cwd=cwd, env=env, stdin=source,
                                    stdout=output, stderr=error, label="p4-operator-" + stage_name)
                safe_to_restore = False
                record["pid"] = owned.popen.pid
                try:
                    record["exit_code"] = owned.wait(timeout=args.timeout_seconds)
                except subprocess.TimeoutExpired:
                    record["error"] = "stage deadline exceeded; retain failed outcome"
                finally:
                    record["cleanup"] = owned.terminate_tree(timeout=5)
                    safe_to_restore = bool(record["cleanup"].get("cleaned"))
            finally:
                source.close()
    except Exception as exc:
        record["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        if safe_to_restore:
            record["guard_restore"] = common.restore_guard(guard_record)
            if not record["guard_restore"].get("ok") or any(
                    row.get("action") == "left_modified" for row in record["guard_restore"].get("restored", [])):
                record["error"] = "guard restoration incomplete; retain receipt and do not start another stage"
        else:
            record["error"] = "child cleanup not affirmed; guard left installed for independent recovery review"
        record["outputs"] = {path.name: {"sha256": common.sha_file(path), "bytes": path.stat().st_size}
                             for path in (out_path, err_path) if path.is_file()}
        record["status"] = "completed_pending_review" if not record.get("error") and record["exit_code"] == 0 else "failed"
        common.save_json_exclusive(receipt_path, record)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=[*TOOLS, "client"])
    common.add_common_args(parser)
    parser.add_argument("--operator-json", type=Path)
    parser.add_argument("--client-exe", type=Path)
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--client-route", choices=["ordinary", "recall"], default="ordinary")
    parser.add_argument("--subscription-confirmed", action="store_true")
    parser.add_argument("--usage-credits-off", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args(argv)
    if not 1 <= args.timeout_seconds <= 1800:
        parser.error("timeout must be 1..1800 seconds")
    try:
        result = run(args)
    except common.IsolationError as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "completed_pending_review" else 1


if __name__ == "__main__":
    raise SystemExit(main())
