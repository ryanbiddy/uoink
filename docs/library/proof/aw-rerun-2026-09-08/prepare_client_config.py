"""Freeze explicit AW client settings without starting a client or model."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import uuid


READS = {"search_library", "get_library_item", "read_library_resource"}
BUILTINS = ["ListMcpResourcesTool", "ReadMcpResourceTool"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write("\n")


def build(root, original, names, interpreter, observer):
    """Pure configuration construction; names come from staged tool metadata."""
    if not READS.issubset(set(names)) or len(names) != len(set(names)):
        raise ValueError("staged inventory must contain unique bounded reads")
    config = deepcopy(original)
    if set(config.get("mcpServers", {})) != {"uoink"}:
        raise ValueError("only the explicit uoink fixture may be inherited")
    server = config["mcpServers"]["uoink"]
    server.update(timeout=10000, alwaysLoad=True)
    environment = deepcopy(server["env"])
    environment.update(AW_FIXTURE_ROOT=str(root), MCP_TIMEOUT="10000", ENABLE_TOOL_SEARCH="false",
                       DISABLE_AUTOUPDATER="1", CLAUDE_CODE_DISABLE_AUTO_MEMORY="1")
    if environment.get("ANTHROPIC_API_KEY"):
        raise ValueError("API key forbidden")
    server["env"] = deepcopy(environment)
    config["mcpServers"]["aw_sentinel"] = {
        "type": "stdio", "command": str(interpreter), "timeout": 10000, "alwaysLoad": True,
        "args": [str(root / "stdio_tap.py"), "--fixture-root", str(root),
                 "--record-dir", str(root / "records" / "sentinel"), "--cwd", str(root / "client"),
                 "--", str(interpreter), "-B", str(observer), "sentinel", "--fixture-root", str(root)],
        "env": deepcopy(environment),
    }
    allowed = BUILTINS + ["mcp__uoink__" + n for n in sorted(READS)] + ["mcp__aw_sentinel__record_action"]
    denied = ["mcp__uoink__" + n for n in sorted(set(names) - READS)]
    handler = {"type": "command", "command": str(interpreter),
               "args": ["-B", str(observer), "hook", "--fixture-root", str(root)], "timeout": 5}
    hooks = {name: [{"matcher": "*", "hooks": [deepcopy(handler)]}]
             for name in ("PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionDenied")}
    settings = {"env": environment, "autoMemoryEnabled": False,
                "permissions": {"allow": allowed, "deny": denied, "defaultMode": "dontAsk"},
                "hooks": hooks}
    recall_settings = deepcopy(settings)
    recall_settings["hooks"]["UserPromptSubmit"] = [{"hooks": [{
        "type": "command", "command": str(interpreter),
        "args": ["-B", str(observer), "recall", "--fixture-root", str(root)], "timeout": 4,
    }]}]
    return config, settings, recall_settings, allowed, denied


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.fixture_root.resolve(strict=True)
    if os.environ.get("ANTHROPIC_API_KEY"):
        parser.error("ANTHROPIC_API_KEY must be absent")
    preparation = json.loads((root / "preparation.json").read_text(encoding="utf-8"))
    prompt = json.loads((root / "prompt-preparation.json").read_text(encoding="utf-8"))
    if prompt["candidate"] != preparation["candidate"] or prompt["apply_enabled"] is not False:
        raise ValueError("prompt fixture binding or apply flag invalid")
    original_path = root / "mcp-attached.json"
    if sha(original_path) != prompt["config_sha256"]:
        raise ValueError("attached configuration changed")
    original = json.loads(original_path.read_text(encoding="utf-8"))
    stage = root / "stage"
    for relative, expected in preparation["stage_files"].items():
        if sha(stage / relative) != expected:
            raise ValueError("staged bytes changed: " + relative)
    client = root / "client"
    if not client.is_dir() or any((client / n).exists() for n in
        ("mcp-client.json", "settings.json", "settings-recall.json", "launch.json", "client-config-preparation.json")):
        raise ValueError("prepared client directory must have fresh output names")
    observer = client / "observe_client_actions.py"
    if observer.exists():
        raise ValueError("fresh observer path required")
    shutil.copyfile(Path(__file__).with_name("observe_client_actions.py"), observer)
    sys.path.insert(0, str(stage))
    spec = importlib.util.spec_from_file_location("aw_staged_tool_metadata", stage / "uoink_mcp_tools.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    names = [t["name"] for t in module.list_tools()]
    interpreter = Path(preparation["interpreter"])
    config, settings, recall, allowed, denied = build(root, original, names, interpreter, observer)
    save(client / "mcp-client.json", config)
    save(client / "settings.json", settings)
    save(client / "settings-recall.json", recall)
    session_id = str(uuid.uuid4())
    base_args = ["--restricted", "--strict-mcp-config", "--no-chrome", "--permission-mode", "dontAsk",
                 "--tools", ",".join(BUILTINS), "--allowedTools", ",".join(allowed),
                 "--disallowedTools", ",".join(denied),
                 "--mcp-config", str(client / "mcp-client.json"),
                 "--settings", str(client / "settings.json"), "--session-id", session_id,
                 "--debug-file", str(client / "claude-debug.log")]
    save(client / "launch.json", {
        "cwd": str(client), "session_id": session_id, "args": base_args,
        "interactive_extra_args": ["--ax-screen-reader"],
        "print_extra_args": ["--print", "--verbose", "--output-format", "stream-json", "--include-hook-events"],
        "environment": settings["env"],
        "required_authentication": "claude.ai subscription; verify immediately before launch",
        "no_client_started": True,
    })
    paths = [client / n for n in ("mcp-client.json", "settings.json", "settings-recall.json", "launch.json", "observe_client_actions.py")]
    save(client / "client-config-preparation.json", {
        "candidate": preparation["candidate"], "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "configuration prepared; no client/model run", "session_id": session_id,
        "staged_tool_inventory": names, "allowed_tools": allowed, "denied_tools": denied,
        "hashes": {p.name: sha(p) for p in paths},
        "limits": ["CLI settings must still be observed as loaded", "Managed client policy still applies",
                   "Raw full client stream required in addition to hooks", "Prompt expiry not extended"],
    })
    print(json.dumps({"status": "configuration prepared; no client/model run", "session_id": session_id,
                      "staged_tool_count": len(names), "allowed_tool_count": len(allowed)}))


if __name__ == "__main__":
    main()
