Source review supports integrating this bounded reliability repair. I found no
remaining blocking product defect within the committed brief after reading the
three-file product diff and all four new regression files. This review did not
execute tests or import product code.

The final source differs from the preserved Grok output by exactly two lines:
retain the lexical absolute cache root before checking resolution, and permit
the saved download estimate only when the selected model is the saved model.
server.py and the three worker regression files are byte-identical to their
original preserved versions. The fourth regression matches its earlier capture.
FINAL-ROOT-BINDINGS.json records exact final worker and checkout hashes.

Ordinary reliability constructors default to local-only, and both ordinary
call sites pass that policy explicitly. ensure_model remains the explicit
acquisition path. Readiness checks the consent marker, selected repository,
bounded main reference, snapshot identity and nonempty required files without
model imports or construction. Internal repository blob links remain supported.
Settings have one label function for six choices, per-choice approximate sizes,
honest unknown-size handling and confirmation before the selected-model POST.

One nonblocking coverage weakness remains in the new local-only test file:
the default-load and detection cases check root.exists() after TemporaryDirectory
has removed the tree. Those assertions cannot establish whether the directory
existed during the call. Current production source does gate mkdir on explicit
acquisition. Preserve these assertions; an independent assertion inside the
temporary-directory context can strengthen that claim later.

The accepted evidence is source review plus the guarded synthetic/local test
scope. The cache check establishes minimum structure, not artifact integrity,
tokenizer validity, model usability or atomic protection against path replacement.
No native ASR, model download, installed GUI, full-tree or market-readiness
acceptance follows from these runs.
