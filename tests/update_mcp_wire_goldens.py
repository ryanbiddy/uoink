"""Explicit wire baseline regeneration, never run automatically by pytest.

Run with the repository on PYTHONPATH and an isolated parent environment:
    python -B tests/update_mcp_wire_goldens.py
The full baseline still requires SDK 1.28.1. On SDK 2, search-only refresh is:
    python -B tests/update_mcp_wire_goldens.py --search-only
This uses the real stdio server with a disposable seeded library. It updates
only the four search tools' schemas/descriptions and the embedded search data
in prompt/success. Protocol envelopes and every other baseline entry are kept.
The modern fixture contains requests only and shares these expected results.
For documentation changes on either supported SDK, use:
    python -B tests/update_mcp_wire_goldens.py --metadata-only
This refreshes all tool metadata after rejecting any input contract or inventory
change and synchronizes the bundle's tool descriptions. All non-tool protocol
fixtures remain unchanged. See docs/GLAMA-BUILD.md.
Review the fixture diff. Only VERSION and the platform capability notice are
substituted by the tests; schemas and all other text are exact comparisons.
"""
import argparse
import copy
import importlib.metadata
import json
from pathlib import Path
import tempfile

from uoink_mcp_tools import without_descriptions

from tests.mcp_wire import ROOT, HttpClient, StdioClient, initialize_request, registry_golden, rpc
from tests.mcp_wire_fixtures import seed_library


SEARCH_TOOLS = {"search_uoinks", "search_clips", "search_library", "find_mentions"}


def refresh_metadata(golden, tools):
    """Refresh documentation only; reject any input-contract or inventory drift."""
    updated = copy.deepcopy(golden)
    assert [t["name"] for t in tools] == [t["name"] for t in golden["tools"]]
    for old, live in zip(golden["tools"], tools):
        assert without_descriptions(old["inputSchema"]) == without_descriptions(live["inputSchema"]), old["name"]
        allowed = {"description", "title", "annotations", "inputSchema", "outputSchema"}
        assert {k: v for k, v in old.items() if k not in allowed} == {
            k: v for k, v in live.items() if k not in allowed}, old["name"]
    updated["tools"] = copy.deepcopy(tools)
    return updated


def update_metadata_only():
    target = Path(__file__).parent / "fixtures/mcp_wire/sdk1.json"
    golden = json.loads(target.read_text(encoding="utf-8"))
    scratch = ROOT / "_scratch/tdqs-wire"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as directory:
        with StdioClient.launch(directory) as client:
            client.initialize()
            tools = client.request(2, "tools/list")["result"]["tools"]
            assert tools == registry_golden(), "Wire registry differs from product schemas"
            client.save(scratch / "metadata-generation-stdio.jsonl")
    updated = refresh_metadata(golden, tools)
    manifest_path = ROOT / ".mcpb/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [t["name"] for t in manifest["tools"]] == [t["name"] for t in tools]
    for bundled, live in zip(manifest["tools"], tools):
        bundled["description"] = live["description"]
    target.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Metadata-only refresh: {len(tools)} tools; input contracts and other wire fixtures unchanged")


def refresh_search(golden, tools, prompt, success):
    """Return a narrow update; refuse changes outside search-owned fields."""
    updated = copy.deepcopy(golden)
    assert [t["name"] for t in tools] == [t["name"] for t in golden["tools"]]
    for old, live, target in zip(golden["tools"], tools, updated["tools"]):
        if old["name"] in SEARCH_TOOLS:
            for field in ("inputSchema", "description"):
                if target[field] != live[field]:
                    target[field] = live[field]
        assert target == live, f"Non-search tool change: {old['name']}"

    # Only the second prompt message's search data may change. Keep the
    # instructions, wrapper, contract versions, topic and message envelope exact.
    old_text = golden["prompt"]["messages"][1]["content"]["text"]
    new_text = prompt["messages"][1]["content"]["text"]
    opening = "<untrusted_uoink_library_context>\n"
    closing = "\n</untrusted_uoink_library_context>"
    old_prefix, old_body = old_text.split(opening)
    new_prefix, new_body = new_text.split(opening)
    old_body, old_suffix = old_body.split(closing)
    new_body, new_suffix = new_body.split(closing)
    assert (old_prefix, old_suffix) == (new_prefix, new_suffix)
    old_data, new_data = json.loads(old_body), json.loads(new_body)
    for field in ("hits", "hit_count", "next_step", "note", "omitted", "dropped_for_budget"):
        old_data.pop(field, None)
        new_data.pop(field, None)
    assert old_data == new_data, "Non-search prompt data changed"
    updated["prompt"]["messages"][1]["content"]["text"] = new_text
    assert updated["prompt"] == prompt, "Prompt envelope or instructions changed"

    old_data = json.loads(golden["success"]["content"][0]["text"])
    new_text = success["content"][0]["text"]
    new_data = json.loads(new_text)
    for field in ("results", "search_mode", "requested_mode", "fallback_reason"):
        old_data.pop(field, None)
        new_data.pop(field, None)
    assert old_data == new_data, "Non-search tool result data changed"
    updated["success"]["content"][0]["text"] = new_text
    assert updated["success"] == success, "Tool result envelope changed"
    return updated


