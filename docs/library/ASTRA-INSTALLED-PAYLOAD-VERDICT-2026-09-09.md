# Installed payload correction: integrator verdict, 2026-09-09

Astra accepts the bounded verifier repair from Gemini `73720c08`. The worker's
35 tests passed in 6.04 seconds; Astra independently repeated 35 in 6.23 seconds
in that worktree, then applied the raw diff through three-way integration.
The same checkout suite passed 35 in 3.72 seconds. No existing test or Inno
behavior changed. The 34 new regression cases exercise missing or altered app
bytes, improper exemptions, malformed metadata, traversal and binding counts.

The verifier keeps all 142 compiler bindings. An explicit installer-only role
is valid only for upgrade_prep.ps1 with its exact installer source path and valid
Git/SHA metadata. It records that row separately and checks the remaining 141
installed files. Legacy unlabelled seals still require all 142 on disk. An app
file cannot be marked exempt. files_checked now reports actual installed files;
compiler_bindings retains the separate compiler-input count.

Astra's new seal producer derives the role from the exact Inno dontcopy entry,
retains the definition and its hash, and classifies every compiler input through
the Files and Wizard directives. Mapping the old inventory produces 32,194
installed files, eight wizard bitmaps and one setup-only script. This is a static
mapping, not a new installation result. The new build must derive its own counts.
The outer observer uses the repaired verifier before and after installed stages.
The separate installed-byte comparison covers every real Files destination.

The installer remains unchanged. Isolated PrepareToInstall deliberately skips
the ordinary upgrade script, so a same-version isolated reinstall must not be
claimed as execution of that script or a cross-version binary upgrade. Original
empty/legacy migration and process-recovery scenarios remain required.

Worker and independent records, the raw patch, original/final observer, layout
preflight, seal producer and installed-byte comparison are preserved under
proof/ryan-installed-payload-repair-2026-09-09/SHA256.json. The portable bound-CLI
launcher selects package data while retaining original CLI behavior; it receives
its own parse and invocation check. None of these checks supplies installed or
client acceptance.

The corrected complete tree at 80a4fa8 already has 2,451 passes and only the
historical AT6 exit failure, plus three skips and the existing SEC-06 xfail.
After this correction, freeze the final source, build and verify the replacement
package, and complete a new full tree before Setup. The final native run may add
the verified pinned bundled ffmpeg to PATH to exercise the formerly skipped
synthetic-video check. Record the environment difference and preserve the skip
in the first observation. POSIX and symlink-privilege limitations remain explicit.
