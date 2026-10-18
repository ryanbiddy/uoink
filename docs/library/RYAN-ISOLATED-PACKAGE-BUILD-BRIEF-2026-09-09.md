# Isolated candidate package build — 2026-09-09

The retained package is from e47e4f2 and cannot run the isolated receipt session.
Production source changed after the corrected tree: mirror lifetime, SDK wire
settlement, media refusal, startup anchors, read-only opening and install isolation
are now integrated. The complete 8fc6a40 observation includes all current product
source: 2,254 passed / ten failed / three skipped / one xfailed. The additional
failure is reproduced as an older test's replaced getter; both fixture proposals
remain unapplied. Neither this diagnosis nor compilation makes a failed test pass.

Build one replacement candidate now while receipt instruments finish. Freeze the
next committed source and verify there is no packaged source change since 8fc6a40.
Retain and hash-check the old executable before the build. Use the reviewed
build_library_candidate.ps1 wrapper, with its checked workspace-only recursive
targets, private environment, existing download cache and no Clean switch. Compile
only: no Setup, uninstall, 5179, live index, key, paid API, fetch of library media,
client/model, label application or publication.

Before any runtime instrument changes staging, inventory the actual compiler
inputs, bind every product file to the frozen checkout and its Git blob, and hash
the resulting executable. Record exact commands, exit, duration, dependency lock
check and compiler output. This is compiler-input evidence, not an extraction
of installer bytes or an installed receipt.

The final verified receipt kit must exercise the original bundled stdio entry
and helper with disposable fixtures. Retain every failed attempt and its repair
brief. Final kit-inclusive tree still runs on a committed SHA. If packaged source
changes, rebuild and reseal; if only notes, kit or fixtures change, verify all
packaged source bindings remain identical and retain this package's original
build commit. Final notes state both build source and validation commit. The
complete operator runbook receives the actual hash and executable kit commands.

## Preflight correction before compilation

The first source comparison used a recursive *.py pathspec that also selected
archived proof scripts under docs; it stopped before checking the retained
artifact. A separate wrapper invocation supplied an incorrect short candidate
argument and was refused by its exact-SHA check before any build began. Neither
attempt compiled or changed the installer. Preserve both as failed preflights.
Correct the comparison by excluding docs and tests, verify the retained package
hash, and pass the actual full git rev-parse HEAD result to the wrapper. These
are argument/check corrections, not product changes or test edits.
