# Sealer launch refusal and bounded correction

The first native-Python sealer invocation stopped during interpreter startup:
the inherited sitecustomize audit guard required IG_FORBIDDEN_LIVE, which the
shell invocation had omitted. The script never opened or created the seal.
The observed error was KeyError: 'IG_FORBIDDEN_LIVE', followed by Python's
can't-open-script message. The shell continued its independent Git commands:
79ec2f5 contains the repair brief only; no proof files were committed there.

Keep the unexecuted sealer draft. Set the required forbidden-path string and
scrub provider variables before the corrected invocation. The new script checks
the documentary 79ec2f5 sealing HEAD, separately preserves the actual b62aab3
measurement source, and checks their mirror Git blobs are identical. No test
rerun, measurement correction or guard weakening is involved. Use fail-fast
native-command exit checks for the subsequent seal/add/commit sequence.
