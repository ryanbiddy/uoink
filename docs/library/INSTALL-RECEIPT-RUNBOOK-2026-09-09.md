# Living Library: Ryan's installed receipt session

Status: **blocked before installation with the current package**. This runbook
does not authorize contacting port 5179. Run the preflight below once; do not
launch the installer when it reports the block. The remaining sections specify
the receipt session and evidence required after the product repair is reviewed.

The blocker is in shipped code. Inno's `PrepareToInstall` always runs
`upgrade_prep.ps1`, whose initial port check probes 127.0.0.1:5179. Silent installation
does not skip that hook. The normal helper launcher also probes/binds the fixed
port. A different Windows account does not isolate TCP ports on the same host.
See [the product repair brief](INSTALL-ISOLATION-REPAIR-BRIEF-2026-09-09.md).
No installed receipt has been produced by this runbook.

## 1. Run this preflight once

Use a new throwaway Windows account with no Uoink/Yoink installation or client
credentials. Stay signed into that account for the session. Do not use Ryan's
ordinary profile or import its settings, registry or live database. Copy only
the named installer and this runbook to that account's Downloads folder. The
later installed interpreter must not resolve modules from a checkout or the
integrator's user-site packages.

Open PowerShell and run the following. It reads the installer, records a fresh
receipt folder and stops before invoking any installer or helper:

```powershell
$ErrorActionPreference = 'Stop'
if ($env:USERPROFILE -ieq 'C:\Users\hello') {
    throw 'Use the throwaway Windows profile, not Ryan''s ordinary profile.'
}
$receiptRoot = Join-Path $env:USERPROFILE 'Documents\Uoink Install Receipt 2026-09-09'
if (Test-Path -LiteralPath $receiptRoot) {
    throw 'This receipt directory already exists. Preserve it; do not overwrite or rerun.'
}
$receiptPackage = Join-Path $env:USERPROFILE 'Downloads\Uoink-Setup-3.8.0.exe'
$receiptExpected = '9defc2a98ba680f8b4cdf06bdd09eadbb1153f2028070881b5472ce97f7e927d'
$receiptActual = (Get-FileHash -LiteralPath $receiptPackage -Algorithm SHA256).Hash.ToLowerInvariant()
if ($receiptActual -ne $receiptExpected) { throw 'Package hash differs from the frozen candidate.' }
New-Item -ItemType Directory -Path $receiptRoot | Out-Null
$receiptPreflight = [ordered]@{
    utc = [DateTimeOffset]::UtcNow.ToString('o')
    windows = [Environment]::OSVersion.VersionString
    user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    profile = $env:USERPROFILE
    installer_source = 'e47e4f2e8e1b6a83ecb1171436092b9077186430'
    package_sha256 = $receiptActual
    package_bytes = (Get-Item -LiteralPath $receiptPackage).Length
    status = 'blocked_before_installation'
    reason = 'Current Inno preparation and normal helper startup contact prohibited port 5179.'
    installer_started = $false
    helper_started = $false
}
$receiptPreflight | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $receiptRoot 'preflight.json') -Encoding utf8
$receiptPreflight | ConvertTo-Json
throw 'STOP: do not run this installer. Retain preflight.json for Astra.'
```

The expected artifact is 339,042,658 bytes, built from `e47e4f2`. A reviewed
replacement will have its own source and artifact hashes. Do not change the
expected hash locally to bypass this preflight. No install command that satisfies
the current no-5179 rule exists for this artifact; one must come from the repair.

## 2. Required preparation after the product repair

Before asking Ryan to install, Astra must supply a revised, hash-bound operator
kit with the exact supported isolated install, start, stop and relaunch commands.
The kit must refuse a normal profile, an occupied/unapproved port, any path outside
the receipt root and any missing fixture. It must bind the installed application,
fixture inputs and each child process to the receipt. Do not substitute the S21
overlay or source-staged smoke for an installed production-path observation.

The single operator session needs two isolated data profiles, `empty` and
`populated`, under the receipt root, plus an installed application directory with
a space in its path. Use a synthetic legacy database for migration and only a
prepared copy of already-held evidence for the reading flows. Every SQL, sidecar
and embedded path must point into the receipt root before startup. Never open the
live index to make these fixtures. No new source fetch, media download, model or
diarization is part of this session.

