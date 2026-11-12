"""Error text an AI client sees: plain, says what to do next, no file paths."""
import dataclasses

import pytest

import uoink_mcp_tools as tools


def test_scrub_removes_paths_and_clips():
    text = tools._scrub_error_text(
        "could not open C:\\Users\\Someone\\AppData\\Local\\Uoink\\index.db and /home/sam/x/y.json\nline two")
    assert "Users" not in text and "/home/" not in text and "<path>" in text
    assert "\n" not in text
    assert len(tools._scrub_error_text("x" * 900)) <= 200


def test_scrub_keeps_urls():
    text = tools._scrub_error_text(
        "could not fetch https://example.com/home/page and http://example.test/Users/x")
    assert "https://example.com/home/page" in text
    assert "http://example.test/Users/x" in text
    assert "<path>" not in text


def test_unexpected_exception_has_no_path_and_a_next_step(monkeypatch):
    spec = tools.TOOL_REGISTRY["get_job_status"]

    def boom(_args):
        raise RuntimeError("disk error at E:\\Private Folder\\Uoink\\jobs.db")

    patched = dataclasses.replace(spec, handler=boom) if dataclasses.is_dataclass(spec) else spec
    monkeypatch.setitem(tools.TOOL_REGISTRY, "get_job_status", patched)
    result = tools.call_tool("get_job_status", {"job_id": "abc"})
    assert result["ok"] is False
    # No fragment of the path survives, not even the words after the space.
    for fragment in ("Private", "Folder", "jobs.db", "E:", "\\"):
        assert fragment not in result["error"], fragment
    assert result["error"] == ("That tool hit a problem and stopped: disk error at <path>. "
                               "Check that Uoink is running, then try again.")


def test_handler_error_strings_lose_paths(monkeypatch):
    spec = tools.TOOL_REGISTRY["get_job_status"]
    patched = dataclasses.replace(
        spec, handler=lambda _a: {"ok": False, "error": "failed: /Users/sam/Library/Uoink/a.db"})
    monkeypatch.setitem(tools.TOOL_REGISTRY, "get_job_status", patched)
    result = tools.call_tool("get_job_status", {})
    assert result["error"] == "failed: <path>"


# (error text, what the AI client sees, path pieces that must not survive)
PATH_CASES = [
    # Windows folders with spaces, and the sentence after the path survives.
    ("could not open C:\\Users\\Mary Anne\\AppData\\Local\\Uoink\\index.db while saving the queue",
     "could not open <path> while saving the queue", ["Mary", "Anne", "AppData", "index.db"]),
    ("at C:\\Program Files (x86)\\Uoink\\uoink.exe (code 5)",
     "at <path> (code 5)", ["Program", "x86", "uoink.exe"]),
    ("copy C:\\a\\Old Stuff\\b.db to E:\\Private Folder\\d.db failed",
     "copy <path> to <path> failed", ["Old", "Stuff", "b.db", "Private", "Folder", "d.db"]),
    ("cannot open (E:\\Data\\jobs.db) today", "cannot open (<path>) today", ["Data", "jobs.db"]),
    # Network shares (UNC), as typed and as repr() doubles them.
    ("share \\\\fileserver\\team share\\Uoink\\jobs.db is offline",
     "share <path> is offline", ["fileserver", "team", "jobs.db"]),
    ("share \\\\\\\\fileserver\\\\team share\\\\Uoink\\\\jobs.db is offline",
     "share <path> is offline", ["fileserver", "team", "jobs.db"]),
    # Quoted paths go whole, the way OSError writes them.
    ("[Errno 2] No such file or directory: 'C:\\\\Users\\\\Mary Anne\\\\My Notes\\\\x.db'",
     "[Errno 2] No such file or directory: <path>", ["Mary", "Anne", "My Notes", "x.db"]),
    ("[Errno 13] Permission denied: \"/Users/Mary Anne/O'Brien Files/x.db\"",
     "[Errno 13] Permission denied: <path>", ["Mary", "Anne", "Brien", "x.db"]),
    ("Uoink's folder 'E:\\x\\Private Folder' can't be read",
     "Uoink's folder <path> can't be read", ["Private", "Folder"]),
    # macOS app, system and volume folders.
    ("/Applications/Uoink.app/Contents/Resources/server.py failed to start",
     "<path> failed to start", ["Applications", "Uoink.app", "server.py"]),
    ("cannot read /Library/Application Support/Uoink/index.db right now",
     "cannot read <path> right now", ["Library", "Application", "Support", "index.db"]),
    ("cannot read /Volumes/My Drive/Uoink/jobs.db, check the disk",
     "cannot read <path>, check the disk", ["Volumes", "My Drive", "jobs.db"]),
    ("cannot read /System/Volumes/Data/Users/mary/x.db.", "cannot read <path>", ["System", "mary", "x.db"]),
    ("see ~/Library/Logs/Uoink/uoink.log for more", "see <path> for more", ["Library", "uoink.log"]),
    ("open file:///Users/mary/notes.html failed", "open <path> failed", ["mary", "notes.html"]),
]


@pytest.mark.parametrize("raw,want,gone", PATH_CASES)
def test_scrub_removes_whole_paths(raw, want, gone):
    text = tools._scrub_error_text(raw)
    assert text == want
    for piece in gone:
        assert piece not in text, piece


def test_scrub_keeps_urls_next_to_spaced_paths():
    text = tools._scrub_error_text(
        "fetch https://example.com/home/My Page failed, cache at /Users/Mary Anne/x.db")
    assert text == "fetch https://example.com/home/My Page failed, cache at <path>"


def test_handler_error_strings_lose_spaced_and_quoted_paths(monkeypatch):
    spec = tools.TOOL_REGISTRY["get_job_status"]
    patched = dataclasses.replace(spec, handler=lambda _a: {
        "ok": False, "error": "failed: 'E:\\Private Folder\\a.db' and \\\\nas\\Team Share\\b.db here"})
    monkeypatch.setitem(tools.TOOL_REGISTRY, "get_job_status", patched)
    result = tools.call_tool("get_job_status", {})
    assert result["error"] == "failed: <path> and <path> here"


def test_scrub_stays_quick_on_a_huge_message():
    import time
    started = time.perf_counter()
    for bad in ("'C:\\ " * 5000, "C:\\" + "word " * 20000, "C:\\a b " * 5000, "'C:\\x" * 5000):
        tools._scrub_error_text(bad)
        tools._redact_paths(bad)
    assert time.perf_counter() - started < 2


def test_missing_input_messages_say_what_to_pass():
    import server
    tools.bind_backend(server)
    assert "words to search for" in tools.call_tool("search_uoinks", {})["error"]
    assert "capture call returned" in tools.call_tool("get_job_status", {"job_id": "zz"})["error"]
    assert "YouTube playlist URL" in tools.call_tool("uoink_playlist", {"url": "x"})["error"]
