# Inno process and path boundary repair — 2026-09-09

The second isolation patch has 113 worker passes and one existing skip. Its
Python ownership repair is useful, but Inno still has concrete unsafe paths.
Preserve that patch and its results. No installation has been executed.

Apply `docs/library/proof/ryan-install-review-02-2026-09-09/original.patch`
in a fresh Control Room worktree. Own only `installer/uoink.iss`, a new
regression file and your report. Preserve every existing test unchanged.
Write the report early as `RYAN-INNO-FINAL-BOUNDARY-WORKER-2026-09-09.md`.

1. Isolated mode still has `CloseApplications=force`. Skipping `wpPreparing`
   does not disable Restart Manager: Inno never calls ShouldSkipPage for that
   page, and RegisterExtraCloseApplicationsResources only adds resources.
   Require the documented `/NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS`
   switches before installation and refuse positive `/CLOSEAPPLICATIONS`,
   `/FORCECLOSEAPPLICATIONS` or `/RESTARTAPPLICATIONS` overrides in any order.
   Missing or contradictory isolated parameters must refuse, not select
   ordinary mode. Keep ordinary update behavior. Remove the misleading skip
   claim. Existing static checks are frozen; do not edit them.
2. `InitializeUninstall` currently returns true on damaged metadata, and an
   UninstallRun nonzero exit does not gate deletion. Validate isolated mode
   and marker, call the exact owned stop before deletion, and return false on
   missing/damaged evidence, launch failure or nonzero stop. Never fall back
   to the ordinary stop. Keep the normal uninstall behavior. Check official
   runtime support instead of guessing. GetPreviousData does work during
   uninstall using UninstallExpandedAppId in Inno's source; persist enough
   information to refuse safely when a marker disappears. Verify the result
   of persistence, not merely the presence of its call.
3. ExpandFileName/GetLongPathName/GetShortName do not resolve junction targets.
   Refuse a reparse point in every existing app/profile ancestor before any
   marker read, extraction, stop or directory creation, or resolve through
   a documented handle method. Reject device/UNC paths and ambiguous Windows
   names if unsupported. Revalidate at PrepareToInstall. No filesystem or
   process operation may touch a forbidden default library through an alias.
4. The marker parser still uses Pos to find a key and accepts numeric prefixes
   and duplicate/nested keys. Make its accepted format unambiguous and bounded;
   fail on malformed/mismatching markers before mutation. Existing ordinary
   installations must never be adopted as isolated.

Primary sources reviewed by Astra:
- [Setup switches](https://jrsoftware.org/ishelp/topic_setupcmdline.htm):
  positive close/restart switches override the negative switches.
- [Script events](https://jrsoftware.org/ishelp/topic_scriptevents.htm):
  no ShouldSkipPage call for wpPreparing; InitializeUninstall false aborts.
- [Runtime implementation](https://raw.githubusercontent.com/jrsoftware/issrc/main/Projects/Src/Setup.ScriptFunc.pas):
  GetPreviousData uses the installed AppId during uninstall.

Add meaningful new regressions for each correction. Compile the exact script
with dummy staging in a fresh scratch output, retain source/hash/log/exit,
and never execute Setup or uninstall. Run the same fourteen-file union named
in the previous worker report plus your new tests, under the sealed integrator
guard with C:\Python314\python.exe. Record failures and repair before any
rerun. Report unexecuted installed boundaries explicitly. Astra verifies the
worker and checkout before integration. Do not edit the Python ownership
module unless a separate concrete failure is reported to Astra.

No subagents, API keys, paid API, live index access (including hashing it),
5179 contact/bind/probe, external source fetch, client/model run, commit,
push, main merge or acceptance test edits. Subscription Grok only.
Coordinate the final safe switches through Astra to both receipt kits.
