# Python 3.13 package reproduction: independent verdict

The reviewed source and retained receipts support **successful package-byte reproduction**. B2 remains uninstalled; this does not qualify native dependencies, model loading, security closure or release readiness. This reviewer read source and documentary receipts only, without reopening the wheels or runtime binaries or rerunning any build.

| Recorded action | Outcome |
| --- | --- |
| Private runtime copy | Copy and outer exits 0; 33 pinned files plus the private no-site configuration, 34 files verified. The copy action launched no interpreter. |
| Python 3.13 reproduction | Child, launcher and outer exits 0; Python 3.13.15 with isolated/no-site/no-bytecode flags and exactly two private stdlib paths. |
| Package verification | All 16 output members and RECORD checked; opaque asset and license unchanged; complete output byte-equal to the first Python 3.14 build. |

Both builds recorded the same 1,387,859-byte wheel, SHA256 `d64027be41a352117199ecedfa1e9eed48d323140aa4e2c77065111f288b7883`, under different ambient epochs (`1` and `2000000000`). The child compares full byte strings after independently verifying the first output's hash and size. The unchanged builder and four recipes bind the transformation. The guard records no preloaded/postloaded heavy modules or violations and confirms its finder remained installed; the outer launcher rechecks preparation inputs and runtime files after the child.

The source enforces the reviewed preparation manifest, fresh destinations, exact runtime membership, private executable/search paths and bounded input identities before wheel processing. Wheel members, including the bundled model asset, are handled as package bytes. No package/model module, tokenizer, tensor loader or inference engine is called. These local checks assume quiescent paths and do not provide an OS sandbox or fresh publisher provenance.

Historical outcomes remain intact. The first text-preparer attempt exited 1 with a parsing error before its body ran; the documented quoting repair's second attempt exited 0. The 28-payload preparation verdict accurately remains a preparation-time snapshot. Actual copy/build receipts provide the later outcomes; no new synthetic test count is claimed.

This proof preserves the original preparation seal `0b1cb98b296f34965d8bcebe8a67755bb5315df1a3663b479e282da630346f4c`, all 28 payloads, actual raw receipts and provenance, and the root decision. It references the first-build 132-payload manifest `a553c5264f19c08dd86d98fe56db4d9f19cee5bf471a8c1a79bf45f6c0cff9eb` without copying its wheel or repeating its checks. Copy/hash counts are in verification.json; source and destination bindings are in copy-bindings.json.
