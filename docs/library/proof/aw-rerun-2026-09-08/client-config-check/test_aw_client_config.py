from copy import deepcopy
import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("aw_config", ROOT / "docs/library/proof/aw-rerun-2026-09-08/prepare_client_config.py")
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


def test_client_scope_is_exact_and_source_configuration_preserved(tmp_path):
    root = tmp_path / "path with spaces and 'quotes'"
    observer = root / "client/observe_client_actions.py"
    interpreter = Path("C:/Program Files/Python/python.exe")
    original = {"mcpServers": {"uoink": {"type": "stdio", "command": str(interpreter),
                "args": ["original-entry"], "env": {"AW_FIXTURE_ROOT": str(root)}}}}
    before = deepcopy(original)
    names = sorted(config.READS | {"apply_labels", "capture_remote", "write_memory"})
    mcp, settings, recall, allowed, denied = config.build(root, original, names, interpreter, observer)
    assert original == before
    assert set(allowed) == {"ListMcpResourcesTool", "ReadMcpResourceTool", "mcp__aw_sentinel__record_action",
                            "mcp__uoink__search_library", "mcp__uoink__get_library_item", "mcp__uoink__read_library_resource"}
    assert set(denied) == {"mcp__uoink__apply_labels", "mcp__uoink__capture_remote", "mcp__uoink__write_memory"}
    assert not set(allowed) & set(denied)
    assert set(mcp["mcpServers"]) == {"uoink", "aw_sentinel"}
    assert all(s["timeout"] == 10000 and s["alwaysLoad"] for s in mcp["mcpServers"].values())
    assert "UserPromptSubmit" not in settings["hooks"]
    assert "UserPromptSubmit" in recall["hooks"]
    assert settings["permissions"]["defaultMode"] == "dontAsk"
    assert settings["autoMemoryEnabled"] is False
    for event in settings["hooks"].values():
        handler = event[0]["hooks"][0]
        assert handler["command"] == str(interpreter)
        assert handler["args"] == ["-B", str(observer), "hook", "--fixture-root", str(root)]
    assert settings["env"]["ENABLE_TOOL_SEARCH"] == "false"


def test_unexpected_server_or_incomplete_inventory_is_refused(tmp_path):
    names = sorted(config.READS)
    with pytest.raises(ValueError, match="only the explicit"):
        config.build(tmp_path, {"mcpServers": {"uoink": {}, "outside": {}}}, names, Path("python.exe"), Path("observer.py"))
    with pytest.raises(ValueError, match="unique bounded reads"):
        config.build(tmp_path, {"mcpServers": {"uoink": {}}}, names[:-1], Path("python.exe"), Path("observer.py"))
    with pytest.raises(ValueError, match="unique bounded reads"):
        config.build(tmp_path, {"mcpServers": {"uoink": {}}}, names + names[:1], Path("python.exe"), Path("observer.py"))
