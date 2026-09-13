# Exact two-wheel notice integration proposal

2026-09-13. Prepare a source-only patch that puts the retained upstream notice text into the Windows distribution and keeps the proxy-tools metadata conflict visible when notices are regenerated. No production file is edited, no generator/build/test is executed, and no wheel, model or installed binary is opened.

The current generator requests license-file information but writes only the metadata table and fixed FFmpeg block. Its output labels proxy_tools 0.1.0 MIT without the source-license conflict. `build.ps1` lines 436–462 generate the root index, but the subsequent staging block does not copy it. `installer/uoink.iss` has no entry for that index or a supplemental notice directory. These are the source changes proposed here.

Use `third-party-notices/` for two exact upstream files and an attribution index. Copy license bytes from `_scratch/two-wheel-license-notices01/notices/` unchanged; the directory's `.gitattributes` disables text conversion. ANTLR's complete upstream file remains 2,699 bytes / SHA-256 `b1b379fcaf3219593a4c433feb1b35c780bed23fafaae440b1ae2771a9521e3a`. Proxy-tools remains 1,436 bytes / `a428fb8a2e762af3eb0a6edbbb88e9b42ccfee80fd9b423958bcacf9b9abbfe4`, including its placeholder and malformed final sentence.

The generator will append links and a plain conflict explanation for the two exact versions, and qualify the proxy-tools table cell as metadata. The committed fallback index receives the same text. A different present version must not reuse these notices silently. The Windows staging block requires both fixed lock entries, checks exact license hashes before and after copying, and copies the index plus the two notices and attribution file. Inno installs those four files through explicit entries. Existing metadata-collection fallback behavior remains a separate limitation; this proposal does not claim the fallback is an observed inventory of a newly built candidate.

The attribution file binds the cached-wheel hashes from retained inspection JSON to versioned public source/license records. It states the MIT-metadata versus BSD-style-text conflict without choosing a legal resolution or replacing wheel metadata. The exact release treatment remains an integrator decision; carrying the missing text supplies evidence and attribution, not legal clearance.

Deliver `before/`, `after/`, a unified patch, exact copy/source bindings and a focused verification plan. These are reviewable proposals only. Leave the current installer, package receipts and all earlier notice evidence unchanged.
