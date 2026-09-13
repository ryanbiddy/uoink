# Independently verify the unchanged candidate02 graph

Astra's proposed extra-key correction was wrong. The original lock does not
request root extras; Lightning requests fsspec[http] and MCP requests
pyjwt[crypto]. Graph01's actual active_extras already contains both. The
correction preflight exited one at its original-lock assertion before writing
a new selection or invoking the checker. Preserve that diagnostic and withdraw
the proposed correction. No graph02 result exists.

Verify the completed agent's graph with the unchanged selection and retained
metadata under a fresh Astra review label. This is independent verification,
not an attempt to relabel the failed graph. Preserve the actual exit, five
WhisperX conflicts, two source-only wheel failures and local NLTK evidence gap.
Hash all 342 source payloads before and after and verify the nine captured
retrievals and exact metadata bindings. No fetch, runtime/model execution,
installation, production change, accepted-test change or publication occurs.
