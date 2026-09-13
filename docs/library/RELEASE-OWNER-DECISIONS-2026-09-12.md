# Decisions still needed for the Living Library release

The installed review build works for the recorded native Uoink and Claude Code
flows. It is not ready for an ordinary upgrade or public download. Independent
repair and packaging work continues; the items below are the choices the current
handoff reserves for Ryan. This document records proposals, not approvals.

| Decision | Concrete choice and effect | Evidence needed before execution |
|---|---|---|
| Publisher signing | Select the publisher identity/certificate and HTTPS timestamp service. Use the repaired build's explicit certificate selector; do not buy a service, install trust roots or choose a certificate automatically. | SigningCertificateThumbprint, TimestampUrl and the approved signing mechanism. The existing SDK SignTool path is available; no Uoink signing certificate was found. Both installer and uninstaller must verify afterward. |
| Claude Desktop isolation | Provide or authorize a fresh standard Windows account or VM, then complete its normal client sign-in. Do not reuse the failed profile-override technique. | Verify a different account/SID, fresh client configuration, no ordinary connectors or copied credentials, and access only to the test installation/profile. Inspect configuration before launch. No live-index/5179 probe is allowed. |
| Historical AT6 evidence | Decide whether the original missing child-exit record blocks release or can be disclosed as an unrecoverable historical receipt gap. | Keep the original failing assertion, replacement receipts and failure count. A successful new run cannot recreate the old exit status. This decision gives no security or client acceptance. |
| D1 static VAD inspection | Decide whether to inspect only two 500-byte buffers and two version bytes from the fixed existing checkpoint, using the reviewed adapter and fixed consistency basis. No model, pickle evaluation, conversion or network. | The concrete adapter is reviewed at 381985c with 54 synthetic passes in each root. See ASTRA-VAD-D1-ADAPTER-VERDICT-2026-09-13.md. Real inspection remains disabled; any result requires review before a separate conversion decision. |
| Model-stack migration | Review the exact future dependency/source patch and isolated model protocol before authorizing execution or frozen compatibility-test changes. No target stack is approved yet. | A compatible artifact manifest, loader and download-policy review, preserved original test expectations, proposed exact replacement assertions, and before/after quality criteria. The rejected Torch 2.10/Transformers 5.10 proposal cannot fill this role. |
| Publication | Approve the final artifact set and public claims after technical qualification and the earlier decisions. | Final source/installer hashes, complete-tree counts, installed/client receipts, signing result, notes, upgrade/rollback steps, product-page preview and working links. Branch backup alone does not approve a release or main merge. |

For later model qualification, the proposed boundary is a fresh isolated account
or VM, no ordinary credentials or library, no resident helper, and only approved
synthetic audio plus explicitly hashed model artifacts. Runtime network access
stays blocked. Model conversion or deserialization must use a reviewed path that
cannot select arbitrary classes from checkpoint metadata. Record real exits,
refusals, output differences and quality results, including failures. No
diarization is proposed. This describes the required protocol; it does not
authorize a model download, loading the existing checkpoint, inference, or a
specific dependency-test change.

Phase 2 suggestions-only scope, the 0.90 autonomous threshold, apply=false,
the X blocked-link condition, no speaker claims and deferred Phase 5 Part B are
already decided. Ryan does not need to approve them again.

Updated 2026-09-13. The latest production repair is71d3e70: notice generation
and installer attribution, with20 Python and10 inert build-block cases passing
in each root. It follows e8d058f's53 focused passes and13 passing subtests in each
root. Complete tree09 at56d9d4c predates both repairs and remains2,796 passed,
one failed, three skipped, plus13 subtests.
Package 08 still represents b8e44fb; no current-source package or installation
credit exists. The latest completed branch backup is 901964c (2026-09-13). Preserve these
separate identities until replacement build and qualification are complete.
Website and marketing remain paused until council and integrator accept Uoink.
