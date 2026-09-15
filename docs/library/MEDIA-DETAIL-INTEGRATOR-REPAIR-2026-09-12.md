# Close the media-detail review findings

Gemini 2dae80cc has 47 independently repeated passes (astra-media12-worker01).
Before integration, repair these concrete gaps in its new endpoint and the
newly reachable saved-metadata display. Add new regressions; existing tests and
the worker's twelve tests stay unchanged. Preserve the original patch and report.

1. Check lexical containment under the configured output root before lstat,
   is_symlink, resolve or any other metadata operation on a registered path.
   The original worker stats an out-of-root file before rejecting it. Never
   use the actual forbidden index as a probe: use a disposable outside sentinel.
2. Read at most MAX_SIDECAR_BYTES+1 bytes in binary mode, then decode. The worker
   checks file size then reads that many characters; a growing multibyte file
   can exceed the declared byte limit. A synthetic in-root growth probe suffices.
3. Return a structured error for overly nested or non-finite JSON. Do not emit
   NaN/Infinity in a successful response or let a recursion exception sever it.
4. Filter nested speaker/diarization dictionaries too. The worker currently
   returns arbitrary values under speakers maps and speaker objects. Keep only
   the actual label fields required by the renderer, with no generated labels.
5. Track detail-request identity, not only item ID. An A-to-B-to-A selection can
   accept a delayed response from the first A over the newest A. Protect both
   metadata and markdown and the final render with one request generation.
6. Newly loaded transcript strings have no stored timestamps. The existing
   renderer invents 30-second offsets for them and creates missing timeline
   endpoints. Display unknown timing explicitly and require actual start/end
   values for timeline spans. Do not infer a speaker from an empty label object.

First run the new tests against the worker patch and retain failures. Apply only
these source corrections in the worker tree, then run all six original named
suites plus the new cases with --runxfail. Once the frozen a25e3be full-tree run
finishes, reproduce the new media behavior on that original checkout, integrate
by raw binary diff and three-way apply, and repeat the focused union. No test
assertion, fixture or mark is changed to produce a pass. Retain every worker
attempt, including those its final prose omitted. This is not permission to load
models, perform diarization, fetch sources, use paid APIs, read the live index,
contact 5179 or approve a release.

Then freeze the final source and run a new complete tree before package-08.
Do not build the intermediate a25e3be source: its full tree is retained as its
own observation. Adapt the prepared package-08 instruments' source bindings
before any build/install observation, preserving the initial drafts and diffs.
