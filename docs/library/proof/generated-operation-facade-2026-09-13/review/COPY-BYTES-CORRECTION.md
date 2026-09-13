2026-09-13. The first plan preparation returned 0 in tool `71ea2d` and completed its two retained-receipt checks. It verified all required fields and the original preparation payload hashes, then wrote a 96-entry copy plan. Its `payload_bytes` and printed `copy_bytes` were null: `Measure-Object -Property bytes` did not bind the keys of the in-memory ordered dictionaries.

Preserve that source, `COPY-PLAN.json`, `RECEIPT-REVIEW.json` and the actual tool result. The missing byte total makes the first plan's accounting incomplete. No proof copy, candidate execution or native rerun followed it.

`correct_copy_bytes.ps1` reads only the saved JSON plan, requires all 96 explicit integer byte lengths, sums them directly, and writes fresh `COPY-PLAN02.json`. It requires the exact same source/destination/hash/size rows. This correction does not rerun the receipt checks or change either native result.
