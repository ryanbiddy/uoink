"""First-run copy says what Uoink does today.

The in-page button is labelled "Uoink" (extension/content.js), and the
install finish page is the last thing a new user reads before the first
save. Neither may promise the old "rust U" or a dashboard that never opens.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD_NAMES = ("rust U", "rust-U", "magnet-U")


def user_strings(path: Path) -> list[str]:
    """Every string literal in a module except docstrings."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    docstrings = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str)):
            docstrings.add(id(body[0].value))
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings]


def test_no_user_string_names_the_old_rust_u():
    found = [f"{name}: {text[:70]!r}"
             for name in ("server.py", "source_manifest.py", "uoink_tray.py", "uoink_splash.py")
             for text in user_strings(ROOT / name)
             if any(old in text for old in OLD_NAMES)]
    assert not found, "\n".join(found)


def test_capture_hints_name_the_button_people_see():
    import source_manifest
    hints = {row["slug"]: row["capture"] for row in source_manifest.build_sources()["sources"]}
    assert "Uoink button" in hints["youtube"]
    assert "Uoink button" in hints["youtube-shorts"]
    # No in-page button runs on tiktok.com, so the hint points at the toolbar.
    assert "browser toolbar" in hints["tiktok"]
    content_js = (ROOT / "extension" / "content.js").read_text(encoding="utf-8")
    assert '"Uoink"' in content_js


def test_ready_toast_and_empty_library_name_the_uoink_button():
    server = (ROOT / "server.py").read_text(encoding="utf-8")
    assert "Click the Uoink button under any YouTube video to save it. " in server
    assert "Open the dashboard anytime from the Uoink icon in your system tray." in server
    assert "_No uoinks yet. Click the Uoink button under any YouTube video to start._" in server


def test_installer_finish_page_matches_what_a_first_save_does():
    iss = (ROOT / "installer" / "uoink.iss").read_text(encoding="utf-8")
    labels = dict(re.findall(r"(?m)^(FinishedLabel(?:NoIcons)?)=(.*)$", iss))
    assert set(labels) == {"FinishedLabel", "FinishedLabelNoIcons"}
    assert labels["FinishedLabel"] == labels["FinishedLabelNoIcons"]
    extract_js = (ROOT / "extension" / "lib" / "extract.js").read_text(encoding="utf-8")
    after_save = re.search(r'const AFTER_SAVE_DEFAULT = "(\w+)";', extract_js).group(1)
    if after_save == "stay":
        # A first save keeps you on the page and shows a notice. It does not
        # open the dashboard, so the last install screen must not promise it.
        assert "opens the dashboard" not in labels["FinishedLabel"]
    assert "walks you through adding the browser button" in labels["FinishedLabel"]
    assert labels["FinishedLabel"].isascii()