Freeze expected complete evidence, IDs, source/timing fields, revisions and
hashes independently from stored fixture data before the client reads it. The
fixture must include one timed item, one text-only item, a prepared cited brief
and chapter annotations. Keep `librarian_apply_enabled=false`; no accepted
assignment becomes an applied shelf. Keep autonomous filing's 0.90 rule.

## 3. Installed execution order and C22 evidence

AS-7's authoritative list is in
[PHASE3-ACCEPTANCE-7-2026-09-08.md](PHASE3-ACCEPTANCE-7-2026-09-08.md), under
“C22 remains the installed-build gate.” AS-9 later closed its other Phase 3
findings. Execute the following once in the revised kit's declared order. An
unexpected failure ends that scenario; retain it and do not improvise a retry.

| Step | Ryan does | Astra collects and checks |
|---|---|---|
| Install | Run the revised kit's exact isolated Inno command. Record the finish screen and exit. Do not use the ordinary shortcut or enable login autostart. | Installer/source hashes; full argument vector, UTC start/end, exit code, Inno and upgrade-prep logs; installed paths and shortcut/registry effects. |
| Installed provenance | Run the kit's installed-runtime inventory from the spaced path with checkout/user-site resolution absent. | `sys.executable`, Python 3.11.9, MCP 1.27.1, dependency inventory, module `__file__` paths and hashes, subscription module, migration 0028, final schema 30 and registry schemas. Source-only imports receive no installed credit. |
| Empty migration | Start on the empty profile, stop through the supported path, then reopen the same profile. | Complete migration history, counts, integrity/foreign-key checks and before/after state proving replay does not invent or duplicate rows. |
| Populated upgrade | Open the prepared legacy fixture, perform the actual installed upgrade path, then replay once as specified by the kit. | Original fixture hash, migration/upgrade commands and exits, retained item/citation/work identities and exact expected changes. A same-version reinstall must be labeled as such, not a cross-version upgrade. |
| One-off capture | Run the kit's unrelated fixture capture while standing capture is off. | Consent state before/after, item identity, publication outcome, and zero standing charges for that unrelated manual action. Only acquisition/transcript bytes may be synthetic. |
| Manual first | Complete the declared manual fixture capture, then opt that same source into standing capture through its consent flow. | Source/episode/item identities, enrollment, all ledger and charge rows, publication receipt, and no duplicate capture/publication. |
| Standing first | In the other prepared case, consent first, complete the standing capture, then request the same manual item. | Same identity/deduplication evidence, one eligible standing charge, one publication, and the recorded manual outcome. |
| Real restart | While the kit's owned fixture child is demonstrably alive, terminate the actual installed helper process by its recorded PID and creation identity. Relaunch through the reviewed installed path. | Old/new helper PIDs and creation markers, incarnation/claim/lock files, child lifetime, unchanged charges, no duplicate launch and settled ownership only after death/publication is established. Pair the post-restart browser image with persisted state at the same observation time. A listener restart does not count. |
| Launch interruption | Execute the kit's declared interruption between launch preparation and child registration. | Actual child identity/liveness, unresolved-launch state, retained claim/exclusion, restart behavior and eventual settlement. No invented exit marker or “stopped” claim from a missing PID. |
| Registration failure | Execute the separate fixture registration-failure scenario. | Failure injection description, actual launch/registration events, surviving child evidence, charges, refusal/no duplicate launch, cleanup and ownership release. Do not replace this with the interruption case. |
| Protected state | Finish with the kit's after-state capture. | Phase 2 protected file/table hashes, settings, taxonomy, manifest, work/run/attempt and shelf state; enumerate expected fixture-only enqueue changes. Zero live labels applied. |

C22 process cases must record zero model/client spawns. Run any Phase 4 client
session separately, with separate logs and allowlists; do not describe its model
requests as part of a zero-model C22 case. Network/process/file instrumentation
must establish no port 5179, resident-helper or live-index access. A blocked
forbidden attempt is evidence to investigate, not a zero-attempt pass.

