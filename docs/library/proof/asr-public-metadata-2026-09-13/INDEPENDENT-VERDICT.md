# Independent ASR metadata review

2026-09-13. The retained metadata supports approximate download-size labels for the six existing choices. It does not establish asset integrity, loading safety, a complete artifact manifest or release readiness.

The initial capture remains **failed**: 11 requests, 10 successful raw JSON responses, five plans, recorded outer exit 1. Its redirect failure lacks the original response headers. The separate diagnostic records HTTP 307 to the explicitly named dropbox-dash repository, without following it, and outer exit 0. The approved canonical observation then records two successful requests, one turbo plan and outer exit 0. The later observations do not retroactively turn the first run into a success.

Independent read-only checks verified all 12 retained successful response byte counts and SHA-256 values, their repository/revision fields, complete current-versus-pinned sibling metadata, all 26 selected file records and sums, both runs' four source copies against their declared hashes and current source text, and the redirect body/status/outer receipt. All 12 raw JSON documents were separately checked for duplicate object keys; none were found. No mismatch was found. The collector permits only public model-info endpoints, disables redirects and environment proxies, and imports no provider SDK or model module. The canonical derivative preserves the original six-choice source check and changes only its output, explicit canonical repository permission and acquisition loop.

| Choice | Advertised selected bytes | Suggested approximate decimal label |
| --- | ---: | --- |
| tiny | 78,203,619 | About 78 MB |
| base | 147,882,941 | About 148 MB |
| small | 486,212,372 | About 486 MB |
| medium | 1,530,571,735 | About 1.53 GB |
| large | 3,090,835,702 | About 3.09 GB |
| large-v3-turbo | 1,621,665,983 | About 1.62 GB |

These totals cover the selected model/config/tokenizer/vocabulary files, including preprocessor_config.json where advertised. They are dated repository-size estimates, not measured network traffic, available-cache size, peak RAM or total installation space. Use approximate wording and consistent decimal MB/GB units. Cached files, transfer overhead, different revisions and any other acquisition scope can change actual transfer. The turbo canonical identity is explicitly observed metadata; this review does not silently change the production mapping.

Identity types remain distinct. Six `model.bin` records contain a publisher-advertised LFS SHA-256; their `git_blob_oid` identifies the Git LFS pointer, not the model payload. Twenty ordinary Git file records supply a Git blob OID and no SHA-256. The absent SHA-256 values must remain absent. None of the 26 asset bodies was read, so none has a locally verified payload hash. All six plans correctly retain asset_downloaded=false and manifest_accepted=false. The MIT fields are provider card metadata, not an independent licensing conclusion.

Reviewed result hashes under `_scratch/asr-asset-metadata01`:

| File | SHA-256 |
| --- | --- |
| run01/result.json | `0e15b6a854e56266afd6feb94a310a5527a5b0d0f29ca4647d5a70dd676ef021` |
| redirect01/result.json | `02cdd6f273334c69bfad0f7f984023bbe1b2e86f5a28f12a9a89fc48700fe009` |
| canonical-turbo01/result.json | `1772c5746370aaf54fb085956defc83d138e3094fe8a8e3d7b8f81042d2e93b1` |
| collect.py | `d2685a15265acdf1cb1927fdd4185f99dd8081772c19e8d1a903fb5c8103e73a` |
| collect-canonical-turbo.py | `24cb2cf3d52e0dacd4a70a2c238310cc1de31807b7e4d049f77550db66d82d01` |
| inspect-redirect.py | `2d9dc2c7e8066b1962cfb31a47d5e69230d2e1c866df47fb941f0ea5cde409a4` |

Source identities agree across both captures: whisper_runner.py `6586d9f19fea0d20054d6e317b48b9914904e1126bbc7b788ba255633251996f`; retained hf_api.py `444326f4016052dca2cc8ead904cba8255f601aefe4c7efeb96865865d2ad1f1`. No new network call, collector execution, model import, product test, installation or production edit occurred in this independent review.
