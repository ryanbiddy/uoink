# Companion B baseline and repair reason — 2026-09-13

The preregistered `baseline01` arm ran six unchanged constructor contracts on
the retained original source: **1 passed, 5 failed, 0 errors, 0 skipped**, process
exit 1. The raw per-case traces remain in `runs/baseline01/result.json` and
`tests.log`; the launcher receipt records unchanged input hashes.

The explicit non-local fallback passed. Invalid local tokenizer input and a
tokenizer disappearing after the file check both recorded `constructor` before
`tokenizer.file`, when the contracts require refusal before construction. The
missing-local-tokenizer case did not raise the required `FileNotFoundError`.
Valid local tokenizer input and supplied tokenizer bytes were handled after
`constructor`, reversing the required order. These are reproduced behavior
failures in the selected original constructor prefix, not harness errors.

The existing companion-B patch moves available tokenizer preparation ahead of
the CTranslate2 constructor, and raises `FileNotFoundError` before that
constructor when `local_files_only=True` and tokenizer input is missing. It
retains the explicit non-local fallback after construction. Its exact SHA-256
is `ef6e3ea49d4a30279ec6a37dc5d737db5ea8d8d1191af25c578f6411c407b764`;
its derivative text is
`e500e12b0a58420ce5f41b202ba7d942b901a9b99c617d6ca3d3304b9493f269`.
The preparation receipt verifies this patch reconstructs that derivative.

Proceed with the already briefed `candidate01` comparison arm, using those
unchanged derivative bytes and the same six assertions. No fixture, helper or
assertion changes are needed. Retain baseline failures regardless of the next
result. This comparison runs selected AST code with fake tokenizer/model seams;
it does not qualify a real tokenizer, model, native runtime or complete package.
