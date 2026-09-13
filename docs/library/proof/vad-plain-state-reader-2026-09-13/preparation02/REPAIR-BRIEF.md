2026-09-13. Prepare an instrument-only derivative after vpr01 failed during
parameter construction. Its UTF-16LE fixture requested a codec not loaded before
the import guard closed. All actual exits were 1; no case function ran. The
subsequent launcher JSONDecodeError is also retained. This dependency should
have been identified during preflight; it is a harness error, not a reader defect.

Root requested one explicit stdlib preload, import encodings.utf_16_le, beside
the existing utf_8_sig import before guard installation. Make that single-line
harness addition only. Keep the reader bytes, all 76 assertion bodies and case
IDs, fixture construction, exact read allowlist and all no-model boundaries
unchanged. Do not add a blanket import allowance. The earlier literal-fixture
alternative was a proposal in the failure diagnosis and is not being applied.

Preserve the original 26-payload preparation seal and the separate 22-payload
vpr01 failure seal unchanged. This directory is a fresh derivative containing
the required source/context files, exact before/after harness diff, updated
INPUTS and false admission template for unused label vpr02. Verify all original
source bytes before copying and the entire harness AST except the one added
Import node afterward. Do not execute the reader or harness during preparation.

Root must review the tiny diff, hashes and launchers before admitting another
run. This brief does not authorize execution. Synthetic profiles remain caller
claims controlled by the reviewed generated-input harness, and real purpose
remains unconditionally refused. No real artifact, package, model or runtime
operation is involved.
