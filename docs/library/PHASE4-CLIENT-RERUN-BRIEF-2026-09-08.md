# Phase 4 client rerun after AW-4

Run only after AV-5m4a/4b and any further AW-4 repairs are integrated and the candidate SHA
is frozen. The earlier [AW receipt](PHASE4-AW-RECEIPT-2026-09-08.md) is partial
and belongs to `d4d99bb`; preserve it. The repaired observation must satisfy
all five requirements in [AW-3](PHASE4-ACCEPTANCE-3-2026-09-08.md), including
actual actions and complete returned evidence. Do not reuse its numerical or
client verdict as a result for the later candidate.

The preparation and observation changes are:

1. Stage the frozen source through the existing source-only build path. Use a
   disposable profile, stdio child and separate output directory. Duplicate the
   authorized upgraded index copy read-only into the fixture; rebind all used
   corpus/sidecar paths to disposable copies and verify those paths before any
   request. Never open the live index or contact port 5179. Freeze and hash the
   candidate, launch files, client version/mode, interpreter, SDK, allowlist,
   source-copy manifest and full expected packet before starting the client.
   Derive expected IDs, complete quotes, timing and source/card/excerpt hashes
   from stored evidence and canonical card construction, independently of the
   reader response. Include the retained timed and text-only items.
2. Record the complete client event stream and stdio requests/results, with
   timestamps and child identities. Observe discovery, bounded search, item,
   full card and excerpt retrieval; compare complete contents and hashes, not
   prefixes. Compare tool fallback with the same resource response. Record
   all five templates, four prompts and the candidate's actual tool inventory;
   explain authorized inventory changes rather than assuming the old count.
3. Invoke consult-library and reshelve-review through a supported native Claude
   Code prompt route and retain the returned messages and actual prompts/get
   traffic. Model text saying a prompt was invoked is not proof. Record any
   missing client route as a failure; do not substitute a synthetic protocol
   client. Compare queue, projection and settings before/after. Observe the
   actual returned public link in an isolated browser, including the requested
   seek and the text-only item's absence of invented timing. Any brief workflow
   must retain its prepared packet, restart, publication, citations, receipt,
   identical retry and stale refusal.
4. Separate explicit reconnect from fixture-storage failure and broken-child
   transport failure. Keep old/new child PIDs and full unchanged-item responses.
   Measure each live-child storage refusal from its request, within 2 seconds,
   and prove no replacement empty index was created. Measure client transport
   failure from the request/connection attempt, within 15 seconds and at most
   one explicit reconnect. Session duration alone is insufficient.
5. Use hostile titles, source text, fences, labels and brief content with only
   declared fixture reads and inert action sentinels available. Retain full
   tool inputs/results, attempted and executed actions, permission decisions
   and sentinel before/after hashes. The final model summary and an empty
   denial list are insufficient. Separately exercise only the isolated Recall
   fixture and retain its bounded silent-failure behavior and client actions.
   Complete vault disconnection, user-edit and deletion cases with owned files,
   temporary files, cleanup queues and conflicts accounted for after repair.

Claude Code 2.1.261 was available at preparation and reported claude.ai Max
subscription authentication. Recheck the actual mode at execution, with
ANTHROPIC_API_KEY absent; never use bare/API-key mode, paid API or an upgrade.
A quota refusal is a retained failed/partial observation and cannot be called
a passing client receipt. No model execution occurred during this preparation.

Record Claude Desktop separately if an isolated desktop session is available.
The browser connector initially exposed only the in-app browser. The separate
Windows computer-use runtime later found normal Comet and Claude Desktop.
That inventory does not establish an isolated desktop client configuration.
Any missing desktop observation must be stated with exact remaining actions;
it cannot waive the required Claude Code/stdio workflow.

Keep raw private evidence internal, seal every retained artifact with SHA-256,
and distinguish any redacted copy by its own hash. No live labels, settings,
client configuration, helper, install or release changes. No push. Installed
Inno receipts remain Ryan's separate P4-13/C22 gate.

## Recorder preparation, 2026-09-08

`proof/aw-rerun-2026-09-08/stdio_tap.py` records complete byte frames in both
directions, separate stderr, child identities, per-request timing and unanswered
requests at child exit. Configure it as the real client's MCP command, wrapping
the exact staged child. It never issues its own MCP request. Each launch creates
a fresh private recording directory; unsafe profile roots refuse before launch.
Timing includes recorder overhead and is not pure server CPU time.

The stdlib-only `verify_stdio_tap.py` check passed on 2026-09-08: three lossless
requests (85,275 input / 85,221 output bytes), diagnostics, request correlation,
child exit, unanswered request on exit 7, and unsafe-profile refusal. Receipt
and transcripts are retained locally in `_scratch/aw-tap-verify-01`. This ran
neither uoink nor a model and credits no real-client or phase gate.

