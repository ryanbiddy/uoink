# Preserve requested extras in the proposed graph

Astra found that candidate02's collector records fsspec[http] and pyjwt[crypto]
in selection-diff.json but writes plain package names in selection.json. The
checker reads extras from composite selection keys. Graph01 therefore does
not establish the claimed original-extra coverage. Keep its FAIL result,
original review and entire 342-payload seal unchanged.

Create a fresh runtime-candidate02-astra-graph02 directory. Change only those
two selection keys, preserving all 144 versions and exact captured metadata.
Bind the correction to the original production lock snapshot and save the
before/after diff. Run the committed offline checker once with original guards,
no network or subprocesses inside the checker, and a fresh output path.
Record actual exit and every unresolved item. This is a metadata-only
instrument correction, with no product dependency, test or model change.

Verify all 342 original payloads before and after, plus each of nine new
retrieval hashes and its metadata binding. No fetch, install, model execution,
live-index/5179 access, website, marketing, commit or push occurs in this check.
