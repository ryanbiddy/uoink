# Review the Desktop isolation incident, without launching anything

Ryan requested native GUI checks and Gemini security review through Control Room.
Read E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/NATIVE-CLIENT-ISOLATION-INCIDENT-2026-09-12.md
first, then write docs/library/NATIVE-CLIENT-ISOLATION-WORKER-2026-09-12.md early.
This is a bounded documentary security review of an integrator mistake.

Inspect only repository scripts/install_receipt/p4_common.py and p4_session.py,
the integrator's _scratch/native_gui07_driver.py, and the statically extracted
shipped source at _scratch/desktop-startup12-static/.vite/build/index.pre.js,
all under the checkout above. You may read its snippets.json and bindings.json.
Do not read any ordinary profile/configuration/authentication store or additional
receipt logs. No applications, model processes, installs, UI or network requests.

Determine whether the packaged startup can discard CLAUDE_USER_DATA_DIR before
its setter, whether the guard installed into one Python interpreter can contain
an unrelated configured connector, and whether Job Object cleanup establishes
absence of earlier effects. Distinguish confirmed source/log facts supplied in
the incident from speculation. Identify a supported safe next environment for
Desktop GUI acceptance without disabling or bypassing packaged security checks.
No attempt to forge developer authorization, modify third-party app code, copy
credentials, mutate global profile settings or invoke ordinary MCP servers.

Review the proposed correction: package-08 exposes only the isolated Uoink
dashboard; Desktop GUI credit stays absent until a separately verified account/
VM or supported isolation method is available. Keep the verified CLI exchanges
separate and do not conclude the live index was or was not accessed from silence.
Name any further concrete gap in that correction. No product/test/fixture edits,
no commits/pushes/subagents. Never open/stat/hash the live index, contact 5179,
use paid APIs or set ANTHROPIC_API_KEY. Apply remains false.

No executable suite is named because this is source-only analysis; retain exact
file hashes and small relevant excerpts, and do not claim an unexecuted test.
Astra verifies and integrates the report while preserving the incident record.
