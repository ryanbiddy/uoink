# Optional direct-empty-list defect — 2026-09-13

pc01's separate diagnostic called the selected captured Pipeline.__call__ through
FasterWhisperPipeline with `[]`. It raised IndexError at `base.py:1242`, before
parameter normalization, call counting or loader construction. The first-item
chat classification indexes the list without an empty check.

The scoped empty-generator contract passes: the generator branch catches
StopIteration, substitutes an empty list, then reaches normal list iteration.
The captured transcribe code supplies a generator at `asr.py:266`; the observed
list defect therefore does not contradict this default boundary result.

If direct list input is part of the supported public interface, make a separate
reviewed repair that avoids first-item classification for an empty list while
preserving normal parameter handling and empty output. Add independent direct
empty-list, empty-generator, nonempty-list, first-item order and chat boundary
contracts before execution. Inspect tuple/KeyDataset semantics separately;
do not infer their acceptance from this probe.

No fix is applied here, and no direct-empty-list assertion is counted as passed.
The original captured files, test bodies and pc01 receipt remain unchanged.
This ordinary source defect does not by itself require a new Ryan decision;
the scope of any dependency derivative still belongs in its separate review.
