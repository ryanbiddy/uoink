"""Documentation must preserve accepted inputs and describe actual result shapes."""
import copy
import json
from pathlib import Path

import jsonschema
import pytest

import uoink_mcp_tools as tools
from tests.update_mcp_wire_goldens import refresh_metadata


def test_client_metadata_preserves_every_input_contract():
    original = copy.deepcopy(tools.list_tools())
    assert set(tools.DESCRIPTIONS) == set(tools.TOOL_REGISTRY)
    for name, spec in tools.TOOL_REGISTRY.items():
        plain = tools.client_input_schema(spec.input_schema)
        documented = tools.client_input_schema(spec.input_schema, name)
        assert tools.without_descriptions(documented) == tools.without_descriptions(plain), name
        assert all(p.get("description") for p in documented.get("properties", {}).values()), name
        assert "\u2014" not in spec.description, name
        jsonschema.Draft202012Validator.check_schema(documented)
    assert tools.list_tools() == original


@pytest.mark.parametrize("change", ["required", "type", "enum", "minimum", "name", "count"])
def test_metadata_refresh_refuses_contract_changes(change):
    baseline = json.loads((Path(__file__).parent / "fixtures/mcp_wire/sdk1.json").read_text(encoding="utf-8"))
    live = copy.deepcopy(baseline["tools"])
    if change == "name":
        live[0]["name"] = "renamed"
    elif change == "count":
        live.pop()
    elif change == "required":
        live[0]["inputSchema"]["required"] = []
    else:
        live[0]["inputSchema"]["properties"]["url"][change] = {
            "type": "integer", "enum": ["restricted"], "minimum": 2}[change]
    with pytest.raises(AssertionError):
        refresh_metadata(baseline, live)


def test_metadata_refresh_preserves_protocol_fixtures():
    baseline = json.loads((Path(__file__).parent / "fixtures/mcp_wire/sdk1.json").read_text(encoding="utf-8"))
    live = copy.deepcopy(baseline["tools"])
    live[0]["description"] = "Changed documentation."
    live[0]["inputSchema"]["properties"]["url"]["description"] = "Updated URL guidance."
    result = refresh_metadata(baseline, live)
    assert result["tools"] == live
    assert {k: v for k, v in result.items() if k != "tools"} == {
        k: v for k, v in baseline.items() if k != "tools"}


def test_output_schemas_accept_existing_failure_envelopes():
    for name, schema in tools.OUTPUT_SCHEMAS.items():
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate({"ok": False, "error": "not found"})
        validator.validate({"ok": False, "error": {"code": "invalid_request", "message": "bad input"}})
        with pytest.raises(jsonschema.ValidationError):
            validator.validate({"ok": True})


def test_metadata_comparison_keeps_description_named_fields_and_literal_constraints():
    schema = {"type": "object", "description": "Schema prose", "properties": {
        "description": {"type": "string", "description": "Parameter prose"},
        "record": {"const": {"description": "Required literal value"}}}}
    expected = {"type": "object", "properties": {
        "description": {"type": "string"},
        "record": {"const": {"description": "Required literal value"}}}}
    assert tools.without_descriptions(schema) == expected
    assert tools.without_descriptions(schema) != tools.without_descriptions({
        **schema, "properties": {"record": schema["properties"]["record"]}})
