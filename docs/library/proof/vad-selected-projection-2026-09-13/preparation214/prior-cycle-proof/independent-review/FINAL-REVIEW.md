# Independent cycle-diagnostic review — 2026-09-13

No blocking source or synthetic-qualification issue was found in this reporting-only change. The earlier actual static inspection remains a reference-cycle refusal, reader/outer exit 2; the diagnostic does not change that outcome into acceptance. Root's decision about one further labeled static inspection remains separate. This review establishes no architecture, configuration, artifact provenance, conversion viability, model safety or release readiness.

Reviewed source: `_scratch/vad-symbolic-cycle-diagnostic-proposal01/read_symbolic_inventory.py`, SHA256 `15b9d339be34358dfecc2142a960cc524fe6e4620e0ec1716114027cac216ddd`. Its preserved adapter baseline is `0b5e786b1721dd63c84d9cd12eabf23af2c856790d6bdcabd6b270288e0049fc`. The prewritten brief is `8434df597f98f07b46c99ada436d06c7316297455faa80f0495c05c31fa73058`.

The complete source diff retains the first detected gray-edge rejection and its exact reason, `Reference cycle refused`. Graph validation still covers every node and keeps all prior grammar, memo, duplicate, depth and resource refusals. The new branch constructs only a small diagnostic and immediately raises `TraceRefusal`; it does not call graph output, tensor descriptors, an evaluator or a loader. Diagnostic-generation exceptions produce a fixed unavailable marker and preserve refusal.

The witness includes at most 12 cycle-prefix node references/kinds and 11 edges, plus the actual closing edge separately. It uses DFS edge occurrence indices rather than searching for the first equal child. Full cycle length and truncation are explicit, so the closing edge cannot be mistaken for the end of a truncated prefix. Edge roles come from fixed structural labels; arbitrary keys, values, GLOBAL names and omitted training data are not copied. The optional GLOBAL classifier was excluded before implementation.

Root-entry categories describe only the active DFS path when it directly starts at the literal root. The selected labels are fixed; unknown root names are omitted. Unavailable context remains unavailable. The explicit alias caveat prevents a training-path category from claiming that a cycle belongs exclusively to training data. Fixed parent/content field roles describe literal structure and do not establish OmegaConf or object semantics.

The independent witness cap is 4,096 compact JSON bytes. Oversize output yields a small truncation marker. Fixed input and expected artifact digest, ZIP/member/size/CRC gates and the final 256 KiB receipt cap remain unchanged. The earlier assumptions also remain: quiescent staging, cooperative deadlines, and opaque whole-file hashing/ZIP-tail reads that can overlap storage bytes without selecting, decompressing or interpreting storage members.

`cycle-diagnostic-preflight01` recorded **36 distinct passed cases, 0 failed**, actual qualification exit **0**, in **0.066185 seconds**, with empty stderr. The reviewed launcher propagates that exit, scrubs provider variables and sets the exact forbidden-live path string before `-I -S -B` startup. The child asserts the binding. Source and harness hashes are unchanged before/after the run. No actual checkpoint or real main input/output paths were used.

The harness retains 23 prior behavior/source-boundary cases unchanged. It preserves the old composition predicate as unregistered historical code and replaces that scope-specific predicate with one reporting-delta check, then adds 12 witness cases. It does not relabel the old 24-case suite as passing against changed instrumentation. AST normalization proves equality outside the explicitly removed diagnostic blocks; this reviewer read those new blocks directly, and focused cases test their behavior. The duplicate-occurrence case is correctly described as a direct helper check, not an invented claim about which duplicate a DFS would reach first.

The focused cases cover self/two-node cycles, fixed parent roles, edge occurrence indices, a truncated 20-node cycle, tightened byte cap, unavailable root context, nonexclusive aliases, omission of private root names/values, diagnostic failure, refusal before output/descriptors and inert main refusal context/return 2. Inert main returns are function results, not actual checkpoint reader invocations. The original actual refusal and completed 108-payload proposal seal remain separate historical evidence; this reviewer did not modify them.

Evidence hashes independently read from disk:

- `qualify_cycle.py`: `f76fa88e58bba46130c2b8d44c7d17543ff46334c73976adb138efa0fa169f6a`.
- `cycle-diagnostic-preflight01/stdout.json`: `b1fdfbc71f3edc72edea106fc7c8579df8d81fa3da09f8e46df3236ca07342bb`.
- `cycle-diagnostic-preflight01/launch-receipt.json`: `38f7661fb4f1edb6b12ad0698feace28c7fc44058d0a159bd5d8ae4fccdfeeca`.

The reviewer read source, diffs, plans and raw receipts only, and executed neither the adapter nor the synthetic suite. No checkpoint was read, no model/tensor was constructed, and no competing parser was created. A future fixed loader still needs independently supported settings and a trusted plain tensor artifact or a separately reviewed nonexecuting conversion. A cycle witness alone supplies neither.
