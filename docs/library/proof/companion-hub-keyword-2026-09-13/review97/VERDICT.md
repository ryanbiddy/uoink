# Independent Hub keyword review — 2026-09-13

The existing one-line source proposal is accepted for this narrow synthetic
argument-forwarding contract. It removes only
`kwargs["local_dir_use_symlinks"] = False` from the output-directory branch at
upstream utils.py:108. The 4,897-byte proposed source retains SHA-256
`ecec29ad34688e2d559218685672c3c2f1086f524d78bcfd53e633a5739d5b19`.
The patch remains inert; no package, combined derivative or wheel was changed.

The captured Hub implementation signature at
`qualification/hub-signature-source.py.txt:120` accepts `local_dir` but has
neither the obsolete keyword nor `**kwargs`. Its 31,197-byte source has SHA-256
`29c2316ec5d0862d0311b0a2cfd97cd39be636042073cef427279b4261893a93`.
The signature adapter preserves positional/keyword-only names and requiredness;
every keyword-only parameter has a default. It does not evaluate annotations,
default expressions, decorators or the Hub function body.

| Attempt | Passed | Errors | Child / outer exit | Guard | Meaning |
| --- | ---: | ---: | --- | --- | --- |
| Original baseline01 | 4 | 4 | 1 / 1 | Invalid | Four denied opens; retained failure |
| Original baseline02 | 4 | 4 | 1 / 1 | Invalid | Compile-filename change did not resolve guard |
| Diagnostic01 | 4 | 4 | 1 / 1 | Valid | Absolute script / contained cwd did not reproduce guard |
| Diagnostic02 | 4 | 4 | 1 / 1 | Invalid | Relative script / checkout cwd reproduced exact denied paths |
| Corrected baseline03 | 4 | 4 | 1 / 1 | Valid | Existing obsolete keyword raises TypeError |
| Proposed patched03 | 8 | 0 | 0 / 0 | Valid | All eight forwarding contracts pass |

Every attempt has zero assertion failures and zero skips; the baseline defects
are TypeError errors, not passing cases. Diagnostic02 recorded exactly four
denied lexical paths, all `E:\AI\projects\uoink\checkouts\Yoink-library\<unknown>`.
The diagnostic hook did not open or stat them. The earlier filename hypothesis
was insufficient. Python 3.14 traceback formatting uses `ast.parse`, whose
default filename is `<unknown>`; this is a source-based lead, not a claim that
the entire internal stack was separately traced.

The measured repair is confined to unittest error rendering: print the same
exception type/message and raw traceback frame file/line/function fields without
source lookup. The allowed read roots and eight Contracts assertion bodies are
unchanged. Corrected runs use the original relative-script/checkout-cwd convention,
with offline flags, scrubbed credentials and the same stdlib import/network guard.
Both corrected receipts report inputs unchanged and no blocked operation.

The eight cases cover output-directory calls in local-only and fetch modes,
explicit/mapped repository IDs, revision/cache/token forwarding, false tokens,
invalid names, return values and original helper exceptions. They execute only
the extracted helper with fake Hub/progress seams and a captured signature.
No Hub request, package import, tokenizer/model, file download or real build ran.
This qualifies the narrow source proposal, not Hub I/O behavior, asset integrity,
the full module, model-stack compatibility, an installation or market readiness.
The original B2 wheel and all earlier seals remain unchanged.
