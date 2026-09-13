# Preseal clarification

Root reviewed the concrete factory and requested an explicit plain-string-key boundary. Preserve the first unexecuted factory and its manifest before adding the check. The approved reader remains the source of the dictionary; the proposed factory also refuses any key whose exact type is not `str` before comparing the key set. No model code was or will be run by this task.

The original tensor table is preserved. Its `Declared elements` and `Advertised bytes` columns describe the referenced whole storage, not one tensor's payload. Storage `16` therefore appears 32 times. The evidence report and supplement give the distinct storage total and each tensor's offset/range. The original mapping's aggregate equality check is false for shared views by design; it is not a model failure.

The final manifest will be a separately named `manifest.proposal02.json` with the refined factory hash. The first `manifest.proposal.json` remains an unexecuted draft bound to the earlier factory bytes.
