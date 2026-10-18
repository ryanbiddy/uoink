# Optional signing path: focused verification complete

The build can now reject incomplete signing configuration before staging and
route Setup and its uninstaller through one certificate-specific signing and
verification callback. A fresh Inno cache prevents reusing another build's signed
uninstaller. Unsigned review builds remain explicit, and their hash-bound receipt
replaces any stale signed receipt. No actual publisher certificate was used.

The signing, installer-lock and build-guide selection passes **34 tests** under
the isolated integrator runner. Its first result, **32 passes / two failures**, is
retained. The verifier's failed Get-FileHash dependency was replaced with a .NET
SHA256 stream; the same selection then passed. Existing acceptance files were
not edited. This is focused verification, not the complete candidate tree.

The real Inno compiler also invoked the production callback through a forwarding
observer, with spaces in both callback and tool paths. A deliberately nonexistent
certificate was refused, the compiler exited 2, and no installer was created.
This proves the observed refusal and argument routing. It provides no successful
signing credit. Two earlier observation-wrapper failures remain in the archive:
one stopped on stderr, and the next could not see Inno's separate callback output.

Proof: proof/signing-repair-01-2026-09-12/SHA256.json. It includes source hashes,
test logs/XML, the three wiring attempts, exact wrapper scripts and a labelled
reconstruction of the verifier before its hash repair. Windows 11 Home was
observed on this host, with neither WindowsSandbox.exe nor vmconnect.exe present.
No code-signing certificate was returned from the standard CurrentUser/My and
LocalMachine/My stores; SignTool was absent from PATH. This does not exclude a
certificate or SDK stored elsewhere.

The release still needs the dependency repair, client acceptance and historical
receipt disposition. Successful certificate signing, timestamp-service behavior
and installation of the signed bytes remain unobserved. The changed build source
must receive full-tree qualification before a replacement package is built.
