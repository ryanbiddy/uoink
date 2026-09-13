# Owned WhisperX repeat and byte-build preparation — 2026-09-13

Prepare source only. The author qualified the frozen 46-input manifest with
50 passed and no failures, errors, skips or subtests. The first outer invocation
failed before any cases because it named a nonexistent PowerShell host; both
that failure and the separately admitted successful outer02 remain untouched.

The repeat preparer copies only the exact 46 manifest inputs plus their manifest
to a fresh root-owned scratch directory, checks each original and copied hash,
and records the copied membership. It does not invoke Python or a test. The
unchanged launcher can then be reviewed and separately admitted by root.

The byte-build proposal uses the already retained private CPython 3.13.15
identity plan. The future launcher must check all 34 named runtime files,
isolation and the exact two private import paths, source and metadata identities,
and fresh output. It invokes the reviewed byte builder once, captures the actual
native exit durably before postchecks, and invokes the independent verifier only
after a successful build. Every failure retains its partial output and raw exit.

Only the exact text recipe and generated 22-member wheel are in scope. Do not
import any wheel member, resolve dependencies, call uv/pip/setuptools, install,
fetch or run a model. This wheel is not a runtime or release qualification. Its
closed runtime port, decoder, filter banks, asset authority, owner decisions and
native lifetime checks remain unresolved. Root must review the exact new
launch source and admit any later execution separately.
