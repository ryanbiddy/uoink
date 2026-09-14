# Initial-entry helper finding

The first durable correction bc95b798512a588af9a46e591fb7d1d69d19f7c5d8218d7c7e13ad5f071fd20e closes replacement after entry, but still selects current named helpers before establishing their original identities. At lines539/558 it stores and later calls `adapter._capture_controller_boundary`; a replacement installed after actual startup issuance and before open can run under manager/token locks before the original function-set check is reached. Later refusal does not undo that call. Line543 likewise captures the current `_require_factory_start` with no source-owned original anchor.

Select capture/entry/boundary from the existing source-owned adapter tuple and compare current names before acquiring either lock. Add a fixed source-owned anchor for the new durable guard, and select/check it before entry. The new negative boundary should install a failing trap before open and require zero calls to that replacement, not merely an eventual refusal.

Root independently identified this finite new-helper issue; this reviewer confirmed it in the retained bc95 source. It is not a claim about every legacy module global. No candidate was executed. Preserve this draft and the first helper correction before revising.

