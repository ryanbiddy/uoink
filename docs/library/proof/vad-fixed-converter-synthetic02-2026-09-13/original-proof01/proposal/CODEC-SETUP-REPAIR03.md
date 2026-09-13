# Preload the exact stdlib BOM codec

`converter-preflight02` exited 1 before the case loop when decoding the pinned plan JSON as UTF-8 with a possible BOM. Python lazily imported `encodings.utf_8_sig`, which the closed import audit had not preloaded. The audit refused that import. No case counts were emitted; preserve the raw traceback, empty stdout, source copies and actual exit receipt.

Preload only the standard-library `encodings.utf_8_sig` module beside the already-preloaded cp437 codec, before establishing the import allowlist. Keep all subsequent import/file/network denials and all behavior assertions unchanged. Run under the fresh label `converter-preflight03`; no converter, plan or ZIP implementation change is needed.
