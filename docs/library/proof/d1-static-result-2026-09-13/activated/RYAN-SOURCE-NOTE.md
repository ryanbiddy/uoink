# Ryan's D1 static-inspection ruling

Recorded by Astra from Ryan's reply in this conversation on 2026-09-13. This is a transcript note, not a fabricated tool receipt or model-execution approval.

The question presented to Ryan was:

> Can I proceed with the reviewed D1 checkpoint inspection? It will hash the existing 17.7 MB VAD checkpoint offline and interpret only two 500-byte buffers plus two version bytes. It will not load a model, evaluate pickle, convert anything or fetch data. This is the remaining D1 decision reserved for you in RELEASE-OWNER-DECISIONS-2026-09-12.md; the inspection code and focused checks are already reviewed. I recommend approving it so we can resolve that part of the runtime qualification.

Ryan's exact answer was:

> Approve D1 static inspection only

The referenced reviewed invocation binds the existing checkpoint at `installer/staging/python/Lib/site-packages/whisperx/assets/pytorch_model.bin`, 17,719,103 bytes, SHA-256 `0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea`. Its expected inventory and fixed eight-ULP basis remain as reviewed in ASTRA-D1-INVOCATION-REVIEW-2026-09-13.md and ASTRA-VAD-D1-ADAPTER-VERDICT-2026-09-13.md. Any size, hash, inventory, version or consistency mismatch must remain a refusal.

This permits preparing and executing that static inspection after exact activated-source and invocation review. It does not approve D2 conversion, new downloads, native model execution, stack migration, installation, signing, publication or changes to the live library. The converter's REAL_PROFILE stays None.
