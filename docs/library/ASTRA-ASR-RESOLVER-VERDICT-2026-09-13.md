2026-09-13. Accept the trusted-manifest resolver as a qualified scratch proposal.
It is not installed, wired into the product, or approved for real assets.
Production remains e8d058f; website and marketing remain paused.

The author and independent Astra runs each passed the same 87 cases with zero
failures, in 0.262197 and 0.224466 seconds respectively. Qualification, native
and outer exits were all zero. Exact case membership agrees, all eleven copied
and original inputs remained unchanged, stderr was empty, and no audit denial
occurred. These are 87 distinct synthetic cases repeated independently.

The first run remains failed: 64 passed and nine failed, all exits one. A separate
forty-file diagnostic found nine differences confined to Windows cross-API
ctime: path observations returned birthtime there, while handle observations
returned modification time. Same-API observations remained unchanged. The
repair compares required birthtime and six other exact fields across APIs,
preserves complete path and handle records separately, and checks both through
rebind. It adds no time tolerance; non-Windows ctime remains strict. Fourteen
regressions cover this repair. The original 73 assertions are unchanged; their
scratch stat-copy helper now conditionally carries an existing birthtime.

Astra reviewed the source and repair before execution and independently verified
the final proof: 138 payloads, 1,274,072 bytes, seal SHA-256
8a0cc12d716711d0898b726e7cfcaa5c83827ecaadcacd137b9db5ac271656c4.
The archive contains 415 verified generated files and 312 directory entries;
forty diagnostic files are also retained individually. All 128 mapped source
copies and the original 134 preliminary payloads remain byte-identical. The
preliminary sealer exited zero but left two aggregate-size fields null; a fresh
documentary seal corrects those summaries and preserves the original manifest.
No source, assertion, fixture or raw measurement changed for that correction.

The diagnostic map keeps historical path/handle observations separate from
copied file metadata. Its hashes bind the retained bytes at sealing; the
diagnostic itself did not record historical content hashes. The independent
root launcher retained the author's plan label, but its distinct absolute run
path, admission and outer tool receipt identify the independent execution.

REAL_APPROVAL remains None. Twenty ordinary-file SHA-256 values are still absent
from the six public plans. The resolver requires a complete externally accepted
manifest, exact private snapshot membership, content hashes and revalidation
before returning local-only constructor arguments. Generated placeholders
cannot authorize real assets. Private directories must remain quiescent; the
future native reopen still needs a lifecycle design and runtime qualification.
No model import, constructor, download, install or inference was exercised.

Evidence: proof/asr-trusted-manifest-resolver-2026-09-13. The full tree at
56d9d4c remains historical: 2,796 passed, one failed, three skipped, plus 13
passing subtests. This proposal supplies no replacement package or installed
receipt and does not close the historical AT6 gap.
