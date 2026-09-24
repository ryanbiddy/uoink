# Phase 4 installed provenance probe repair

The actual package-05 Setup and reinstall succeeded. Its installed C22 scenarios
have 11 passes and zero failures, with three manual placeholders retained. The
first installed P4 prepare stage exits one before fixture creation: the provenance
probe cannot import uoink_mcp, server, index, library_cards, library_work or
library_prompts. The complete package-file comparison passes all 32,054 files.

The embedded Python ._pth deliberately omits the script directory. Normal server
and MCP entry points explicitly prepend their own installed directory. The P4
probe instead executes a temporary script containing bare imports and assumes
the interpreter supplies that path. Source-runtime tests used an ordinary Python
environment and did not expose this assumption.

Repair only the probe bootstrap and its command arguments in p4_common.py. Pass
the already validated absolute installed app directory as an explicit argument.
Prepend that directory before importing the exact original modules. Record the
resulting sys.path and module paths as before. Keep automatic parent/child guards,
checkout/user-site rejection, original installed MCP command, fixture behavior,
assertions and all package-binding comparisons unchanged. No _pth modification
or source-path exemption is allowed for this P4 repair.

Add independent regressions that execute the probe under isolated no-site Python
with a temporary app and fake modules. Prove the pre-repair code fails that
embedded-style condition and the repaired probe imports only the bound app.
Reject a missing/relative bootstrap path and preserve checkout rejection.

Astra uses a fresh detached worktree. Verify the new regression and all five
test_install_receipt_p4_* suites, export a raw git diff, apply it three-way in the
checkout, repeat those suites, and commit. Then repeat the complete accounted
tree on the new committed source. This changes the receipt kit, not a compiler
input, so no installer rebuild is owed unless separate packaged source changes.

After integration, use a fresh P4 receipt/profile directory. Retain the original
p4/profile operator receipt, stderr, guard canary, owned cleanup and guard restore.
The first failure remains failed. No live helper/index, new source, paid client,
speaker processing or ordinary credential access is authorized.
