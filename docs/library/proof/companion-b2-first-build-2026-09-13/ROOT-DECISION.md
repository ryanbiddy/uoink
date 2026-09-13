# First local tokenizer wheel build: root decision

Reviewed 2026-09-13 at checkout 5d8292c174bc72f97c8656e1107ff68c959a07a7.

Proceed once with `py314-01` under the user's existing authorization to fix
and prepare Uoink. This is a local byte-only package build, not a model run,
installation, frozen-test change, new fetch or release acceptance.

The preparation manifest must be
`ebab6c9180c7c8f230e55b619d1cc469d7043f1a43e197a3a8abd126f7eb7484`.
Its 21 payloads must match their declared lengths and hashes before launch.
The launcher is `95900e3ef3b5b1fdd7179a715168dbde65fe7c909b30c1c0a181963ef1e61633`;
the child is `3becaed597aa15f3b2fc5d5cc816aaf172d89cfa4165aed92d18e47fb56ccc73`.
Root read both completely, along with the brief, reviewed builder and prior
synthetic qualifications. Author and root each observed 62 passing builder
cases; earlier failed attempts remain preserved.

The only package input is the already captured, exact-size/hash upstream
wheel named in the brief. ZIP members, including its ONNX asset, are opaque
bytes for manifest/RECORD validation and unchanged repacking. No model parser,
unpickler, tokenizer module, provider, installer or native model library runs.
The child checks Python 3.14.6 and no-site isolation, blocks non-stdlib imports,
network and subprocess activity, and restricts file access. Writes remain
inside a fresh scratch run. Root pins the manifest externally because the
launcher itself verifies payloads but does not pin the manifest digest.

The bounded reads and identity checks assume quiescent local paths. They do
not provide an atomic boundary against a hostile process with the same user
access. Python 3.13 reproduction is a separate pending action; neither the
original embedded runtime nor its site hooks will be launched here.

Retain actual child and outer exits, console, input identities and output
receipt. Any failure remains a failure and requires a documented repair and
fresh run label before retry. A successful build qualifies packaging only.
Runtime security, signing, the historical receipt and isolated client checks
still prevent market approval. Website and marketing remain paused.
