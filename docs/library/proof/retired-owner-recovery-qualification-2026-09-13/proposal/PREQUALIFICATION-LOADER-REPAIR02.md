# Selected-case loader setup repair — 2026-09-13

The first frozen qualifier passed a full module.Class.method name to unittest without an explicit module. Peer source review identified the installed loader's speculative import and failed-import traceback path. That path could encounter the already closed import/content/metadata guards before running a case.

The one-line repair splits each unchanged pinned ID once and passes its class.method suffix together with the already loaded exact module object. The 22 IDs, test bodies, assertion bodies, result accounting, module ordering and all guard code stay unchanged. No imports are added or admitted.

The previous qualifier, diff, PINS, false template, protocol, passive result and source-preservation report are retained under before/prequalification-loader01-*. Their old observations remain tied to those old bytes. PINS and the false fake admission template are regenerated for the repaired qualifier. The native source map and native launcher are unaffected.

No qualification has run. This is a pre-execution instrument repair, with root and peer review required before the first measurement. The protocol's phrase 'unchanged launcher' refers to the inherited launch and receipt structure: its already documented label/count/map changes remain part of the proposal.
