# Package-06 proof transport repair

The first committed-object check at e9e69aa stopped because one sealed installed
receipt payload was absent from Git:
`proof/ryan-agent-installed-06-2026-09-11/p4/vault/Uoink/.uoink-mirror/manifest.json`.
The repository's `.gitignore` line 14, `Uoink/`, excluded that fixture directory.
The file exists locally and its bytes still match the original seal. The ZIP
builder did not run after the failed check.

Force-add this exact manifest-listed fixture file. Do not weaken the ignore rule,
edit the manifest, omit the payload from the seal or change its hash. It contains
the synthetic mirror's recorded ownership data; no database or client credential
store is added. Retain the [first check](proof/ryan-proof-transport-06-2026-09-11/first-check.json).

Then repeat verification against every committed installed-proof payload, plus
the package and full-tree proofs, before building the review kit. This is a
documented transport correction, not a product/test rerun. All original installed
results and the incomplete client gate remain unchanged. Future integrations
must check every manifest-listed Git object, including paths excluded by broad
runtime-directory ignore rules, before claiming that a seal is backed up.
