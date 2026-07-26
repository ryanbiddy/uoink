"""Settings surfaces must expose only behavior with a live consumer."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP_HTML = (ROOT / "extension" / "setup.html").read_text(encoding="utf-8")
SETUP_JS = (ROOT / "extension" / "setup.js").read_text(encoding="utf-8")
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(
    encoding="utf-8"
)
SERVER = (ROOT / "server.py").read_text(encoding="utf-8")
MCP = (ROOT / "uoink_mcp_tools.py").read_text(encoding="utf-8")
SECURITY = (ROOT / "docs" / "security.md").read_text(encoding="utf-8")


def test_setup_does_not_expose_unconsumed_creator_defaults():
    phantom_ids = (
        'id="ct-workspace-format"',
        'id="ct-target-length"',
        'name="ct-style-source"',
        'id="ct-obsidian-mirror"',
        'id="cv-sources"',
    )
    assert not [field for field in phantom_ids if field in SETUP_HTML]

    phantom_fields = (
        "default_workspace_format",
        "default_target_length",
        "style_anchors_source",
        "mirror_scripts_to_obsidian",
        "default_evidence_sources",
    )
    assert not [field for field in phantom_fields if field in SETUP_JS]
    phantom_identifiers = (
        "ctWorkspaceFormat",
        "ctTargetLength",
        "ctStyleSourceRadios",
        "ctObsidianMirror",
        "cvEnabled",
        "cvSources",
    )
    assert not [name for name in phantom_identifiers if name in SETUP_JS]

    assert "Memory mirror" in SETUP_HTML
    assert "TASTE.md and USER.md" in SETUP_HTML
    assert "obsidian_vault_path:" in SETUP_JS
    assert '"obsidian_vault_path"' in SERVER


def test_claim_settings_describe_explicit_agent_work_not_automatic_scan():
    combined_ui = f"{SETUP_HTML}\n{DASHBOARD}"
    assert 'id="cv-enabled"' not in SETUP_HTML
    assert 'id="claimVerificationToggle"' not in DASHBOARD
    assert "claimVerificationToggle" not in DASHBOARD
    assert "claim_verification_enabled" not in SETUP_JS
    assert "every transcript is scanned" not in combined_ui.lower()
    assert "every uoink's transcript is scanned" not in combined_ui.lower()
    assert "agent-initiated" in SETUP_HTML.lower()
    assert "does not search the web" in combined_ui.lower()
    assert "no current automatic claim scan consumes" in SECURITY.lower()


def test_explicit_evidence_workflow_remains_available():
    # Integration note: this is CX-30's negative control -- it proves that
    # removing the phantom claim-verification *settings* did not remove the
    # real, explicit evidence workflow. It originally witnessed that via the
    # dashboard's "Run claim scan" button (id="runEvidenceClaims") and its
    # POST to /claims/extract. CX-31 (#254) subsequently proved that button
    # was itself a no-op -- it posted an empty claim list and then reported
    # success -- and removed it. The control is therefore re-pointed at the
    # evidence surfaces that are genuinely live after both repairs. Both
    # intents hold: the phantom settings are gone, the no-op action is gone,
    # and the real agent-owned workflow is still reachable.
    assert 'id="reloadEvidence"' in DASHBOARD
    assert "authFetch(`/claims/${encodeURIComponent(videoId)}`)" in DASHBOARD
    assert "data-verify-claim=" in DASHBOARD
    assert "authFetch(`/claims/${encodeURIComponent(claimId)}/verify`" in DASHBOARD
    assert '"extract_claims": ToolSpec(' in MCP
    assert '"verify_claim": ToolSpec(' in MCP
