# Reference candidate OSV metadata review — 2026-09-13

The uninstalled 144-pin reference candidate returned **1 raw advisory entry in 1 alias group**. A separate query for upstream NLTK 3.10.3 returned **1 entry in 1 group**. These are new candidate observations; the original audit remains **19 raw entries / 15 alias groups**. No runtime compatibility or release approval follows from this metadata review.

| Query scope | Pins | Raw entries | Alias groups | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Frozen reference candidate | 144 | 1 | 1 | Lightning 2.6.6 matches the advisory below; retain the raw match despite inconsistent range metadata. |
| Upstream NLTK 3.10.3 comparison, separate from the candidate | 1 | 1 | 1 | The upstream advisory remains applicable in OSV. |
| Local NLTK 3.10.3+uoink.pathsec1, already included in the 144 | 1 | 0 | 0 | This local version has no PyPI release record. A zero-match response does not establish patch safety or a recognized package identity. |

Collection ran from **11:36:07.685799 to 11:36:09.047386 UTC** on September 13. Both query batches and both full-advisory requests returned HTTP 200: **4 requests, 0 retries, 0 redirects, 0 returned pagination tokens, 0 collection failures**. All 144 candidate queries completed. The collector follows per-query continuation tokens when present, as documented by the [OSV batch API](https://google.github.io/osv.dev/post-v1-querybatch/); none occurred in this collection. Full records were retrieved through the [OSV advisory endpoint](https://google.github.io/osv.dev/get-v1-vulns/).

**Lightning metadata disagreement remains unresolved.** Querying `lightning==2.6.6` returned `GHSA-qqmf-gpg7-g8gw`, with aliases `CVE-2026-58659`, `PYSEC-2026-3624`, and `PYSEC-2026-3967`. The saved full record describes checkpoint `_instantiator` arbitrary code execution through 2.6.5 and names a repair commit. Its enumerated affected versions end at 2.6.5, while its ecosystem range carries the inconsistent fixed event `2022.6.15`. The query nevertheless matched 2.6.6. This review retains the match as **1/1**; it does not subtract it or claim a new code repair. The earlier code review in `docs/library/ASTRA-SECURITY-REPAIR-REVIEW-2026-09-12.md` is separate evidence.

**The NLTK comparison prevents a misleading local-version conclusion.** Upstream `nltk==3.10.3` returned `GHSA-8mgp-746c-j5xp`, with aliases `CVE-2026-81726` and `PYSEC-2026-3740`. The saved advisory describes model-artifact APIs bypassing allowed-root checks; its range ends with `last_affected: 3.10.3` and has no fixed event. The local patched version returned no match. That difference cannot establish whether the patch addresses the vulnerability: the patched package is not represented by an upstream PyPI release. The candidate and comparison counts remain separate.

The collector, exact selection, prewritten brief, HTTP request bytes handed to TLS, response bodies, timestamps, headers, query mappings, derived records, and hashes are sealed in `_scratch/runtime-candidate02-osv01`. The request-byte receipt is not a packet capture or delivery acknowledgement. The seal contains **31 payload files plus `SHA256.json`**. Its manifest SHA-256 is:

`f6378453d1bc9ea432793b33ea6e2aa108b5ce868a740f9df9e79c3d79e29bf5`

The selection SHA-256 is `8628331233238ca4fc8af3b424e64b91906b5ece338ad6ce84226622c7187e50`.

A separate read-only checker, `_scratch/review_runtime_candidate02_osv01.py`, exited **0** on its first run. It verified all 31 payload hashes and exact seal membership, unchanged selection/collector bytes, all request and response hashes, exact 144-pin membership, the separate upstream query, raw-to-derived mapping, alias groups, and count/claim consistency. Its result and log are `_scratch/runtime-candidate02-osv01-review.json` and `_scratch/runtime-candidate02-osv01-review.log`. The reader's PASS applies only to saved metadata consistency. There were no failed collector or reader attempts and no instrument corrections in this run.

No candidate was installed or executed. No models, wheels, binaries, media, or product tests were fetched or run. This review does not establish dependency compatibility, safe checkpoint/model loading, exploit reachability, or market readiness. Parent review of these payloads is still required before documentary integration; no source, accepted tests, handoff, commits, or website files were changed here.
