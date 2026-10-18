# Unicode search repair observations

The first new regression run, unicode-before-01, reports 12 failed / 6 passed.
Six failures demonstrate the original ASCII-only query behavior. Six retrieval
cases stop on the new helper's missing required yoinked_at field; they are not
observations of retrieval behavior. Before rerunning, the new seed helper adds
an explicit fixture timestamp. No assertion or existing test changes. The first
log stays retained. This review will record the repaired product and both-root
verification when those observations finish.

unicode-before-02 also reports 12 failed / 6 passed. The timestamp alone was an
incomplete seed repair: corpus_path and sidecar_path are required too. The seed
now supplies both paths inside its disposable directory, without creating or
reading those files. Assertions remain unchanged. Both setup failures are
retained; no retrieval pass is inferred from them.

The product now normalizes query text to NFC and retains Unicode letters,
numbers, underscores and attached combining marks. Punctuation remains a
separator, and every term stays quoted with only the final prefix operator.
No schema, indexed content or existing test changes. SQLite still applies its
existing tokenization rules; this adds no language-specific segmentation.
Reference: https://www.sqlite.org/fts5.html#unicode61_tokenizer (read 2026-09-11).

unicode-repaired-01: 136 passed / one failed in 3.55 seconds. All 18 new cases
pass. The sole failure is the original SEC-06 XPASS(strict): its unchanged
assertions now succeed. Preserve that ordinary result. The brief's next run
uses --runxfail to execute those same assertions as an ordinary test, rather
than deleting or changing its marker.

The same focused union with --runxfail passes 137 tests in the worktree
(unicode-repaired-02, 3.06 seconds) and 137 in the checkout after raw-diff /
three-way integration (unicode-checkout-01, 3.28 seconds). Both report four
existing datetime deprecation warnings. Japanese, accented Latin, Cyrillic,
Arabic, Devanagari, canonical-equivalent text, prefix matches, clip retrieval,
literal boolean keywords and separator-only input are covered.

Approve this bounded product repair. It preserves the existing quoted grammar,
all original test bytes, schema and source data. The full candidate tree and
installed observation are still owed. The earlier failure records remain in
proof/unicode-search-2026-09-11 alongside both-root results and the raw patch.
