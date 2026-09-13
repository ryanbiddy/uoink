ASR trusted-manifest resolver proposal, 2026-09-13

The repaired scratch resolver passed 87 synthetic cases in 0.262197 seconds: the original 73 cases plus fourteen identity regressions. Qualification, native Python and outer launcher exits were 0. Stderr was empty, the audit recorded no denied operation, startup binding was asserted, and all eleven copied/original launch inputs stayed unchanged. This author result is in resolver-preflight02. It qualifies the bounded generated-placeholder contract; it does not approve any real model, manifest, download, package installation or native constructor.

The initial resolver-preflight01 remains a failed result: 64 passed and 9 failed in 0.160223 seconds, all three exits 1. Its exact source, harness, raw output and fixtures are retained. A separately reviewed diagnostic then observed forty explicitly named retained placeholders, with no refusals in 0.063862 seconds and all exits 0. Nine files had a cross-API ctime difference while both full same-API records remained stable. The source repair removes only Windows cross-API ctime equality, requires exact birthtime plus device/inode/mode/links/size/mtime, retains both complete path and handle identities, and compares each namespace exactly through reading and rebind. Non-Windows ctime stays strict. No tolerance or missing-birthtime fallback was added.

The original 73 assertion bodies and case names remain unchanged. The scratch stat-copy helper now preserves a birthtime only when present; the omission was reported and reviewed before its correction. A separate regression module tests missing/changed birthtime, same-API ctime changes, both namespaces between admission and rebind, stable cross-API differences, and non-Windows strictness. Its AST preservation case passed. No product source or accepted test was edited.

The API is `load_manifest(raw, approval)`, `admit_snapshot(manifest, choice, private_root, snapshot)` and `bind_for_constructor(admission)`. The first accepts only externally hash-bound, complete, explicitly accepted records for the exact six captured immutable model identities. The second checks the exact private snapshot, all required four/five assets, path ancestors, file kinds, inventory, byte limits, SHA-256 and stable metadata. The third repeats the full verification and compares both stored identities before returning a local path and `local_files_only=True`. None constructs a model or calls a downloader. Synthetic files must be under this proposal's attempt-owned labels, have the fixed prefix and stay at or below 4 KiB.

`REAL_APPROVAL` remains None. The unchanged public plans refuse, mapped false acceptance flags refuse, and a synthetic-size mapping retaining all twenty missing digests refuses even when its flags are true. The six LFS hashes are publisher metadata; the twenty ordinary Git blob identities do not supply SHA-256. These checks do not fill those gaps. All six choices remain available in the proposal's schema: tiny, base, small, medium, large and large-v3-turbo.

Real integration still requires accepted complete asset manifests, reviewed immutable acquisition, an enforced private and quiescent snapshot lifecycle, and a constructor that uses the returned local-only path. Rechecking paths cannot prevent malicious replacement after verification or create a native handle lease. Windows path spellings differing from the resolved physical form are conservatively refused. The diagnostic explains these forty observations, not every Windows/Python version. Provider/network/native-model operations were outside the qualification; no claim of an OS sandbox or model compatibility follows from the pass.

Reviewed and qualified SHA-256 values:

- Resolver: 16a5a1245f649a3eb04d077b661835503f08bef0ff8822dcb545176f0cc30833
- Harness: c9ddee48b81bbe5be8783e14380cbf68765a46349cf0d12cfe6ec726aa03d9b2
- Extra regressions: 952cb1e453cb1a75fe90210abcd436fbdf1bdb1cc3f0cff78043e61b93ac8b96
- Failed run01 raw stdout: 08fb8079df2486d2e2227bd8791722cdb92073fb9a1a02bf8c25cc3c137e00ae
- Passed run02 raw stdout: 143075d7d25d953c2182feab9221eef5ea5addc5976b791f6673679dea716d1e
- Captured six-model plan: cbd6e4c7d56b1dac1aa5f63f3e3b61a21137373d21bdd92e532fd0b5523e7850

Root and peer source/launcher reviews are retained separately with their actual scope. Independent root execution is pending at the time this author report is written; it is not included in these counts.
