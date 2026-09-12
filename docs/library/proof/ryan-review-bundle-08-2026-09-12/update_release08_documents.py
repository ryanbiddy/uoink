"""Update human-facing notes from completed package-08 observations only."""
from pathlib import Path
import json
r=Path(__file__).resolve().parents[1];d=r/'docs/library';s=r/'_scratch'
read=lambda q:json.loads(q.read_text(encoding='utf-8-sig'))
p=read(d/'proof/candidate-package-08-2026-09-12/package-manifest.json')
b=read(d/'proof/candidate-package-08-2026-09-12/build-receipt.json')
t=read(d/'proof/ryan-final-partitioned-06-2026-09-12/summary.json')
i=read(s/'installed08-reviewed-summary.json');g=read(s/'native08-observed-summary.json')
assert i['package_sha256']==g['package_sha256']==p['package_sha256']
assert i['setup_observed'] and g['actual_gui_observation'] and g['owned_cleanup_affirmed']
assert t['counts']=={'passed':2579,'failed':1,'skipped':2}
oldhash='308205ec6273dafe3fb0b2f5273e713803e6e78ea989d883217ecd813a17d32b'
oldsource='6a89189d601467eeff33d304c2c9b69cdd2e6d0b'
published=i['published_chapter'];recall=i['recall']
current=f'''## Current package-08 installed observations

Setup and same-version reinstall each exit zero. All {i['installed_files_compared']:,}
installed destinations match the seal, with {i['recognized_generated_files']} recognized generated files.
Observed ordinary registry, startup and shortcut state is unchanged. This is a
separate app/data/credential namespace in the same non-elevated Windows account.
The earlier isolated package-07 app was uninstalled; its receipt profiles remain.

C22 retains {i['c22_raw_counts']['pass']} passed, {i['c22_raw_counts']['fail']} failed
and {i['c22_raw_counts']['unexecuted']} unexecuted manual placeholders. The separate
Setup and four actual browser images support the independent review. Consent,
charge and worker_lost recovery state agree before viewing, afterward and after
stop. Raw placeholders remain unchanged. Installed synthetic decoder and
encryption checks pass with exact restoration of temporary instrumentation.

The Phase 4 collector retains 15 passed, zero failed, one blocked, five unobserved
and two pending-review rows. Two actual CLI sessions each have 20/20 exact packet
comparisons. Native prompts and the production-published chapter export have
separate observed results. The five actual subscription sessions record
{i['actual_client_tool_calls']} calls and {i['successful_terminal_hooks']} successful terminal
hooks, with {i['failed_terminal_hooks']} failed hooks and zero sentinel calls.
Sentinel discovery requests ({i['sentinel_discovery_requests']}) are separate from calls.
Recall's silent unavailable-storage result took {recall['elapsed_ms']:.4f} ms;
it establishes no positive context-injection behavior.

The fresh native Uoink GUI observation is reviewed separately in
[the native verdict](NATIVE-GUI-PACKAGE-08-OBSERVATION-2026-09-12.md).
It uses the installed dashboard, a new synthetic profile and port 18484.
Its original images and action records establish only the enumerated flows;
no native AI-client citation, brief or chapter-player interaction is inferred.
The original package-07 note/media defects and Desktop failure stay retained.

See [the installed verdict](ASTRA-INSTALLED-PACKAGE-08-VERDICT-2026-09-12.md),
[installed proof](proof/ryan-agent-installed-08-2026-09-12/SHA256.json) and
[native proof](proof/native-gui-package08-2026-09-12/SHA256.json).

## Desktop isolation incident and acceptance boundary

The earlier Claude Desktop attempt was not isolated as claimed. Packaged Claude
discarded the proposed user-data override and launched the ordinary Uoink and
filesystem connectors. Their earlier live-index or port-5179 effects are unknown.
The owned job was empty and the test interpreter guard restored afterward;
those cleanup facts cannot establish absence of earlier effects. Astra told Ryan
and withdrew the claim. No live-index, ordinary auth/config or resident-port
probe was made to investigate.

The package-08 native driver exposes only the separately guarded Uoink dashboard.
Desktop GUI acceptance remains blocked until a supported isolation method is
verified before launch, or a clean separate Windows account/VM is prepared with
only the test connector and human sign-in. Do not bypass vendor checks or reuse
the failed override. The verified CLI configuration path remains a separate
CLI observation. Read [the incident](NATIVE-CLIENT-ISOLATION-INCIDENT-2026-09-12.md)
and [Astra's correction of Gemini's review](ASTRA-NATIVE-CLIENT-ISOLATION-REVIEW-2026-09-12.md).

'''
notes=(d/'RELEASE-NOTES-LIVING-LIBRARY.md').read_text(encoding='utf8')
start=notes.index('Package-07 contains');end=notes.index('## What the phases deliver')
notes=notes[:start]+f'''Package 08 includes the native note and saved-media repairs at `d2caac5`
and `60d203f`. Its complete tree at `b8e44fb` records **2,579 passed, one
historical failure and two skips**. Actual isolated installation, browser and
CLI observations are complete; native Uoink GUI results have their own verdict.
Desktop GUI acceptance, retained dependency findings and the historical receipt
remain release holds. The candidate is not approved for an ordinary upgrade.

The library supports evidence retrieval, reviewable shelf proposals, consented
standing capture, native resources and prompts, an optional file mirror,
descriptive activity reports, and chapters with cited ranges. No main merge or
publication occurred. Installation is not a security certification.

## Package and verification

| Item | Recorded value |
|---|---|
| Installer | Uoink-Setup-3.8.0.exe, package-08 |
| Build and complete-tree source | `{p['build_source']}` |
| Bytes | {p['package_bytes']:,} |
| SHA-256 | `{p['package_sha256']}` |
| Bundled runtime | Python 3.13.15, MCP 1.28.1, schema 30 |
| Build interval, UTC | {b['started_utc']} to {b['finished_utc']}; {b['elapsed_s']:.3f} seconds |
| Complete-tree result | 2,579 passed, 1 historical failure, 2 skipped; 2,582 cases |
| Actual installation | Same-account Agent Install 08: Setup/reinstall exit 0; all 32,497 files match |

The [package seal](proof/candidate-package-08-2026-09-12/SHA256.json) records
32,506 compiler inputs: 32,497 installed destinations, eight wizard images and
one setup-only script. All 142 source bindings match. The installed comparison
matches all destinations and accounts for three expected generated files.
All 140 runtime pins and 283 active requirements match, as do 983 compared
repair-wheel payloads. Installation-rewritten RECORD files are excluded explicitly.

Fifty license fields use exact packaged License-Expression metadata; seven
missing declarations stay unknown. Original generated notices are retained.
Notices are outside the installer payload. No packaged source changed after
the full tree. See [the package verdict](ASTRA-PACKAGE-08-VERDICT-2026-09-12.md)
and the [runbook](INSTALL-RECEIPT-RUNBOOK-2026-09-09.md). Preserve completed
agent stages and earlier installers/ZIPs.

'''+notes[end:]
needle='| SQLite deadline cleanup | `d812785` | 97 passes in each root; four old-code failures / one pass, then all five regressions pass in the complete tree |'
assert needle in notes
notes=notes.replace(needle,needle+'\n| Native note display and readiness | `d2caac5` | 60 passes in each root; 16 new negative/positive cases, original worker shortcuts rejected |\n| Saved media details and truthful timing | `60d203f` | 58 passes in each root; 23 new cases cover authenticated bounded reads, stale selection, private metadata and unsupported timestamps |',1)
needle='Remaining model-loader advisories require a release decision.'
notes=notes.replace(needle,'''The September 12 Gemini backport review is integrated at `43b42bc` after
Astra corrected unsupported reachability claims. Separating the verified Lightning
patch leaves 18 entries / 14 groups; the raw 19 / 15 is retained without suppression.
Default VAD reaches weights_only=False before the speaker branch. That trace
does not prove every advisory is reachable. Safetensors is already installed;
simply switching a loader flag is not a qualified migration.

The remaining migration needs Ryan's exact authorization for the frozen Torch
2.8.0 / WhisperX 3.8.6 compatibility assertions and an isolated checkpoint/model
qualification protocol. Current scope prohibits that execution. No unverified
version list or proposed test weakening is adopted. Read
[the corrected feasibility review](ASTRA-SECURITY-BACKPORT-REVIEW-2026-09-12.md).
Remaining model-loader advisories require a release decision.''',1)
notes=notes.replace('This host has no Windows\nSandbox; no elevation, system-feature installation or protection downgrade was\nused.', "Sky's app inventory returned no Windows Sandbox entry; no separate account/VM\nis prepared. This does not establish that every VM option is unavailable. No\nelevation, system-feature installation or protection downgrade was used.",1)
notes=notes.replace('## Current package-07 installed observations',current+'## Historical package-07 installed observations',1)
notes=notes.replace('| `6a89189` (explicit --runxfail)',f"| `b8e44fb` (explicit --runxfail) | 2,579 | 1 | 2 | 0 | {t['seconds_including_collection']:.3f} |\n| `a25e3be` (explicit --runxfail) | 2,556 | 1 | 2 | 0 | 1500.638 |\n| `6a89189` (explicit --runxfail)",1)
start=notes.index('All 2,543 cases are accounted for once:');end=notes.index('\n\nThe original AT6',start)
notes=notes[:start]+'''All 2,582 cases are accounted for once: the prior 2,559 plus 23 media regressions,
with none missing. The aggregate remains FAIL because the historical AT6 exit
assertion fails. Existing tests and fixture guards are unchanged. See
[the qualification verdict](ASTRA-PACKAGE-08-VERDICT-2026-09-12.md) and
[tree seal](proof/ryan-final-partitioned-06-2026-09-12/SHA256.json).'''+notes[end:]
old='- Package-07 installation and bounded CLI observations are complete. Native-client GUI citation/brief/chapter acceptance remains unobserved; the current agent has no native client UI surface. Positive Recall injection and per-session combined prompt/template completeness are not claimed. Release scope must preserve these limits.'
assert old in notes
notes=notes.replace(old,'- Package-08 installation and bounded CLI observations are complete. Native Uoink dashboard checks are separate. Desktop citation/brief/chapter acceptance remains blocked by the documented isolation failure; positive Recall injection and per-session combined prompt/template completeness are not claimed.',1)
old='No live library index, resident helper on 5179, paid API or live label application\nbelongs to this verification. No X access repair or new source-media fetch is\nincluded.'
assert old in notes
notes=notes.replace(old,'The live index and resident port remain prohibited. The earlier Desktop attempt\nviolated the intended connector boundary; its prior effects are unknown as stated\nabove. No paid API, live label application, X access repair or new source-media\nfetch is authorized by these instructions.',1)
notes=notes.replace('## Current review kit (package-07)','''## Package-08 review kit

The accompanying review ZIP pairs this installer with the matching notes,
receipt tools and evidence. Its `.receipt.json` records the actual ZIP hash,
size and source commits; BUNDLE-SHA256.json binds every payload. It retains
release_ready=false. Creation and transport verification are recorded separately
in RELEASE-DELIVERY-08-2026-09-12.md; this document does not invent a self-referential
ZIP hash before the archive exists.

## Historical review kit (package-07)''',1)
(d/'RELEASE-NOTES-LIVING-LIBRARY.md').write_text(notes,encoding='utf8',newline='\n')
runbook=(d/'INSTALL-RECEIPT-RUNBOOK-2026-09-09.md').read_text(encoding='utf8')
start=runbook.index('Ryan delegated');end=runbook.index('## Before you begin')
runbook=runbook[:start]+f'''Ryan delegated the installation check to Astra. Package 08 has actual same-account
Setup/reinstall, 32,497 matching installed files, 11 C22 passes and independent
browser review. The original P4 collector retains 15 passed, one blocked,
five unobserved and two pending-review rows. Independent CLI review has 20/20
exact comparisons in each paired session; native prompts and a separately
published chapter export have their own observations. Read
[the installed verdict](ASTRA-INSTALLED-PACKAGE-08-VERDICT-2026-09-12.md) and
[native Uoink verdict](NATIVE-GUI-PACKAGE-08-OBSERVATION-2026-09-12.md).

The completed isolated CLI sign-in and extra-paid-usage-off confirmation need
no repetition. Preserve Agent Install 08 and its collected P4 fixture. The steps
below are for one separate fresh Windows-account receipt if that scope is needed;
they do not ask Ryan to repeat the completed agent installation.

Claude Desktop's earlier profile override failed and launched ordinary configured
connectors. Its earlier live-index/5179 effects are unknown. Desktop GUI acceptance
is blocked until configuration isolation is verified in a separate environment.
Do not launch ordinary Desktop under CLAUDE_USER_DATA_DIR, copy credentials or
try guessed flags. The CLI commands below are for Claude Code only. A future
Desktop workflow needs its own supported setup and human sign-in before GUI checks.
See [the incident](NATIVE-CLIENT-ISOLATION-INCIDENT-2026-09-12.md).

Build and complete-tree source are `{p['build_source']}`: 2,579 passed,
one historical failure and two skips. No packaged source changed afterward.
This procedure does not approve an ordinary upgrade, main merge or publication.
Every new observation gets fresh paths; the throwaway account needs existing
write access to the receipt directory. A refusal is retained, not bypassed by
elevation or permission changes.

Use **{p['package_name']}**, {p['package_bytes']:,} bytes, SHA-256
`{p['package_sha256']}`, with its accompanying package-08 tools and seal.
Earlier packages and their failed or partial results remain historical artifacts.

'''+runbook[end:]
runbook=runbook.replace(oldhash,p['package_sha256']).replace(oldsource,p['build_source']).replace('candidate-package-07-2026-09-12','candidate-package-08-2026-09-12').replace('Ryan Receipt 2026-09-12','Ryan Receipt Package08 2026-09-12')
old='The only already-authorized external player example is `D_FCYsshMI4`, “Why computer use,” 0:34. Preserve any unavailable affordance. Do not substitute synthetic chapter text for a real source quotation or claim speaker accuracy.'
assert old in runbook
runbook=runbook.replace(old,'The historical BD-27 player receipt records `D_FCYsshMI4`, “Why computer use,” 0:34; no new external fetch is authorized here. Preserve unavailable affordances and keep the synthetic stored range distinct from a real source quotation. No speaker accuracy claim.',1)
(d/'INSTALL-RECEIPT-RUNBOOK-2026-09-09.md').write_text(runbook,encoding='utf8',newline='\n')
print(json.dumps({'updated':['release notes','runbook'],'package_sha256':p['package_sha256'],'release_ready':False}))
