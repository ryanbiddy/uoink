"""Explicit SDK 1 baseline regeneration, never run automatically by pytest.

Run with the repository on PYTHONPATH and an isolated parent environment:
    python -B tests/update_mcp_wire_goldens.py
Review the fixture diff. Only VERSION and the platform capability notice are
substituted by the tests; schemas and all other text are exact comparisons.
"""
import importlib.metadata
import json
from pathlib import Path
import tempfile

from tests.mcp_wire import ROOT, HttpClient, StdioClient, initialize_request, registry_golden, rpc
from tests.mcp_wire_fixtures import seed_library


def main():
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
