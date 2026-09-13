# Preserve each compile attempt and signing outcome

Gemini e922b3bf correctly found that a failed compile leaves the old signature
receipt beside a possibly changed installer. Inno also swallows callback output,
and the build does not retain a verified uninstaller receipt. Repair these three
gaps before public signing is attempted. The earlier failed wiring attempts stay
failed; this is new code and needs fresh evidence.

Before invoking Inno, create a fresh attempt directory, preserve any prior EXE
and receipt, and atomically replace the current receipt with an unverified
pending record. Record each signing callback's successful verification or error
in that attempt directory, with exclusive filenames. A callback whose receipt
cannot be written must fail. Compilation failure must leave a failed/unverified
current receipt and preserved diagnostics. Unsigned success remains unverified.

For signed success, reverify the final installer and every cached uninstaller,
require matching successful callback hashes for each, and record the results in
the attempt and current receipt. Do not infer SHA256 file-signature algorithms
from the signer's X.509 certificate algorithm. The signer explicitly requests
SHA256 file and RFC 3161 timestamp digests; trust verification has its existing
documented scope. No certificate creation, signing-service use or release credit.

Add a new receipt suite using synthetic files and mocked signing boundaries.
Cover old-receipt preservation, pending/failure state, missing callback evidence,
changed artifact hashes, uninstaller coverage and durable callback refusal. Run
it with the host, original signing, installer lock and build-guide suites. Run a
fresh minimal Inno refusal check against the production callback without the old
observation forwarder. No full release compilation or installation in this step.

First focused attempt signing-receipts12-checkout01: 43 passed, four failed.
Three failures come from Windows PowerShell converting the null backup filename
in File.Replace into an invalid path. Pass NullString.Value explicitly to the
.NET overload. The fourth records a missing Cert provider instead of the intended
missing certificate: load the built-in Security module explicitly before opening
that store. Preserve the original source and result. Run the same 47 cases with
the same assertions under a fresh label after these production corrections.
