"""CM-12 corpus-intelligence boundary and grounding-equivalence gates."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import corpus_contract  # noqa: E402
import regenerate_migration_step0_fixtures as migration  # noqa: E402


DASHBOARD = (
    ROOT / "assets" / "dashboard" / "index.html"
).read_text(encoding="utf-8")


def test_assemble_is_a_strict_corpus_contract_operation():
    request_type = getattr(corpus_contract, "AssemblyRequest")
    request = request_type.from_body({
        "format": "talking_head",
        "topic": "AI workflows",
        "hook_target": "curiosity_gap",
        "your_channel": "@ryan",
        "n_examples": 12,
    })

    assert "assemble" in corpus_contract.OPERATIONS
    assert request == request_type(
        format="talking_head",
        topic="AI workflows",
        hook_target="curiosity_gap",
        your_channel="@ryan",
        n_examples=12,
    )
    with pytest.raises(corpus_contract.ContractError) as raised:
        request_type.from_body({
            "topic": "AI",
            "workspace_id": "storage must not cross the query contract",
        })
    assert raised.value.code == "invalid_request"
    assert raised.value.message == (
        "unknown assembly fields: workspace_id")


def test_versioned_assemble_matches_legacy_grounding(tmp_path):
    idx = migration.index_mod.Index.open(tmp_path / "index.db")
    try:
        migration._seed_corpus(idx)
        with migration._http_server(idx) as port:
            body = {
                "format": "talking_head",
                "topic": "AI",
                "hook_target": "curiosity_gap",
                "n_examples": 2,
            }
            legacy = migration._call(
                port, "POST", "/workspace/assemble", body)
            versioned = migration._call(
                port, "POST", "/api/corpus/v1/assemble", body)
    finally:
        idx.close()

    assert legacy["status"] == 200
    assert versioned["status"] == 200
    payload = versioned["body"]
    assert payload["contract"] == "uoink.corpus.read"
    assert payload["version"] == 1
    assert payload["operation"] == "assemble"
    assert payload["data"] == {
        key: value
        for key, value in legacy["body"].items()
        if key not in {"ok", "workspace_id"}
    }
    corpus_contract.validate_data("assemble", payload["data"])


def test_cm7_workspace_assembly_characterization_stays_exact():
    expected = json.loads(
        migration.FIXTURES["workspace-assembly"]["path"].read_text(
            encoding="utf-8"))
    assert migration.generate_fixture("workspace-assembly") == expected


def test_assembly_query_has_one_core_owner_and_legacy_wrapper():
    module_path = ROOT / "corpus_intelligence.py"
    assert module_path.exists()
    core = module_path.read_text(encoding="utf-8")
    workspace = (ROOT / "workspaces.py").read_text(encoding="utf-8")

    assert "def assemble(" in core
    assert "FROM yoinks y" in core
    assert "engagement_signal" in core
    assert "read_taste" in core
    assert "corpus_intelligence.assemble" in workspace
    assert "FROM yoinks y" not in workspace
    assert "engagement_signal" not in workspace


def test_generate_dogfoods_writer_facing_assembly_path():
    generate = DASHBOARD.split(
        "async function generateAssemblyBody()", 1)[1].split(
        "async function generateScriptInWriting()", 1)[0]
    build = DASHBOARD.split(
        "async function assembleCurrentWorkspace()", 1)[1].split(
        "async function runWorkspaceCritique()", 1)[0]

    assert "/api/corpus/v1/assemble" in generate
    assert "/workspace/assemble" not in generate
    assert "/workspace/assemble" in build


def test_corpus_intelligence_ships_with_the_helper():
    build = (ROOT / "build.ps1").read_text(encoding="utf-8")
    installer = (
        ROOT / "installer" / "uoink.iss"
    ).read_text(encoding="utf-8")

    assert "'corpus_intelligence.py'" in build
    assert (
        "Copy-Item (Join-Path $RepoRoot 'corpus_intelligence.py')"
        in build
    )
    assert "corpus_intelligence.py page_extractor.py" in build
    assert 'Source: "staging\\corpus_intelligence.py"' in installer
