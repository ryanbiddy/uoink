# Dependency review verdict, September 11

Gemini run 122dbb53 is accepted as an investigation with corrections, not as a
release clearance. Its report is retained verbatim. Astra independently retrieved
the two PyPI 2.6.6 records and OSV GHSA-qqmf-gpg7-g8gw, then downloaded and hashed
only the two Python wheels. No checkpoint, model or media was downloaded or run.

The worker's wheel sizes and SHA-256 values are wrong. The observed artifacts are:

| Wheel | Bytes | SHA-256 |
|---|---:|---|
| lightning-2.6.6-py3-none-any.whl | 849265 | 2bcbd6ee840071cd076c7dc9953d7ac1040df92f1c5fa76583aae644f037ab85 |
| pytorch_lightning-2.6.6-py3-none-any.whl | 853045 | 71f95c7b22f25c4f91cc659e1734bcdc6c69c8b66543f2ed2d78dbe29ce2f167 |

Both ZIPs contain the instantiator allowlist and imported-subclass checks in
core/saving.py. The [upstream release](https://github.com/Lightning-AI/pytorch-lightning/releases/tag/2.6.6)
documents both repairs. PyPI metadata gives the expected existing peer constraints.
This supports qualifying the two-package upgrade, not declaring it installed.
Raw records and wheels are retained privately under
_scratch/dependency-closure-astra-01; the report diff is retained separately.

OSV still reports a fixed event of 2022.6.15. Do not silently rewrite its result
or promise that a new scanner run will drop two entries. Report scanner findings
and the independently inspected upstream correction separately. Exact remaining
counts require a fresh audit on the final inventory.

The report's call-path discussion is static inspection, not an executed trace.
Its claim that a preflight hash neutralizes same-user malware is too broad: a
same-user writer can race the subsequent open or change the checker itself.
Such a guard detects ordinary corruption or a preexisting mismatch; it does not
establish a new security boundary or clear Torch advisories. No guard or VAD
switch is accepted by this verdict. NLTK tokenizer and transitive reachability
claims also need package-specific inspection before a risk classification.

Proceed under LIGHTNING-266-REPAIR-BRIEF-2026-09-11.md. Keep the old audit and all
other security, signing and installed-client gates open. No source test suite
was named for this report-only run; no product source or test changed during
its integration. The newly inspected upstream evidence supersedes the worker's
incorrect artifact table.
