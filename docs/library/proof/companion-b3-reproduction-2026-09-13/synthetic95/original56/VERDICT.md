# B3 synthetic qualification verdict — 2026-09-13

The proposed combined `1.2.1+uoink.localassets2` builder passes its bounded
synthetic qualification: **68 passed, zero failures/errors/skips**, actual
child and outer exits 0. All 62 inherited case IDs remain and six new cases
cover the combined source binding. The receipt reports no preloaded or final
heavy modules, no guard violations, the import guard present at finish and
qualified inputs unchanged. This was the first B3 synthetic run, `b3w01`.

The exact qualified builder is
`f25530a3ee58169c049e63c2e6bfff444061f2c04c9a87ec2af43c8850b81892`;
the protocol is
`9f46c9e6e483d4508960f137142c5e1d8fc9c19409badca7ba624d846aa56cd6`.
Before execution, the independent reviewer read the source, NOTICE, complete
recipe, inherited expectation changes, six added cases and guards. Root also
reviewed the complete builder and expectation deltas without finding a blocker.
The independent reviewer verified all 15 text member identities in the proposed
16-member manifest. Its one asset identity remains inherited evidence.

The builder retains exact upstream wheel identity, bounded stable reads, path
and archive validation, deterministic ZIP format and complete RECORD checks.
The five fixed recipe inputs combine the unchanged B2 tokenizer constructor
repair with the exact reviewed utils keyword removal. Original and replacement
utils bytes are bound. Dependency lines, MIT license and the remaining members
are preserved; local version, metadata version, NOTICE and RECORD identify B3.

Only two inherited expectations changed: the approved changed-member setup
adds utils.py, and version.py expects localassets2. Their exact diff is retained.
All other inherited assertions are unchanged. Added cases reject altered or
missing utils recipes and source, bind both repaired outputs, constrain changed
Python members, and preserve dependency metadata/license/placeholder asset.

This run used retained text fixtures and an in-memory asset placeholder. The
existing negative case still rejects that placeholder against the fixed real
asset manifest. No actual upstream/output wheel, model asset, package/native
runtime, network request, installation or build was accessed or executed.
Successful synthetic ZIP tests do not establish full-module or native runtime
compatibility, a B3 artifact identity, distribution acceptance or release readiness.
The proposed B3 output wheel hash remains null. All earlier B2 and Hub seals
remain unchanged; no production, staging, dependency pin or frozen test was edited.

Root's independent synthetic run is next. Any later real build should reuse and
revalidate the already verified private 34-file Python 3.13 runtime, under a
separate reviewed byte-only invocation, without copying or launching an original
embedded interpreter. No real-build invocation is provided or authorized here.
