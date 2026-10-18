# Static VAD metadata is available; checkpoint remains refused

The reviewed selected-root diagnostic returned useful partial metadata on
2026-09-13. The actual reader and outer process both returned **2**, retaining
`Reference cycle refused`. This is not checkpoint, model or runtime acceptance.

Author and root each passed all 63 synthetic cases, actual exit zero. Root's
run took 0.047207 seconds with five unchanged inputs. The source delta,
independent review, unchanged inherited assertions, narrow synthetic signature
adaptation and unexecuted deadline-repair draft are preserved. The independent
review found and closed a prequalification serialization-deadline gap.

The single actual `symbolic-projection01` invocation took **0.034605 seconds**.
It records the same fixed artifact identity and a fully traversed, acyclic
selected closure: **1,069 nodes and 54 tensor argument descriptors**. Present
selected roots are `state_dict`, `hyper_parameters` and `pyannote.audio`.
The 190,182-byte receipt remains below the unchanged 256 KiB limit; its hash is
`60b0078f3367bf80b8ed526d681850c47b0caae09f4fbd8da3de0883f927247d`.

The selected records include sample rate 16,000, one channel, SincNet stride 10,
LSTM hidden size 128 with four bidirectional layers, and two linear layers of
size 128. The architecture entry names PyanNet. These are recorded literals and
references, not evaluated constructor state or independently trusted model
configuration. Tensor sizes, strides, storage and hooks remain symbolic
arguments. No referenced class, reducer, object or tensor was constructed.

Whole-graph acceptance still fails. The selected acyclic values may be shared
with omitted training roots; their semantic ownership and provenance remain
unknown. No storage member was decoded. Normal final artifact-identity checks
are not reached after the strict refusal, so the receipt does not establish
atomic or post-inspection file stability. The copied reader remained unchanged.

Next, map this safe JSON evidence to the existing fixed-loader source proposal,
checking every configuration and tensor-schema requirement and retaining
unknowns. Do not select classes from checkpoint strings or infer missing defaults.
Any source-defined defaults must be identified separately from recorded values.
Conversion, native execution, compatibility and release approval remain open.

Proof: `proof/vad-selected-projection-2026-09-13`, **228 payloads**, manifest
`700044423a8a8c0728524b8c3621c7378e41daf302d2137df4f0492d2d1ee8cf`.
It includes the unchanged 214-payload preparation seal and actual launch evidence;
no checkpoint or model storage payload is archived. Production source and the
full-tree result at `56d9d4c` remain unchanged: 2,796 passed, one failed, three
skipped, plus 13 passed subtests. Website and marketing remain paused.
