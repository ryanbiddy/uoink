# Signing review repairs: host selection and release instructions

Gemini e922b3bf identified that joining powershell.exe to PSHOME fails under
PowerShell 7. Select the installed Windows PowerShell host through Windows'
system directory instead, preserving the already qualified callback runtime.
Add real read-only host-selection checks under both available shells. Do not
sign, install, alter certificates or change existing tests.

Also check the selected certificate's trust chain during preflight, so an
untrusted certificate cannot trigger the full staging work before rejection.
Add mocked positive/negative chain controls without using a private key.
Update the launch checklist to require the explicit signed-build arguments
and the final receipt. Unsigned builds remain review artifacts.

Run the new host-selection suite plus the same three prior signing/build suites.
Keep all first-run failures. The earlier d24cc33 result remains 34 focused passes;
this source change needs its own result and eventual full candidate tree.

The worker's DEF-01 is rejected: Inno documents $f as the quoted filename.
Replacing it with an unquoted test string does not reproduce Inno's substitution.
Semicolons or apostrophes inside quoted arguments to PowerShell -File are not
automatically script execution. No quoting assertion will be weakened. Review
the worker's other claims separately, including stale receipts and callback
diagnostics. These repairs alone do not clear those open items or the release.
