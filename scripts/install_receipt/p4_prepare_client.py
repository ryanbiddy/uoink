"""Freeze disposable Claude Code configuration. Starts no client or model.

Native resource tools, bounded reads and an inert sentinel only. Explicit
deny lists, isolated CLAUDE_CONFIG_DIR, usage credits off, no API key.
Ordinary and Recall launches are separate. Credentials are neither copied
nor inspected.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from p4_common import (
    IsolationError,
    add_common_args,
    bind_from_args,
    isolation_env,
    save_json_exclusive,
    sha_file,
)
from p4_observe_actions import SENTINEL_TOOL

BUILTINS = ["ListMcpResourcesTool", "ReadMcpResourceTool"]
READS = {"search_library", "get_library_item", "read_library_resource"}


def build(root: Path, original: dict, names: list[str], interpreter: Path, observer: Path,
          profile: Path, port: int) -> tuple:
    if not READS.issubset(set(names)) or len(names) != len(set(names)):
        raise IsolationError("staged inventory must contain unique bounded reads")
    config = deepcopy(original)
    servers = set(config.get("mcpServers", {}))
    if servers - {"uoink"}:
        raise IsolationError("only the explicit uoink fixture may be inherited")
    if "uoink" not in servers:
        raise IsolationError("uoink fixture server missing")
    server = config["mcpServers"]["uoink"]
    server.update(timeout=10000, alwaysLoad=True)
    environment = deepcopy(server.get("env") or {})
    environment.update(
        P4_FIXTURE_ROOT=str(root),
        P4_ISOLATED_PROFILE=str(profile),
        P4_ISOLATED_PORT=str(port),
        MCP_TIMEOUT="10000",
        ENABLE_TOOL_SEARCH="false",
        DISABLE_AUTOUPDATER="1",
        CLAUDE_CODE_DISABLE_AUTO_MEMORY="1",
        CLAUDE_CONFIG_DIR=str(root / "client" / "claude-config"),
    )
    if environment.get("ANTHROPIC_API_KEY"):
        raise IsolationError("API key forbidden")
    server["env"] = deepcopy(environment)
    config["mcpServers"]["p4_sentinel"] = {
        "type": "stdio", "command": str(interpreter), "timeout": 10000, "alwaysLoad": True,
        "args": [
            str(root / "kit" / "p4_stdio_tap.py"),
            "--isolated-profile", str(profile),
            "--isolated-port", str(port),
            "--fixture-root", str(root),
            "--record-dir", str(root / "records" / "sentinel"),
            "--cwd", str(root / "client"),
            "--route-label", "sentinel",
            "--", str(interpreter), "-B", "-s", "-P", str(observer), "sentinel",
            "--fixture-root", str(root),
            "--isolated-profile", str(profile),
            "--isolated-port", str(port),
        ],
        "env": deepcopy(environment),
    }
    allowed = BUILTINS + ["mcp__uoink__" + n for n in sorted(READS)] + [SENTINEL_TOOL]
    denied = ["mcp__uoink__" + n for n in sorted(set(names) - READS)]
    handler = {
        "type": "command", "command": str(interpreter),
        "args": ["-B", "-s", "-P", str(observer), "hook",
                 "--fixture-root", str(root),
                 "--isolated-profile", str(profile),
                 "--isolated-port", str(port)],
        "timeout": 5,
    }
    hooks = {name: [{"matcher": "*", "hooks": [deepcopy(handler)]}]
             for name in ("PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionDenied")}
    settings = {
        "env": environment,
        "autoMemoryEnabled": False,
        "permissions": {"allow": allowed, "deny": denied, "defaultMode": "dontAsk"},
        "hooks": hooks,
    }
    recall_settings = deepcopy(settings)
    recall_settings["hooks"]["UserPromptSubmit"] = [{"hooks": [{
        "type": "command", "command": str(interpreter),
        "args": ["-B", "-s", "-P", str(observer), "recall",
                 "--fixture-root", str(root),
                 "--isolated-profile", str(profile),
                 "--isolated-port", str(port)],
        "timeout": 4,
    }]}]
    # Claude command hooks consume one command string. Separate args fields are
    # not an execution contract; quote executable and arguments together.
    for document in (settings, recall_settings):
        for groups in document["hooks"].values():
            for group in groups:
                for hook in group["hooks"]:
                    argv = [hook["command"], *hook.pop("args", [])]
                    hook["command"] = subprocess.list2cmdline([str(part).replace("\\", "/") for part in argv])
    return config, settings, recall_settings, allowed, denied


def validate_original_config(config: dict, binding: dict) -> None:
    server = (config.get("mcpServers") or {}).get("uoink") or {}
    argv = server.get("args") or []
    try:
        command = argv[argv.index("--") + 1:]
        route = argv[argv.index("--route-label") + 1]
        entry = str(Path(binding["installed_app"]) / "uoink_mcp.py")
        if route != "original-installed" or entry not in command:
            raise ValueError("original entry/route missing")
        if command[0] != binding["installed_interpreter"] or server.get("command") != binding["installed_interpreter"]:
            raise ValueError("interpreter differs")
        for flag, value in (("--isolated-profile", binding["isolated_profile"]),
                            ("--isolated-port", str(binding["isolated_port"]))):
            if command.count(flag) != 1 or command[command.index(flag)+1] != value:
                raise ValueError("child isolation differs")
    except (ValueError, IndexError, KeyError) as exc:
        raise IsolationError("original client configuration binding failed") from exc


def main(argv=None):
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    parser.add_argument("--tool-names-json", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        binding = bind_from_args(args)
    except IsolationError as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}), file=sys.stderr)
        return 2
    if os.environ.get("ANTHROPIC_API_KEY"):
        print(json.dumps({"status": "refused", "error": "ANTHROPIC_API_KEY must be absent"}), file=sys.stderr)
        return 2
    root = Path(binding["isolated_profile"])
    preparation = json.loads((root / "preparation.json").read_text(encoding="utf-8"))
    prompt = json.loads((root / "prompt-preparation.json").read_text(encoding="utf-8"))
    if prompt.get("apply_enabled") is not False:
        raise IsolationError("prompt fixture apply flag invalid")
    original_path = root / "mcp.json"
    if sha_file(original_path) != preparation.get("mcp_config_sha256"):
        raise IsolationError("original configuration changed")
    original = json.loads(original_path.read_text(encoding="utf-8"))
    validate_original_config(original, binding)
    client = root / "client"
    names = [
        "mcp-client.json", "settings.json", "settings-recall.json",
        "launch.json", "launch-recall.json", "client-config-preparation.json",
    ]
    if any((client / n).exists() for n in names):
        raise IsolationError("prepared client directory must have fresh output names")
    observer = client / "observe_client_actions.py"
    shutil.copyfile(_HERE / "p4_observe_actions.py", observer)
    config_dir = client / "claude-config"
    config_dir.mkdir(parents=True, exist_ok=True)
    # Empty isolated CLAUDE_CONFIG_DIR. Do not copy or inspect credentials.
    if any(config_dir.iterdir()):
        raise IsolationError("CLAUDE_CONFIG_DIR must start empty; credentials were not copied")
    if args.tool_names_json:
        names_list = json.loads(args.tool_names_json.read_text(encoding="utf-8"))
    else:
        from p4_common import EXPECTED_STDIO_TOOLS
        names_list = list(EXPECTED_STDIO_TOOLS)
    interpreter = Path(binding["installed_interpreter"])
    config, settings, recall, allowed, denied = build(
        root, original, names_list, interpreter, observer,
        Path(binding["isolated_profile"]), binding["isolated_port"],
    )
    save_json_exclusive(client / "mcp-client.json", config)
    save_json_exclusive(client / "settings.json", settings)
    save_json_exclusive(client / "settings-recall.json", recall)
    session_id = str(uuid.uuid4())
    recall_session = str(uuid.uuid4())
    env = isolation_env(binding, extra={"route_label": "client-ordinary"})
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    base = [
        "--restricted", "--strict-mcp-config", "--no-chrome", "--permission-mode", "dontAsk",
        "--tools", ",".join(BUILTINS),
        "--allowedTools", ",".join(allowed),
        "--disallowedTools", ",".join(denied),
        "--mcp-config", str(client / "mcp-client.json"),
    ]
    ordinary = {
        "cwd": str(client),
        "session_id": session_id,
        "claude_config_dir": str(config_dir),
        "args": base + [
            "--settings", str(client / "settings.json"),
            "--session-id", session_id,
            "--debug-file", str(client / "claude-debug.log"),
        ],
        "interactive_extra_args": ["--ax-screen-reader"],
        "print_extra_args": ["--print", "--verbose", "--output-format", "stream-json",
                             "--include-hook-events"],
        "environment": {**settings["env"], "CLAUDE_CONFIG_DIR": str(config_dir)},
        "required_authentication": "claude.ai subscription; verify immediately before launch",
        "usage_credits": "off; operator must confirm; no paid API fallback",
        "no_client_started": True,
        "credentials_copied": False,
        "credentials_inspected": False,
        "normal_client_settings_required": False,
        "route_label": "ordinary",
        "stream_collection": {
            "stdout": str(client / "claude-stream.jsonl"),
            "stderr": str(client / "claude-stream.stderr.log"),
            "print_command_shape": (
                "claude " + " ".join(base + [
                    "--settings", str(client / "settings.json"),
                    "--session-id", session_id,
                    "--print", "--verbose", "--output-format", "stream-json",
                    "--include-hook-events",
                ])
                + f" 1> {client / 'claude-stream.jsonl'} 2> {client / 'claude-stream.stderr.log'}"
            ),
            "operator_must_capture_complete_stream": True,
            "this_worker_does_not_start_client": True,
        },
    }
    recall_launch = deepcopy(ordinary)
    recall_launch.update({
        "session_id": recall_session,
        "route_label": "recall",
        "args": base + [
            "--settings", str(client / "settings-recall.json"),
            "--session-id", recall_session,
            "--debug-file", str(client / "claude-debug-recall.log"),
        ],
    })
    save_json_exclusive(client / "launch.json", ordinary)
    save_json_exclusive(client / "launch-recall.json", recall_launch)
    isolated_launch = deepcopy(ordinary)
    isolated_launch["environment"] = {
        **ordinary["environment"], **{k: env[k] for k in (
            "LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "CLAUDE_CONFIG_DIR",
            "P4_ISOLATED_PROFILE", "P4_ISOLATED_PORT", "P4_FIXTURE_ROOT",
            "UOINK_ISOLATED_PROFILE", "UOINK_ISOLATED_PORT", "UOINK_INDEX_PATH",
        ) if k in env},
    }
    save_json_exclusive(client / "launch-isolated.json", isolated_launch)
    paths = [client / n for n in (
        "mcp-client.json", "settings.json", "settings-recall.json",
        "launch.json", "launch-recall.json", "launch-isolated.json",
        "observe_client_actions.py",
    )]
    receipt = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "configuration prepared; no client/model run",
        "product_route": "original-installed",
        "original_config_sha256": sha_file(original_path),
        "session_id": session_id,
        "recall_session_id": recall_session,
        "claude_config_dir": str(config_dir),
        "claude_config_dir_empty": True,
        "credentials_copied": False,
        "credentials_inspected": False,
        "usage_credits_off": "operator_must_confirm",
        "apply_enabled": False,
        "staged_tool_inventory": names_list,
        "allowed_tools": allowed,
        "denied_tools": denied,
        "hashes": {p.name: sha_file(p) for p in paths},
        "limits": [
            "Authentication and actual client execution are Ryan's session",
            "CLI settings must still be observed as loaded",
            "Raw full client stream required in addition to hooks",
            "Do not set ANTHROPIC_API_KEY",
            "Normal client settings are not required or edited",
            "X HTTP 403 stays blocked; D_FCYsshMI4 player jump is optional; apply false",
            "No speaker-accuracy claim; Phase 5 Part B remains deferred",
        ],
        "candidate": preparation.get("package_manifest", {}).get("installer_source_sha"),
    }
    save_json_exclusive(client / "client-config-preparation.json", receipt)
    launch_script = client / "ryan-stream-capture.ps1"
    launch_script.write_text(
        "\n".join([
            "$ErrorActionPreference = 'Stop'",
            "if ($env:ANTHROPIC_API_KEY) { throw 'ANTHROPIC_API_KEY must be absent' }",
            f"$env:CLAUDE_CONFIG_DIR = '{config_dir}'",
            "$env:DISABLE_AUTOUPDATER = '1'",
            "$env:CLAUDE_CODE_DISABLE_AUTO_MEMORY = '1'",
            "# Ryan: confirm claude.ai subscription and usage credits OFF, then:",
            f"# Ordinary stream: see launch-isolated.json stream_collection after sealing",
            f"# Capture complete stdout JSONL and stderr. Do not copy credentials.",
            f"Write-Output 'prepared; this script does not start claude'",
            "",
        ]),
        encoding="utf-8", newline="\n",
    )
    print(json.dumps({
        "status": receipt["status"],
        "session_id": session_id,
        "recall_session_id": recall_session,
        "allowed_tool_count": len(allowed),
        "denied_tool_count": len(denied),
        "credentials_copied": False,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
