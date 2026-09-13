# Candidate03 retained-metadata graph — 2026-09-13

The complete 144-pin graph is **FAIL** because the retained release metadata has no wheel for `antlr4-python3-runtime==4.9.3` or `proxy-tools==0.1.0`. Its 287 active dependency edges have no missing targets or version conflicts. There is no incomplete metadata evidence and no manifest, marker, direct-URL or selection error. These two packaging gaps remain open; the graph does not authorize a version change or archive acquisition.

The single complete run took 3.4721001999860164 seconds. Native and outer exits were both 1, with valid invocation/accounting, no guard denials and empty stderr. All 313 original captures matched their original manifest before and after the graph. All 36 preparation inputs and their recorded filesystem identities stayed unchanged. Raw graph SHA256 is `eb56674b511a90b13685d1bb53b24d27c735fdd3fee068c9abd6d61c6d0b149e`; actual outer tool `e7bf3f` recorded exit 1 in 4.0301332 seconds.

| Retained measurement | Observed counts | Meaning |
|---|---|---|
| First two-record qualification | 51 passed, 11 failed; 25 guard denials | Failed qualification. The guard incorrectly denied generated metadata probes; no valid subset is claimed. |
| Repaired two-record qualification | 62 passed; 0 failed/errors/skips/subtests | Valid inert qualification after the documented, narrow metadata-probe repair. |
| Final three-record qualification, author | 59 passed; 0 failed/errors/skips/subtests | Valid inert qualification: original 36 public cases plus 23 controls for the final local-record interface. |
| Final three-record qualification, root | Same 59 ordered case results; all other counts 0 | Independent valid repeat; the separate admission-file collision is preserved below. |
| Complete candidate03 graph | 144 pins, 287 edges, 2 wheel failures | Valid metadata measurement with native/outer exit 1. |

The earlier candidate02 graph remains FAIL with five WhisperX cap conflicts, two wheel gaps and missing local NLTK public evidence. The new graph uses exact prior built-wheel METADATA for faster-whisper `1.2.1+uoink.localassets2`, WhisperX `3.8.6+uoink.owned1`, and NLTK `3.10.3+uoink.pathsec1`. It does not reopen those wheels: each local entry retains `artifact_verified_in_this_invocation=false`, no public release claim and no invented download URL. NLTK's separate metadata reader is preserved by integrated commit `e5b1ddd` and its 23-payload seal `ee428799befd7b04c68f5de81a7eab287d1102bc86fb6e5993d22d8661e6df08`.

All preparation failures, corrections and raw results remain in the source map. Root's attempt to create its dedicated final59 admission file collided with an existing author-admission filename. The root then explicitly invoked the reviewed independent run; no successful new dedicated pre-execution file existed. The late independent review records this truth. This proof retains that review and the unchanged author-only admission; it does not invent a raw tool object for the collision.

This evidence qualifies source/metadata contracts only. CPU artifact provenance, installation, native imports, waveform decoding and filter-bank ownership, model assets, factory/session lifetime and real non-speaker runtime behavior remain outside its acceptance. Fixed platform accessors simulate a metadata target; they do not qualify installed Windows CPython 3.13 packages. The two absent wheels require a separate bounded acquisition/build decision before the metadata graph can pass.
