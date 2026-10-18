# Installed payload classification repair, 2026-09-09

Source inspection before Setup found a C22 instrument defect. The package's
142 source bindings describe compiler inputs. One is installer/upgrade_prep.ps1,
whose Inno entry is explicitly dontcopy. It is not an installed application
file, and isolated PrepareToInstall deliberately skips this ordinary-upgrade
script. The verifier incorrectly requires all 142 files inside the app. Do not
install an otherwise unnecessary ordinary-upgrade script to satisfy that test.
Wizard bitmaps are also compiler-only inputs, outside the 142 source bindings.

Gemini: repair only scripts/install_receipt/receipt_integrity.py and add a new
independent tests/test_install_receipt_payload_roles.py. Do not edit existing
tests, Inno, product code, manifest defaults, helper behavior or proof archives.
No Setup, original helper, model, network, credential store or live data access.
Preserve port 5179 and paid-API prohibitions. Work in your assigned worktree;
do not commit. Write a concise review report in
docs/library/GEMINI-INSTALLED-PAYLOAD-REPAIR-2026-09-09.md.

Retain the existing 142-binding count and all path/hash checks by default. New
package seals may explicitly label a row install_role="installer-only" only
for staged_path upgrade_prep.ps1 and source_path installer/upgrade_prep.ps1,
with valid source_git_blob and checkout_and_staged_sha256. Only that exact
compiler-only row may be recorded separately instead of required inside app.
Reject every other non-installed/unknown role, malformed digest/blob or path.
An unlabelled legacy row remains an installed-file requirement. No caller may
mark server.py, any other application file or an escaping path as exempt.
Report the 142 compiler bindings, actual installed files checked and the
explicit compiler-only row separately; no false claim that 142 installed files
were checked. No status is a Setup or upgrade-execution receipt.

Astra owns producing the new role from the exact hash-bound Inno dontcopy entry,
retaining all compiler inputs in the seal, adapting the outer observation's
binding checks and matching the full installed payload inventory against Inno's
actual Files destinations. P4's native module oracle remains unchanged. The
fresh full-tree observation already running at 80a4fa8 remains a separate result;
commit this repair and run a new complete tree afterward. Never relabel either.

Named worker and integrator verification: the new payload-role file and
tests/test_install_receipt_c22_integrator_oracles.py::test_binding_checks_reject_missing_or_escaping_compiler_inputs.
Include positive exact compiler-only and legacy-installed cases, omitted or
changed runtime bytes, attempts to exempt another file, traversal, unknown
roles, invalid digests/blobs and incomplete binding counts. Use the guarded
native runner from the source checkout's _scratch/integrator_verify.py, fresh
labels payload-role-w1 (worker) and payload-role-c1 (checkout). No fixture or
behavior assertion edits. A failure needs its own documented concrete repair.
