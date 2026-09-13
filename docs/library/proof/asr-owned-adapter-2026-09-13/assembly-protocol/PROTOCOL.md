2026-09-13. Proposed documentary execution only, pending root review of build_combined.py and verify_combined.py. No test, child model, kernel API or copied source will execute.

After verifying the preparation's exact hashes, root may invoke C:\Python314\python.exe -I -S -B with build_combined.py once. It binds the old 209-payload archive manifest and all 37 independent-root file hashes, checks recorded outcomes and source-copy differences, then writes only the fresh fixed _scratch/asr-adapter-combined-proof01 directory. It never modifies earlier archives.

The builder copies immutable prior payloads and manifests, independent inputs/raw receipts, the assembly protocol, verdict and outer manifest. Every copied file is checked against its source bytes. It checks recorded case equality and outcome guards before creating the output directory. A failed check stops assembly; no output cleanup or implicit retry is allowed. Source paths must be private and quiescent during this documentary copy; these checks are not kernel-enforced atomic snapshots.

Root may then invoke the separately reviewed verify_combined.py using the same stdlib interpreter and flags. It checks complete outer membership, byte hashes, nested seals, recorded 58-case equality, exits and preservation of the failed null receipt. It imports no archive source. Preserve the actual builder/verifier tool outcomes and resulting manifest hash.

The observed input inventory initially had a null aggregate, preserved in ROOT-INPUTS.json with HASH-INVENTORY-REPAIR.md. ROOT-INPUTS-v2.json retains the same 37 rows with the corrected 217,293-byte total, and is the only inventory accepted by the builder. No diagnostic or qualification is rerun to assemble this proof.
