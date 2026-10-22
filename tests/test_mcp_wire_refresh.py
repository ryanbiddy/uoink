"""Search refresh must not bless unrelated registry or protocol changes."""
import copy
import json
from pathlib import Path

import pytest

from tests.update_mcp_wire_goldens import refresh_search


@pytest.mark.parametrize("change", ["other_tool", "annotations", "prompt_instructions",
                                    "prompt_contract", "structured_content", "is_error"])
def test_search_refresh_refuses_non_search_changes(change):
    golden = json.loads((Path(__file__).parent / "fixtures/mcp_wire/sdk1.json").read_text(encoding="utf-8"))
    live = copy.deepcopy(golden)
    if change == "other_tool":
        live["tools"][0]["description"] = "changed"
    elif change == "annotations":
        next(t for t in live["tools"] if t["name"] == "search_clips")["annotations"]["readOnlyHint"] = False
    elif change == "prompt_instructions":
        live["prompt"]["messages"][0]["content"]["text"] = "changed"
    elif change == "prompt_contract":
        content = live["prompt"]["messages"][1]["content"]
        content["text"] = content["text"].replace("phase4-v1-2026-09-08", "changed")
    elif change == "structured_content":
        live["success"]["structuredContent"] = {"ok": True}
    else:
        live["success"]["isError"] = True
    original = copy.deepcopy(golden)
    with pytest.raises(AssertionError):
        refresh_search(golden, live["tools"], live["prompt"], live["success"])
    assert golden == original