Anthropic's [MCP documentation](https://code.claude.com/docs/en/mcp#use-mcp-prompts-as-commands)
documents native `/mcp__servername__promptname` commands with positional
arguments. Its [programmatic guide](https://code.claude.com/docs/en/headless)
describes print mode but does not by itself prove this installed client's prompt
route. Observe the actual `prompts/get` exchange for both required prompts; a
documentation lookup, slash-command-looking model text or fixture probe is not
an invocation receipt. Keep bare/API-key mode disabled and stop on a quota
refusal; no upgrade or additional paid usage is authorized.

`proof/aw-rerun-2026-09-08/prepare_fixture.py` prepares a fresh fixture only
after the prerequisites above. It requires the exact clean committed SHA,
checks the archived source bytes/hash, rebinds SQL/embedded JSON and copied
sidecar paths, stages source, and freezes complete expected cards/excerpts
from stored rows plus canonical pure construction. It never starts a client
or model. Run it with --repo, a fresh --fixture-root under checkout scratch,
and --candidate. Freeze its resulting preparation/expected/config files and
the actual client version/mode/allowlist before any client observation.

During authoring only syntax, guard syntax and synthetic rebinding are checked.
No current candidate or measured-copy receipt is credited until this script
actually runs after AW-4 closes its implementation findings.

## Valid-preview application fixture

The default stdio entry does not attach a Phase 2 work service. Preserve its
`feature_unavailable` behavior and original `mcp.json` configuration. To
observe a valid native `reshelve-review`, run
`proof/aw-rerun-2026-09-08/prepare_prompt_session.py` once on the prepared
fixture immediately before the client observation. It creates a separate
`mcp-attached.json` and application fixture launcher using the real service
and shipped stdio entry. Record this launch distinction explicitly.

Preconditioning approves a synthetic, inactive taxonomy, makes a run whose
two held items are explicitly excluded from classification, and creates an
unapproved report-only preview. Apply stays false; no assignment is created.
All setup calls/results, the original and post-setup semantic state, preview
expiry, and launch/config hashes are retained. Compare client actions against
that post-setup state. Do not treat synthetic exclusions as a classifier result.
The preview expires after 15 minutes; a missed window is a retained failed
observation and requires a documented fresh-fixture repair before retry.

Authoring verification used two synthetic items, source staging and the real
service recheck: **one passed**, 0.85 seconds (checkout scratch
`aw-prompt-prep-synthetic`). Apply remained false, assignments unchanged, and
service reattachment preserved the semantic state. No archived copy, actual
client/model, native prompt request or phase acceptance is credited by that test.

## Client timeout preparation

Set `MCP_TIMEOUT=10000` and the explicit fixture server's `timeout` to 10000
milliseconds in the separately frozen client launch. The installed 2.1.261
client's help supports restricted mode, strict MCP configuration and explicit
settings. [Anthropic's MCP documentation](https://code.claude.com/docs/en/mcp)
documents both timeout controls and identifies the per-server tool timeout
as a wall-clock limit. This is a planned configuration, not a measured bound.
Retain actual request/connection timestamps, failure and any explicit reconnect;
the 15-second acceptance gate still requires an observation. Recheck subscription
authentication immediately before launch, with API-key and bare modes absent.

## Complete-packet inspection

`proof/aw-rerun-2026-09-08/inspect_client_evidence.py` reads the recorder's
complete frames, validates their lengths and hashes, correlates requests
within each connection and compares every character of the frozen card and
excerpt text on both native-resource and fallback-tool routes. It retains
discovery inventories, full native prompt messages, tool actions, unmatched
responses and unanswered requests. Missing evidence and changed tails fail
its packet/prompt subset; that subset never establishes phase acceptance.

Authoring verification: four synthetic checks passed in 1.70 seconds
(checkout scratch `aw-evidence-inspector-01`). They cover exact equality,
changed tails with identical prefixes, missing native prompt exchanges and
a corrupted frame hash. No client/model or archived copy was used.

The fixture client's built-in tool list must retain `ListMcpResourcesTool`
and `ReadMcpResourceTool`, the names in Anthropic's
[tools reference](https://code.claude.com/docs/en/tools-reference). An empty
built-in tool list would remove these native resource routes. Restrict other
capabilities explicitly and retain the observed session inventory; the
[MCP documentation](https://code.claude.com/docs/en/mcp) describes native
resource mentions and prompt commands, but the receipt requires actual traffic.

## Action and Recall observation

`proof/aw-rerun-2026-09-08/observe_client_actions.py` supplies three fixture
modes. `hook` retains full client hook inputs and decisions; PreToolUse permits
only the three bounded library reads, two native resource tools and the inert
sentinel. `sentinel` advertises one action recorder that refuses every effect;
an invocation is an attempted action even though protected bytes are unchanged.
`recall` wraps the staged Recall hook against only fixture/recall/index.db,
retaining its complete input/output, exit and wall time. It never uses the
normal default index. Freeze the explicit fixture settings and launch first.

Attach the observer to PreToolUse, PostToolUse, PostToolUseFailure and
PermissionDenied, and retain the complete client stream as well. Anthropic's
[hook reference](https://code.claude.com/docs/en/hooks) states that validation
rejections can occur before tool hooks; hook logs alone cannot prove that no
other action was attempted. Keep Recall's UserPromptSubmit hook separate so
its injected context and subsequent client actions can be identified.

Four synthetic observer checks passed in 3.20 seconds: full read approval,
non-read denial, an inert sentinel invocation with unchanged protected bytes,
and silent missing-index Recall with no replacement database. The URI guard's
initial failure and repair, packet-inspector checks, and observer checks are
retained under the adjacent preparation-checks archive. These are authoring
results, not a client or phase acceptance receipt.
