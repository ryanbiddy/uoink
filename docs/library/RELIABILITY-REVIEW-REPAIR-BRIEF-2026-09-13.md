# Reliability review repairs before integration

2026-09-13. Grok run 0851b440 has produced a scoped repair; final worker
completion and verification are still pending. Astra's source review and the
independent reviewer found two remaining defects. Preserve the completed
worker diff and all new tests before making these repairs. No existing test
or assertion may be changed.

1. `_reliability_cache_root` resolves its argument before comparing it with
   the resolved path. That loses the evidence that the supplied root was an
   alias. The worker's redirected-root fixture points at an empty destination
   and therefore misses this case. Add a separate regression whose redirected
   physical destination contains a complete ready cache. It must remain
   unready. Keep the lexical absolute path until the comparison; retain
   ordinary Windows case equality and supported internal Hub blob links.
2. `reliabilityStatusText` supplies the saved model's size even when an
   unsaved selection has no metadata. It can describe that new selection
   using the old model's size. Add a separate regression with a saved tiny
   estimate and an unknown unsaved choice. The result must say size unknown.
   Use a server estimate only for the same selected model. Preserve the
   worker test that allows a correctly associated server estimate.

The `_load_model` keyword repair meets the current ordinary-local-only
requirement. An earlier reviewer suggestion to bind its constructor directly
to the checked snapshot is separate hardening; no additional acquisition
bypass was demonstrated in that finding. The broader tokenizer/VAD migration
gates remain open and are not closed by this repair.

Before changing worker source, execute the two added regressions against its
completed patch under the reviewed focused instrumentation and preserve the
actual failures. Also record the original default-keyword behavior with a
fake constructor under a bounded source-only probe. No real model or asset
may be touched. Then apply the two source fixes, choose a fresh run label and
run the complete original five-suite union plus every new regression in both
worktree and checkout. Preserve exact membership, raw exits, guard results,
commit and file hashes. Integrate only after root review and both runs.

No worker rerun, Python launch or Node child follows from this brief alone;
the exact instrumentation must be reviewed and bound first. No model fetch,
dependency change, install, release, website or marketing action is included.
