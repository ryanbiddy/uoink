"""G-25 Settings polish contract.

Run: python tests/test_g25_settings_polish.py
"""
from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_dashboard_settings_copy_and_controls() -> None:
    stale = (
        "Download Whisper model now",
        "whisper-timestamped",
        "Local Whisper",
        "Whisper model",
        "sk-ant-...",
        "Credential Manager",
        "Comment Intelligence, Hook Type",
        'data-remove-topic="${index}" aria-label="Remove topic">x</button>',
    )
    for marker in stale:
        require(marker not in DASHBOARD, f"stale Settings marker remains: {marker}")

    expected = (
        'id="pickOutputFolder">Choose folder</button>',
        '<summary>Enter a path manually</summary>',
        'id="outputFolderDisplay"',
        'id="topicUndo"',
        'id="undoTopicRemove">Undo</button>',
        'class="button ghost topic-remove" type="button" data-remove-topic="${index}">Remove</button>',
        "function transcriptModelLabel(model)",
        'JSON.stringify({ model: els.whisperModel.value })',
        'authFetch("/settings/output-folder/pick"',
    )
    for marker in expected:
        require(marker in DASHBOARD, f"missing Settings control: {marker}")
    print("ok  Settings UI hides raw path/model controls and adds undo")


def test_server_folder_picker_and_model_contract() -> None:
    import server

    require(hasattr(server.Handler, "_handle_settings_output_folder_pick"),
            "folder picker handler should be routed through the helper")
    require("output_dir_configured" in server._public_settings({}),
            "public settings should expose the configured output folder")
    require(server._normalize_reliability_model("small") == "small",
            "valid reliability model should be preserved")
    require(server._normalize_reliability_model("bogus") == server.RELIABILITY_MODEL_NAME,
            "invalid reliability model should fall back")

    with TemporaryDirectory() as tmp:
        picked = Path(tmp) / "picked-output"
        with mock.patch.object(server, "_pick_output_folder", return_value=str(picked)):
            settings = {"output_dir": str(Path(tmp) / "current"), "whisper_model": "small"}
            selected = server._pick_output_folder(Path(tmp))
            candidate, error = server._validate_output_dir_value(selected)
            require(error is None and candidate == picked.resolve(),
                    "picked output folder should validate and resolve")
            public = server._public_settings({**settings, "output_dir": str(candidate)})
            require(public["output_dir_configured"] == str(candidate),
                    "public settings should return the selected folder")
    print("ok  server supports picked folders and selected reliability models")


def main() -> int:
    test_dashboard_settings_copy_and_controls()
    test_server_folder_picker_and_model_contract()
    print("\nALL G-25 SETTINGS POLISH TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
