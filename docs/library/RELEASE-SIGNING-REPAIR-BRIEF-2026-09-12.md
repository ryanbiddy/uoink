# Release signing repair, 2026-09-12

The build creates an unsigned installer and has no verified signing path. Add an
optional release-signing mode that refuses missing prerequisites before staging.
It must sign both Inno Setup and its uninstaller, select an exact certificate
from the Windows certificate store, require SHA256 and an RFC 3161 timestamp,
then verify publisher identity, trust and timestamp. No private key or password
may enter a command, receipt or repository. Do not create a test certificate,
modify trust stores, buy a service or sign the existing package 08.

Scope: build.ps1, installer/uoink.iss, two signing scripts, new regression tests
and docs/build-installer.md. Existing tests and package 08 stay unchanged.
Keep unsigned review builds available and clearly labelled. Signing does not
clear the dependency hold, historical receipt failure or client acceptance.

Validation: PowerShell parser checks, new behavioral tests with mocked certificate
and SignTool boundaries, and existing installer-lock/build-guide suites. Exercise
missing certificate, wrong publisher, untrusted or absent signature, absent
timestamp, signing/verification warnings and failures, unsafe command fields,
and the compiler hook. Never run a mock signer against a release executable.
Actual signing remains unobserved until Ryan selects a suitable certificate and
timestamp service. The standard personal stores currently contain no code-signing
certificate, and SignTool is absent from PATH. Build the combined candidate only
after its changes are reviewed and its full tree is complete.

References: Microsoft's SignTool reference and Inno's SignTool, SignedUninstaller
and SignedUninstallerDir documentation. These define verification, nonzero
warning results and compiler callbacks; they do not certify this product.

First validation: signing12-checkout01, 32 passes / two failures. Both failures
occurred when the verifier called Get-FileHash, which was unavailable in the
isolated child PowerShell. The ordinary PowerShell process resolves that command;
the exact command-discovery cause is not established. Repair: the verifier now
uses a disposed .NET SHA256 stream, avoiding that module-discovery dependency.
Rerun the identical three test files as signing12-checkout02. The failed result
stays under _scratch/signing12-checkout01. No fixture correction or acceptance
assertion change is involved.

The identical checkout02 selection passed all 34 cases. An additional synthetic
Inno wiring check intentionally requests a nonexistent certificate. The first
wrapper stopped on the compiler's expected stderr before recording its exit;
retain signing12-inno-wiring01 as incomplete. Wrapper02 temporarily captures
native stderr with ErrorActionPreference=Continue, then immediately restores
Stop and asserts the actual nonzero exit, missing-certificate message and absent
installer. Only the observation wrapper changes. No real certificate or release
artifact is used, and this grants no successful-signing credit.

Wrapper02 records compiler exit 2 and no installer, but Inno does not forward
the callback's output into compiler.log. Its two callback-evidence assertions
therefore fail; this is not a positive wiring result. Wrapper03 adds an
observation-only forwarding callback that records its bound arguments, redirects
the unchanged production callback's output to a separate log, and propagates its
exit. The expected refusal, algorithms, arguments and product code stay unchanged.