def update_search_only():
    target = Path(__file__).parent / "fixtures/mcp_wire/sdk1.json"
    golden = json.loads(target.read_text(encoding="utf-8"))
    scratch = ROOT / "_scratch/sdk2/m2"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as directory:
        seed_library(directory)
        with StdioClient.launch(directory) as client:
            client.initialize()
            tools = client.request(2, "tools/list")["result"]["tools"]
            assert tools == registry_golden(), "Wire registry differs from product schemas"
            prompt = client.request(3, "prompts/get", {
                "name": "consult-library", "arguments": {"topic": "absent-m2-topic"}})["result"]
            success = client.request(4, "tools/call", {
                "name": "search_clips", "arguments": {"query": "absent-m2-topic"}})["result"]
            client.save(scratch / "search-golden-generation-stdio.jsonl")
    updated = refresh_search(golden, tools, prompt, success)
    target.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    changed = [key for key in golden if updated[key] != golden[key]]
    print(f"Search-only refresh: {', '.join(changed) or 'no changes'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-only", action="store_true",
                        help="Refresh only search data, allowed on SDK 2")
    parser.add_argument("--metadata-only", action="store_true",
                        help="Refresh tool documentation with structural input-contract checks")
    args = parser.parse_args()
    if args.metadata_only:
        assert not args.search_only, "Choose only one refresh mode"
        update_metadata_only()
        return
    if args.search_only:
        update_search_only()
        return
    assert importlib.metadata.version("mcp") == "1.28.1", "Regenerate the baseline on pinned SDK 1"
    import _platform
    from library_resources import TEMPLATES
    from library_prompts import PROMPTS
    from research_playbooks import PLAYBOOKS

    scratch = ROOT / "_scratch/sdk2/m2"
    scratch.mkdir(parents=True, exist_ok=True)
    golden = {"tools": registry_golden()}
    with tempfile.TemporaryDirectory(dir=scratch) as directory:
        uri = seed_library(directory)
        with StdioClient.launch(directory) as client:
            golden["stdio_initialize"] = client.initialize()["result"]
            assert client.request(2, "tools/list")["result"]["tools"] == golden["tools"]
            cases = [
                ("templates", "resources/templates/list", None),
                ("prompts", "prompts/list", None),
                ("resource", "resources/read", {"uri": uri}),
                ("prompt", "prompts/get", {"name": "consult-library", "arguments": {"topic": "absent-m2-topic"}}),
                ("success", "tools/call", {"name": "search_clips", "arguments": {"query": "absent-m2-topic"}}),
                ("invalid", "tools/call", {"name": "get_playbook_input", "arguments": {}}),
            ]
            for n, (label, method, params) in enumerate(cases, 3):
                golden[label] = client.request(n, method, params)["result"]
            assert golden["templates"]["resourceTemplates"] == list(TEMPLATES)
            assert golden["prompts"]["prompts"] == list((*PROMPTS, *PLAYBOOKS))
            golden["unknown_stdio"] = client.request(9, "m2/unknown")["error"]
            client.send_raw("{")
            golden["parser_notification"] = client.receive()
            client.send_raw(" " * 65537)
            golden["oversized"] = client.receive()
            client.save(scratch / "golden-generation-stdio.jsonl")
        with HttpClient(directory) as client:
            golden["http_initialize"] = client.post(initialize_request("2025-11-25"))[1]["result"]
            golden["http_token_refusal"] = client.post(rpc(2, "tools/list"), token=None)[1]
            golden["http_host_refusal"] = client.post(rpc(3, "tools/list"), host="attacker.invalid")[1]
            golden["unknown_http"] = client.post(rpc(4, "m2/unknown"))[1]["error"]
        for transport in ("stdio", "http"):
            init = golden[transport + "_initialize"]
            init["serverInfo"]["version"] = "${VERSION}"
            init["protocolVersion"] = "${LEGACY_VERSION}"
            notice = _platform.capability_notice()
            if notice:
                assert init["instructions"].endswith(notice)
                init["instructions"] = init["instructions"][:-len(notice)]
    target = Path(__file__).parent / "fixtures/mcp_wire/sdk1.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(golden, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {target}: 91 tools, 5 templates, 9 prompts, stdio and HTTP baseline")


if __name__ == "__main__":
    main()