## 4. Phase 4 installed receipt and everyday checks

Use only the installed interpreter and original installed stdio entry, from the
spaced path. Record initialization, all returned tools, five resource templates
and four prompts. The expected current inventory is 32 tools; compare actual
names/schemas and explain any difference. The exact tap, guarded launch, client
configuration and expected packets must be included and hashed in the revised kit.
Keep full JSON-RPC frames and stderr separate. Synthetic stdio and actual client
observations must have separate labels.

For the actual client portion, Ryan uses a disposable Claude Code profile with
subscription authentication and usage credits off. Record the actual version,
mode, model, allowlist and launch. Never set an API key, enable paid credits or
reuse normal-profile credentials/configuration. A capacity refusal is retained;
there is no automatic fallback to paid usage. The approved X HTTP 403 needs no
retry and no replacement source. No isolated Desktop result is required or claimed.

1. **Retrieve evidence.** Ask for the kit's named held timed item, then its full
   card and a cited excerpt. Repeat via native resource and fallback routes.
   Compare every returned character and revision with the frozen expected packet.
   Repeat on the text-only item, preserving null timing fields.
2. **Follow a citation.** Open the returned local evidence/corpus citation and
   compare the complete quote with the held source. Record target URI, source ID,
   timestamp, screenshot and browser address. Use the existing approved public
   video only if the kit explicitly declares that observation; do not fetch a
   new source. X remains blocked and is not a successful click.
3. **Open a brief.** Open the prepared fixture brief through the actual client,
   follow one citation to its source and record the full response. Invoke native
   `consult-library` and `reshelve-review`; retain actual `prompts/get` traffic.
   A prepared brief is not evidence of client-authored publication. If publication
   is included in the kit, retain its packet, restart, citations, receipt, exact
   retry and stale refusal separately. Preview remains report-only and unapproved.
4. **Jump to a chapter.** Use the kit's chapter-bearing held item, open its chapter
   list and follow the declared target. Record the title, range, actual displayed
   player time and image. The previously observed example is video `D_FCYsshMI4`,
   chapter “Why computer use,” at 0:34. Do not repeat it unless it is explicitly
   included in the revised kit's allowed observation. No speaker-accuracy claim.
5. **Reconnect and failures.** Preserve old/new child IDs and complete unchanged-
   item responses for one explicit reconnect. Separately observe live-child
   unavailable storage with no replacement empty database, and broken transport.
   Measure from each actual request: storage refusal within two seconds, client
   transport failure within 15 seconds and at most one explicit reconnect.
6. **Action safety and optional mirror.** Retain actual tool requests, permission
   decisions and before/after sentinels for the kit's hostile source fixtures.
   Record Recall's silent failure separately. For the fixture-only mirror,
   disconnect/reconnect, preserve an independently edited file and delete the
   declared source; account for every owned/temp/pending/conflict entry afterward.

The existing two client receipts remain historical evidence. Missing UI affordances,
blocked links, partial scenarios and failures stay labeled; an empty denial list or
a model saying it complied does not establish the result.

## 5. What to return to Astra

For the current artifact, return only `preflight.json`; installation must not
have started. After a repaired, approved kit is available, retain the complete
private receipt directory and provide its path. Astra collects:

- Candidate/package/installed-source hashes, exact commands/exits and environment
  provenance; all installer, upgrade, stdout/stderr and client logs.
- Full protocol/action traces, screenshots with scenario IDs/UTC times, complete
  expected and actual packets, and before/after semantic snapshots.
- Closed disposable database snapshots and fixture corpus/sidecars for private
  verification, integrity/foreign-key results, charges, claims, incarnations,
  child identities and ownership settlement evidence.
- Protected Phase 2 hashes, settings/apply state, an explicit scenario outcome
  table, elapsed times, all deviations and the exact list of unexecuted checks.

Stop only recorded task-owned processes. Do not uninstall through an unreviewed
stop script, delete failed evidence, remove another profile or overwrite a receipt.
Raw databases and credentials never enter Git. Astra seals reviewed artifacts,
labels any redacted copy with its own hash and issues separate C22 and Phase 4
verdicts. An installed package is not automatically an accepted package.
