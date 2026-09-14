# Token-lookup cleanup finding

In retained durable8de6757dd1c21399d8bae5cf0accdeac28368b150d27e4fa54622559ed4b047b, `_flush_quarantine` lines353–371 resolves `self._token(key)` before its preserving try. If the new attempt check rejects a removed token-map entry, kernel cleanup can retain that original failure, but this subsequent lookup raises a new exception outside the catch and replaces the primary error.

Move that lookup into the existing try. With an original exception supplied, the current catch adds an uncertainty note and preserves it; with original=None, the existing bare raise remains. Root identified this called-path issue and this reviewer confirmed it at95202a/0. No subject was executed.

The earlier passive check03e249 describing an unchanged durable pre-factory head applies only to the prior8de snapshot. The final source must instead preserve that head except for this explicitly reviewed movement.

