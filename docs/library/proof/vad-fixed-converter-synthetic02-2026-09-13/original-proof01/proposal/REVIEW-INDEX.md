# Converter review index

2026-09-13. All paths below are relative to `E:\AI\projects\uoink\checkouts\Yoink-library`. The converter source is frozen. This is synthetic qualification only; `REAL_PROFILE = None` refuses the real route before path access. No actual artifact conversion is authorized by this package.

Read `_scratch/vad-fixed-converter-proposal01/BRIEF.md` first, then `fixed_converter.py`, `zip_bounds.py`, `fixed-plan.json`, `qualify_converter.py` and `run_preflight03.ps1` in that directory. The harness is the Python runner; the PowerShell file creates a fresh copied-input directory, binds the forbidden-live environment before startup, scrubs provider variables, invokes the guarded stdlib runtime under `-I -S -B`, records actual exit and verifies unchanged hashes. Do not rerun its already-used label. Root may copy the exact five inputs to a fresh independent label.

| Frozen file | SHA-256 |
| --- | --- |
| fixed_converter.py | `b31915b2e6d78a29ec05699952e5e0bfa01d234fec31ed37481c21665cfba54b` |
| zip_bounds.py | `bfe582cb2caa69a344a8147870c4ca161aa14d5202683c2e26e3f9ab040690c6` |
| fixed-plan.json | `37af25ab777ca7c322e00bec20dfffc1b6959d32c5bbd1a8c678bfc4126c91bf` |
| qualify_converter.py | `11f9addddf9b349c4ee249c000cc60c4986b989de2e11ec990ba940d6b7949a9` |
| run_preflight03.ps1 | `78a81a4264e477f2c850d404a31c37e56b3ed416dad17d4fe98347722ef64783` |
| converter-preflight03/reviewed_zip_reader.txt | `67e9edd6c3f6845a8dd3fd21b0b471793b57db0222c56379c0dfce9fcf07c9e5` |

The successful raw records are `converter-preflight03/{plan.json,exit.json,stdout.json,stderr.log}`. `stdout.json` is SHA-256 `0a8883c196ebd7b4ed650d74a69e71f59d6e5c60a13c350f66dbb8dc065b198f`; `exit.json` is `25bc4a0c14c0de9b0d9ed9fbc701c5419c2f145e2f6c4ec409e831ea3b372e85`. They record **82 distinct passed cases, 0 failed, 2.147786 seconds, native/qualification exits 0**, empty stderr, startup binding true and unchanged inputs. Each of the 54 output entries is compared with its independent fixed range; the 32 shared-storage views remain covered.

Both earlier raw directories are retained. `converter-preflight01` and `converter-preflight02` each exited 1 before any case ran. Read `IMPORT-SETUP-REPAIR02.md` (SHA `a9a62d2ba520ed377e26956aee2f8903e97c79320c8ed6708130d804b6389ba9`) and `CODEC-SETUP-REPAIR03.md` (SHA `65909ce0674183056a438c19f0cc02eea627eb4bf8d9eb64b484cb01ed6caaed`). Their preserved harness drafts and copied inputs show that the corrections concern module/codec startup; all 82 behavior assertions remain unchanged. `PREQUALIFICATION-WRAPPER-DEADLINE.md` and `PREQUALIFICATION-ANCESTOR-REPAIR.md` document the two source corrections made before any test attempt. The original source drafts remain under `drafts/`.

`SYNTHETIC-REPORT.md` (SHA `e58f896ee0481ce06a4b0041f770c198ec9c3583a498431ae4fbfb43b66d4f71`) explains coverage and limitations. The source-only independent verdict is `_scratch/vad-converter-independent-review01/PRE-SYNTHETIC-REVIEW.md`, SHA `83ce486d5cdf02814dad0c17e05e69d6f637eb7e5f5600598203b2f2d9c06f83`; it is not a verdict on the later harness or run.

## Binding chain

`prepare_plan01.ps1` derives the plan only from the already-reviewed safe JSON mapping: `_scratch/vad-selected-metadata-map01/mapping.json`, SHA `b6ef4d932556a24e46661e5600e50b386f3243a3aeeb19fa0dad592e439fd5ca`. No checkpoint is reopened. Its 54 entries cover 23 distinct storages, 1,472,999 declared elements and 5,891,996 advertised bytes. The immutable mapping proof has 48 payloads at `_scratch/vad-selected-metadata-map-final-proof01`, seal `c67d091287456999f95ff9f93dd81d39ca96c2f98d35d678092b5c9fe72dd80d`. The factory, bridge choices and original mapping remain unchanged.

`prepare_boundary01.ps1` copies exactly two bounded ZIP functions from `_scratch/vad-static-metadata-tail01/read_checkpoint_inventory.py` (the frozen 67e9 digest above); the rest of the converter's stored ZIP grammar is new and needs review. `FORMAT-REFERENCE.md` records the primary Safetensors format reference, with no package execution.

The original inventory proof80 remains `_scratch/vad-static-inventory-final-proof01`, seal `60e3f77ba1244e2044b29f1c67facb917b24cc769f6fb4cb08c18c2f4415ee46`; tail proof29 remains `_scratch/vad-static-metadata-tail-final-proof01`, seal `f1a9c61f617fd700019c8c1567453d770614df88415c818000ac969f55bc53aa`. The selected-projection proof214 remains `_scratch/vad-selected-root-projection-final-proof01`, seal `7a3484f2b52d607c65748cb03eb13363418ff2c157e76648c1e7c1cef68d66ed`; root preserved the actual strict-refusal/partial-projection receipt in proof228, commit `ba8d2c8`, seal `700044423a8a8c0728524b8c3621c7378e41daf302d2137df4f0492d2d1ee8cf`.

The separate primary textual provenance package is `_scratch/vad-provenance-text01`, 88 payloads, seal `57b91f83d50db7d1e93a18de793c05802d05ff924e411b86c02b098858004189`. It associates the historical Hub commit with the recorded artifact SHA/size, but leaves actual endian and archive/version bytes unobserved. It does not create an accepted converter profile. The synthetic profile is explicitly little-endian IEEE binary32, contains generated-byte hashes and cannot authorize the original artifact digest.
