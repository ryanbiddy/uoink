"""Dashboard registry tools: errors are readable and never double-send (D2).

Before the fix, callRegistryTool() in assets/dashboard/index.html re-sent every
failure from /mcp/v1/tools/call to /tools/<name>, so a register_source or
set_source_consent the tool had already refused went out a second time with the
same arguments and user_intent_token. authFetch() built Error(data.error) from
the {code, message} contract envelope, so users read "[object Object]", and the
callers' ok:false branches (the activity stale_report recovery among them) were
dead because every refusal arrived as a throw.

Runs tests/js/dash_registry_errors_test.mjs, which loads the REAL dashboard
script (everything before init()) into a node:vm context over a fake page
holding every id the markup declares. A fake helper answers both transports
from one tool function the way server.py does, and every request is logged:

  refusal    -- a tool refusal is returned, shown in words and sent once:
                register_source, set_source_consent (with its minted
                user_intent_token), Retry poll, captured items. The plain
                error string uoink_mcp_tools._err returns reads as well as
                the {code, message} envelope.
  auth_fetch -- authFetch errors read error.message from a contract envelope,
                keep a plain error string, and fall back to the HTTP status.
  transport  -- only a request that got no response, or a helper without the
                MCP route (404), is retried on /tools/, once, and the /tools/
                reply is unwrapped to the MCP shape; a 403/429/500 from the MCP
                route is reported in words and not re-sent.
  activity   -- a refused summary, summary reload or evidence page shows its
                reason, envelope or plain string; a stale evidence
                or collection page reloads the summary over MCP, and a reload
                that lands after a newer refresh leaves that refresh's evidence
                pagers enabled; a refused collection page disables its pager; a
                summary reload that gets no response is reported instead of
                hanging on "Stale".

No network: fetch is a stub inside the harness.
"""
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "tests" / "js" / "dash_registry_errors_test.mjs"

GROUPS = [
    "refusal",
    "auth_fetch",
    "transport",
    "activity",
]


@pytest.mark.parametrize("group", GROUPS)
def test_dash_registry_errors(group):
    assert HARNESS.exists(), f"missing harness: {HARNESS}"
    proc = subprocess.run(
        ["node", str(HARNESS), group],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    output = f"{proc.stdout}\n{proc.stderr}"
    assert proc.returncode == 0, f"{group} harness failed:\n{output}"
    assert "FAIL" not in output, output
    # Guard against a group that silently ran nothing.
    marker = f"group {group}: "
    assert marker in proc.stdout, output
    count = int(proc.stdout.split(marker, 1)[1].split(" ", 1)[0])
    assert count >= 5, output
