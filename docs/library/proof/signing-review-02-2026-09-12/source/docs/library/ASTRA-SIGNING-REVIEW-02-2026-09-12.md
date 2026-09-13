# Signing repair verdict

Accept the PowerShell host, certificate preflight and build-receipt repairs for
candidate qualification. Actual Uoink signing remains unobserved and the release
remains held. The publisher certificate and timestamp service still need Ryan's
selection. Package 08 is unchanged and does not qualify this newer build source.

Gemini e922b3bf reviewed d24cc33. Astra independently ran its three named suites
and five probes: 39 passed. The documentary diff was applied with git apply
--3way; the same three established suites passed 34 cases in the checkout.
The five proposed probes are archived outside the active test tree. They do not
provide five valid regression tests: two simulate an incorrectly split Inno
filename, one assumes a fixed PowerShell installation, one inspects a certificate
algorithm rather than the executable digest, and one supplies Verify as a
property rather than a certificate method. Existing committed tests are unchanged.

The worker's quoting finding is rejected. Inno defines $f as a quoted filename;
adding $q around it is not the documented repair. Its source-level PowerShell 7
finding is valid. The callback now resolves Windows PowerShell from the system
directory, with real host-selection checks under both installed shells. The
preflight also checks certificate trust and explicitly loads the built-in Cert
provider when absent. Semicolons inside a quoted -File argument are not evidence
of script execution. [Inno SignTool reference](https://jrsoftware.org/ishelp/topic_setup_signtool.htm).

The stale receipt and missing uninstaller findings are valid. Before compilation,
the build preserves the old EXE/receipt and marks the current attempt unverified.
Callback records retain success, failure and SignTool diagnostics. Signed success
requires final installer/uninstaller verification and matching callback hashes.
The release checklist now requires signed mode and the exact final receipt.
The remaining Get-FileHash uses were replaced with the shared stream hash; an
unsigned build failure from that command had been a hypothesis, not an observed
product result.

The signer explicitly requests SHA256 file and RFC 3161 timestamp digests.
The verifier's scope is trust, publisher, timestamp and artifact hash; it does
not separately parse executable digest algorithms. Checking X.509
SignatureAlgorithm would not establish that property. A read-only verifier check
on Microsoft's existing SDK SignTool passed with unchanged bytes; it gives no
Uoink signing credit. [Microsoft SignTool reference](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool).

Host repair: 38 passed. Receipt attempt 01: 43 passed / four failed. Production
corrections address Windows PowerShell's null-string overload conversion and
missing Cert provider; the same 47 assertions then pass. Direct Inno wiring04
records compiler exit 2, one durable missing-certificate refusal, no installer
and no observation forwarder. A subsequent diagnostic-capture addition records
native SignTool output and exit status; the final focused tree has 48 passes /
zero failures. Earlier failures remain.

These tests use synthetic files and mocked signing boundaries. The real compiler
observation is a refusal, not successful signing. Full candidate qualification,
the final signed build and installed release checks remain separate work.
