# Agent installation review, 2026-09-09

Ryan delegated the installation check. This host is Windows 11 Home without
Sandbox and the agent is not elevated. Review scripts/install_receipt/agent_install.ps1
as a concrete supplement to the existing runbook. Do not execute it. The intended
receipt is honestly a per-user Inno installation under the same Windows account,
with fresh app/data directories and profile-derived isolated credential namespace.
It must never be called a separate throwaway Windows-account observation.

Gemini: read the driver and its actual Inno call targets, including marker checks,
verify_install.ps1, normal/isolated registry entries, tasks, shortcuts and startup.
Write docs/library/GEMINI-AGENT-INSTALLATION-REVIEW-2026-09-09.md early. No edits to
existing files, no installer or helper run, no process stop, no keyring/credential
query, no live index or port 5179, no network, no paid API, no subagents. Existing
isolated credential tests and the ddfd316 review establish the code repair; the
new package is still required before execution.

Check actual scope: a fresh subtree of checkout/_scratch only, no reparse aliases,
separate isolated AppId, non-elevated process, no replacement of any previous
isolated install, exact package digest, explicit close/restart suppression,
desktop task disabled and a unique Start Menu group. Record actual residual
same-account effects. Review ordinary registry/shortcut hashes, stage/identity
and exit recording, same-version reinstall checks, and failure retention.
Do not call Defender results a security certificate or confuse a static check
with an actual receipt. Flag concrete defects with exact lines and bounded repairs.

Astra must inspect the report, correct findings, parse the final script, bind it
to the newly sealed installer and prepared C22 profiles, then execute it only
when these boundaries are satisfied. Installed C22/P4 and actual browser evidence
follow; no speaker runs, model downloads, live library, 5179, paid API or main merge.
