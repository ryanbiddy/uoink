# Preliminary adapter review — in-flight Gemini run19ac6c2d

No standalone adapter-append blocker established in this snapshot. This is not final acceptance of the mutable delivery, its factory integration or its proposed tests.

The one captured adapter is 42,939 bytes, SHA256 `94e522e622b8de3304ef48c97258a91692e70f22c3112dd6afabd6b493438611`. Its source hash was unchanged immediately after the read. The complete 34,968-byte before file is SHA256 `2f12cbf5a5f1142f892aa34df7d23af77107148b448fb4294329532e36be63ee`; the captured derivative preserves that byte prefix exactly (87c50b/0). No candidate file was modified.

I read the full canonical implementation brief, its complete fixed plan/map, the full append at lines644–780, the accepted stage predicate548–641, startup custody contracts251–547 and baseline durable factory/kernel462–559. Check26462e/0 verifies all eight donor bindings and the plan/map hashes. Its optional aggregate `plan_bytes` field is null; the individual byte/hash checks are complete, and no aggregate measurement is claimed from that field.

The locked pre-resume predicate644–709 is exactly the accepted stage predicate after the required signature, resume-state/message and final unpublished-state changes. It checks current issued/consumed selection references and values, exact full permit/record/lease/protection, live WORKER_BOUND token without pending/revoked/failed persistence or prior resume, exact token/kernel worker, idle live session and NATIVE_RESERVED with no published worker. The wrapper712–727 retains manager-then-token locking. There are no new imports in the append.

Classification730–780 consults both the exact object registry and retained attempt custody for the permit or its record. It refuses exact unissued, ambiguous, inactive, mismatched, foreign/subclassed and substituted-profile controller attempts. Its False return means only that no controller attempt was identified; preservation of generated sentinel/binding refusal belongs to the changed durable path and is not established by this adapter alone.

One integration question was sent to root: classification returns only a boolean at775, while the later predicate retrieves custody afresh at721. The frozen factory must retain or revalidate the original exact custody so substitution after classification cannot satisfy a new lookup. This note does not assert that defect without reviewing the factory's retained attempt context. Root owns that concurrent slice.

The real entry466–468 and every accepted prefix assertion remain unchanged. No Python startup, import, compile, test, native/model/artifact/support/journal access, network or Git operation occurred. Final frozen source requires a bounded follow-up comparison.

