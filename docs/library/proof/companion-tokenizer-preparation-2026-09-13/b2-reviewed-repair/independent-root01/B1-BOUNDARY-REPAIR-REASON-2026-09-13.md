# B1 empty-buffer result and B2 repair reason — 2026-09-13

The first arm `b1-boundary01` ran ten cases: **6 passed, 4 failed, 0 errors,
0 skips**, actual process exit 1. All six original assertions still passed.
The four new cases failed with the following recorded behavior:

| local_files_only | Ambient tokenizer file | B1 observed result |
| --- | --- | --- |
| true | present | File parser then constructor; no exception; model/tokenizer assigned. |
| true | absent | FileNotFoundError without a buffer-parser call; no model allocation. |
| false | present | File parser then constructor; no exception; model/tokenizer assigned. |
| false | absent | Constructor then remote fallback; no exception; model/tokenizer assigned. |

These reproduce the truthiness boundary. All cases supplied `tokenizer.json`
as b'' in a nonempty files dictionary. The new fake buffer parser rejects that
input with ValueError, but B1 never called it. The original six cases did not
exercise empty supplied buffers, so their six-pass result remains valid for
their scope and does not close these four failures.

Proceed with the already briefed B2 candidate, changing only B1's
`if tokenizer_bytes:` to `if tokenizer_bytes is not None:`. Its exact source
SHA-256 is `bf452635becacf6bba46825be6d6eea533da472ce966ee47f5ce7bccfc3bf06d`.
That routes explicitly supplied empty bytes to the parser before considering an
ambient file or allocating the model. No test or helper repair is needed; use
the identical ten assertion bodies and unchanged guards for `b2-candidate01`.

Raw B1 traces, call events, environment plan, input hashes and real exit remain
in their original run/launch folders. This is synthetic parser ordering and
refusal evidence, not a claim about actual tokenizers' exception types or native
model execution. The full B1/B2 source texts are inert apart from the explicitly
selected constructor prefix used by the guarded harness.
