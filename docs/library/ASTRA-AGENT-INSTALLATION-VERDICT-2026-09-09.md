# Agent installation procedure: review verdict, 2026-09-09

The corrected procedure is ready to bind to a new sealed installer and prepared
C22 inputs. It has not been executed. The host/account limits remain: a
non-elevated per-user installation under RYAN-PC\\hello, fresh app/data paths,
separate isolated uninstall entry and credential namespace, and a dedicated
Start Menu group. This is not a new Windows account or an OS sandbox.

Gemini 6a8378f1 correctly identified the ignored /GROUP setting; Astra confirmed
it in Inno's official command-line documentation. DisableProgramGroupPage is now
no, with the page skipped in code. The explicit group can take effect without
adding a wizard step. The driver checks all four actual shortcuts, their target
paths/arguments and hashes, and compares ordinary shortcuts/autorun/uninstall
registry hashes before and after. Its desktop task is explicitly deselected.

Gemini also found that Setup's exit zero does not prove files-only verification
passed. An initial proposal to raise inside VerifyInstalledHelper failed the
existing non-fatal contract test: 87 passed / one failed, 12.58 seconds. That
proposal is rejected and retained in the seal. The final procedure preserves
the installer behavior and makes the receipt driver require its separate fresh
verification log to report success. Setup's raw exit remains an observation;
a failed later driver check prevents receipt acceptance. No test was edited.

Final isolation, credential and installer companion union: 93 passed, 12.80 s.
PowerShell parses successfully. ISCC compiles the exact revised Inno source with
dummy payloads, exit zero in 0.81 s; its source and copy hashes match. That is a
compiler check, not a package build or installation. The real build, package
inventory and Defender scan are still required before executing this procedure.

The raw Gemini report is preserved. Two points are corrected here: the fixed
checkout path is intentional scope for this agent-only tool, and the actual
credential namespace is Uoink-isolated- plus a 32-character digest. The report's
colon-separated example is not the implementation. Cloud-routing variables are
also removed from the driver process environment for consistency with the runbook.

Execute only against a newly sealed package after the complete corrected tree.
Record the actual user/SID, installer and driver outcomes, Inno/file-check logs,
marker and shortcut/registry effects. Then run the original installed C22/P4
routes and observe browser/everyday flows. No normal launcher, live index,
port 5179, real saved-key query, model download, diarization, paid API or main
merge is part of this procedure. Retained dependency advisories remain in the
release notes; this review is not a security certification.
