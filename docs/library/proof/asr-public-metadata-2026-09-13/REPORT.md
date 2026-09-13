The six selected model plans now have dated, immutable repository revisions and advertised logical byte totals. These records support the approximate size labels in the settings repair brief at commit 44e69fc. They do not establish that any model asset is safe to load or that the runtime is accepted.

| Choice | Repository | Immutable revision | Advertised selected bytes | Approximate decimal MB in repair brief |
| --- | --- | --- | ---: | ---: |
| tiny | Systran/faster-whisper-tiny | d90ca5fe260221311c53c58e660288d3deb8d356 | 78,203,619 | 80 |
| base | Systran/faster-whisper-base | ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66 | 147,882,941 | 150 |
| small | Systran/faster-whisper-small | 536b0662742c02347bc0e980a01041f333bce120 | 486,212,372 | 490 |
| medium | Systran/faster-whisper-medium | 08e178d48790749d25932bbc082711ddcfdfbc4f | 1,530,571,735 | 1,540 |
| large | Systran/faster-whisper-large-v3 | edaa852ec7e145841d8ffdb056a99866b5f0a478 | 3,090,835,702 | 3,100 |
| large-v3-turbo | dropbox-dash/faster-whisper-large-v3-turbo | 0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf | 1,621,665,983 | 1,630 |

The original independent review retains its closer rounded decimal labels unchanged. The table above follows the conservative approximate labels subsequently chosen in the repair brief. These are selected-file logical sizes, not measured network traffic, peak memory, installed footprint or a promise that every user downloads the full amount. Cached files, transfer overhead and changed revisions affect actual transfer.

The initial collection made 11 requests and retained 10 successful responses and five plans, then refused a redirect. Its status remains FAILED and its collector and actual outer exits remain 1. The later diagnostic observed HTTP 307 to the canonical turbo repository, retained an empty body and did not follow the redirect; diagnostic and outer exits were 0. The original collector did not retain the redirect headers, so the diagnostic's 307 is not retroactively attributed to that first request. The separately authorized canonical capture made two successful requests, retained one plan and exited 0. All original briefs, collectors, responses and exit receipts are included unchanged.

SIX-MODEL-PLAN.json retains all 26 selected records. Six model.bin files have publisher-advertised LFS SHA-256 values. Their Git blob OIDs identify LFS pointer blobs. The other 20 files have ordinary Git blob OIDs and no SHA-256; those absent values remain null. No asset body was downloaded or hashed. The six plans retain asset_downloaded=false, manifest_accepted=false and all_selected_have_advertised_sha256=false. The MIT classifications are repository card metadata, not independently established licensing conclusions.

The seal verifies all 12 successful raw JSON response sizes and hashes, four retained source copies, selected-file identities and sums, the diagnostic body and all outer exits. The prior independent review also checked duplicate JSON keys and found none. Collector and source review is retained in INDEPENDENT-VERDICT.md. The capture preserves the existing six-choice mapping; observing the canonical turbo metadata does not itself alter product fetching. No new network request, test, package import, asset read, model run or installation occurred during this documentary seal.
