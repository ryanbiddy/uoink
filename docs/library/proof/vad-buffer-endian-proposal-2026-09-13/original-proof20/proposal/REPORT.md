# Fixed-buffer endian consistency proposal

2026-09-13. The proposed comparator passed **37 synthetic cases, 0 failed**, in **0.004261 seconds**, with native and qualification exits 0. Both copied source hashes remained unchanged, stderr was empty and the guarded run reported no unexpected audit events. It generated constants in memory; it did not inspect the actual checkpoint or any storage bytes.

The source-derived buffers provide a useful candidate basis: require all 125 ordered Hamming values and all 125 ordered time-vector values to fit the same orientation, with exactly one of little or big endian satisfying a fixed eight-ULP threshold. The checks cover both orientations, both complete buffers, inclusive eight-ULP and rejected nine-ULP boundaries, changed order/signs, infinities/NaNs, immutable exact-length inputs and explicit neither/both decision refusal. The ambiguity case tests the decision helper directly; it does not claim a complete ambiguous fixed-buffer byte example exists.

| Generated operation-order comparison | Maximum observed float32 steps from the analytic reference |
| --- | ---: |
| Centered Hamming cosine formula | 0 |
| n_: binary32 division before multiplication | 1 |
| n_: binary32 division and rounded 2*pi scalar | 2 |
| n_: double intermediate before final cast | 0 |

Those are generated stdlib examples. No historical NumPy or Torch kernel ran. The eight-ULP margin has a conditional rounding rationale for ordinary binary32 arithmetic; the Hamming calculation also requires an explicit error assumption that retained Python source alone cannot certify for every historical backend. See NUMERICAL-BASIS.md for that limit. Small edits inside the tolerance can pass, so success cannot establish buffer immutability or writer authenticity.

An independent source reviewer found no comparator defect and verified all four retained source bindings. As a separate refusal explanation, the source formula implies positive window values within the conservative exact-binary envelope 2^-4 < window < 17/16, and negative time-vector values with 2^-12 < abs(n_) < 2^-4. The first time value also has exact division -125/16000 = -1/128. These facts could contradict an orientation with much weaker numerical assumptions. They do not replace the complete comparator or add an acceptance rule, and no predicate was changed after the synthetic run.

The comparator source hash is `bfbb83800d127f031008c31fa669b093dca3d945ae2543db1b834f93c1d51373`; the harness is `fe0e3e5559ecc237bf6d7af4b8f38a4d68d557daa574e4470058c2f2b2fa7aa3`. The proposal is separate from the frozen converter and its sealed 82/0 results. `REAL_PROFILE` remains unavailable. The next decision is whether to accept this explicitly conditional consistency basis as part of a reviewed protocol; actual archive/version observation, full digest/ZIP/CRC binding, uniform storage encoding, model notices, conversion approval and runtime validation remain open.

The peer's written verdict covers source and source bindings only. The 37-case harness and raw result are author qualification; they have not received a separate independent execution or final harness/receipt verdict in this proposal.
