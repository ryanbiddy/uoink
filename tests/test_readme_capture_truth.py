"""Keep the README's clipboard claim aligned with asynchronous enrichment."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_readme_distinguishes_initial_clipboard_from_saved_comments() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "comments — copied to your clipboard" not in readme
    assert "comments, metadata → Markdown corpus lands on your clipboard" not in readme
    assert "they are not part of the initial clipboard copy" in readme
    assert "top comments in the background and updates the saved corpus" in readme


def test_runtime_still_builds_clipboard_payload_before_comments_worker() -> None:
    server = (ROOT / "server.py").read_text(encoding="utf-8")
    extension = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")

    paste_built = server.index("paste_md = _generate_paste_corpus(output_folder)")
    comments_started = server.index(
        "_start_comments_thread(url, output_folder, yoink_path, metadata, entries)"
    )

    assert paste_built < comments_started
    assert "data.corpus_md_paste || data.yoink_md" in extension
