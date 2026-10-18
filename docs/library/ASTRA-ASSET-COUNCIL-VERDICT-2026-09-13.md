# Astra disposition of the cache and tokenizer council review

Gemini's source review supports the bounded cache repair in `b96dbd0`. It does
not approve Uoink for release. The raw report is preserved unchanged alongside
its brief, dispatch, reviewed source and integration patch.

The empty-buffer finding is valid. B1 treated `b''` as absent and could select
an ambient tokenizer file, raise the wrong missing-file error, or reach the
explicit nonlocal fallback after allocation. B2 changes the condition to
`tokenizer_bytes is not None`. The four added cases cross local-only true/false
with ambient file present/absent. B1 passed six cases and failed four; B2 passed
all ten in the author run and in Astra's exact-input independent run, with zero
errors or skips and actual process exit 0. Original six assertions are unchanged.
These checks execute only the selected constructor prefix with inert seams.
B2 remains an unapplied derivative, SHA-256
`bf452635becacf6bba46825be6d6eea533da472ce966ee47f5ce7bccfc3bf06d`.

The Windows casing finding has a false premise. Windows Path equality ignores
drive and component case. Astra's native Windows standard-library probe found
different absolute/resolved string spellings but equal Path objects. This
probe did not test 8.3 aliases or production downloads. Canonical-path checks
intentionally reject redirected aliases. Resolving first and then checking
`is_symlink()` would discard the original alias evidence, so that proposed
change is rejected.

The tokenizer deletion race is an existing open limit while B remains unapplied.
The report's broad no-network statement applies only to the cache helpers: it
does not establish offline enforcement across the dependency stack or default
VAD path. Local-only constructor handling, artifact trust and model loading
still require their own qualification. The raw report's broader wording is
not adopted as a release claim.

No tests were required or run by this source-only council brief. The production
repair had already passed 144 cases plus 13 subtests in worker and checkout.
The later complete tree at `56d9d4c` recorded 2,796 passed, one historical AT6
receipt failure and three skipped cases, plus 13 passing subtests. This
document integration changes no production source or acceptance tests, so it
does not trigger a repeat of that tree. Website and marketing remain paused.
