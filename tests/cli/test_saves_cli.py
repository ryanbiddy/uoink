"""Offline saves CLI mapping and human output."""
from pathlib import Path

import pytest

import uoink_cli as cli


def test_import_file_maps_to_existing_tool(tmp_path):
    path = tmp_path / "saves.csv"
    ns = cli.parser().parse_args(["import", str(path), "--source", "watch_later", "--limit", "7", "--offset", "50", "--preview"])
    name, args = cli.friendly_call(ns, None)
    assert name == "import_list"
    assert args == {"file": str(path.resolve()), "source": "watch_later", "limit": 7, "offset": 50, "preview_only": True}
    _, args = cli.friendly_call(cli.parser().parse_args(["import", "saves.txt"]), None)
    assert Path(args["file"]).is_absolute() and "source" not in args


@pytest.mark.parametrize("flags", [["--limit", "0"], ["--limit", "51"], ["--offset", "-1"]])
def test_import_rejects_invalid_paging(flags):
    with pytest.raises(cli.UsageError):
        cli.friendly_call(cli.parser().parse_args(["import", "saves.csv", *flags]), None)


def test_staged_token_next_batch_mapping_and_printing():
    token = "uoink-saves:0123456789abcdef"
    name, args = cli.friendly_call(cli.parser().parse_args(["import-list", token, "--offset", "50"]), None)
    assert name == "import_list" and args["url"] == token and args["offset"] == 50
    rendered = cli.human({"ok": True, "source": {"label": "Reddit saved", "title": "Reddit saved", "url": token},
                          "found": 50, "next_offset": 50, "message": "Found 50 posts."})
    assert token in rendered and "--offset 50" in rendered and "uoink import-list" in rendered
