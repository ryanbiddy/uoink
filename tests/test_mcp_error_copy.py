"""Error text an AI client sees: plain, says what to do next, no file paths."""
import dataclasses

import uoink_mcp_tools as tools


def test_scrub_removes_paths_and_clips():
    text = tools._scrub_error_text(
        "could not open C:\\Users\\Someone\\AppData\\Local\\Uoink\\index.db and /home/sam/x/y.json\nline two")
    assert "Users" not in text and "/home/" not in text and "<path>" in text
    assert "\n" not in text
    assert len(tools._scrub_error_text("x" * 900)) <= 200


def test_unexpected_exception_has_no_path_and_a_next_step(monkeypatch):
    spec = tools.TOOL_REGISTRY["get_job_status"]

    def boom(_args):
        raise RuntimeError("disk error at E:\\Private Folder\\Uoink\\jobs.db")

    patched = dataclasses.replace(spec, handler=boom) if dataclasses.is_dataclass(spec) else spec
    monkeypatch.setitem(tools.TOOL_REGISTRY, "get_job_status", patched)
    result = tools.call_tool("get_job_status", {"job_id": "abc"})
    assert result["ok"] is False
    assert "Private Folder" not in result["error"] and "<path>" in result["error"]
    assert "try again" in result["error"]


def test_handler_error_strings_lose_paths(monkeypatch):
    spec = tools.TOOL_REGISTRY["get_job_status"]
    patched = dataclasses.replace(
        spec, handler=lambda _a: {"ok": False, "error": "failed: /Users/sam/Library/Uoink/a.db"})
    monkeypatch.setitem(tools.TOOL_REGISTRY, "get_job_status", patched)
    result = tools.call_tool("get_job_status", {})
    assert result["error"] == "failed: <path>"


def test_missing_input_messages_say_what_to_pass():
    import server
    tools.bind_backend(server)
    assert "words to search for" in tools.call_tool("search_uoinks", {})["error"]
    assert "capture call returned" in tools.call_tool("get_job_status", {"job_id": "zz"})["error"]
    assert "YouTube playlist URL" in tools.call_tool("uoink_playlist", {"url": "x"})["error"]
