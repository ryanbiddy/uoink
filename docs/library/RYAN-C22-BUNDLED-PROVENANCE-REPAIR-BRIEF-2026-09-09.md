# C22 bundled provenance repair, 2026-09-09

The first original bundled observation at 6632f33 records failed provenance.
Python 3.11.9's embedded `_pth` omits the application directory for `-c` even
when cwd is the application. All seven required original imports are missing.
MCP import also raises `TypeError: function() argument 'code' must be code,
not str`: the receipt guard replaces the `subprocess.Popen` class with a
function, which breaks Windows asyncio's subclass. Other original-helper
scenarios are measured independently; retain the entire first observation.

Repair only the receipt tool's provenance command and Popen instrumentation.
Pass the already validated installed-app directory explicitly to the child and
add that exact directory before original imports. Keep all 142 source checks,
component containment, automatic guard/canary, owned deadline and no-descendant
policy. Do not add a checkout fallback or change the bundled `_pth` file.
Keep Popen a subclassable class and preserve ordinary constructor behavior,
declared failure injection, exact child registration and the audit guard.

Write new regressions in test_install_receipt_c22_bundled_compatibility.py.
First record the unchanged tool's result. Cover a `-c` probe whose original
modules live only in the explicitly supplied app, Popen subclass construction
and Windows asyncio imports with each declared injection. No existing test,
fixture, assertion or packaged product file may change.

Verify the new file plus the frozen final-oracle and integrator/operator files
in worker and checkout, excluding only the long original-source scenario from
that focused command. This bounded change has its original bundled runtime
observation and the later complete tree as its process integration checks.
Stage the worker's already integrated baseline, export only this incremental
diff, apply with three-way apply, and repeat the named checks in checkout.

After the repair is reviewed and committed, use fresh c22-bundled-02 against
the original staged app, then run the final kit-inclusive complete tree under
RYAN-FINAL-KIT-TREE-VERIFICATION-BRIEF-2026-09-09.md. Do not overwrite the failed
observation or call a source check installed acceptance. The browser hold
without an actual image stays unobserved. No Setup, client/model, live index,
port 5179 or external fetch. Installer rebuild is unnecessary if its 142
source bindings remain unchanged.

The complete first bundled observation is nine passed / two failed / three
unexecuted. All nine state comparisons and settings checks pass, but the
protected-state outcome also fails on blocked IPv6 capability queries from the
bundled urllib3 `_has_ipv6` import. Retain these failed counts. Do not permit an
ephemeral bind or erase those events. Recognize only that exact dependency
function/callsite, continue raising before the socket bind, and record it as a
distinct blocked capability query with an explicit nonzero count. Other bind-0
attempts remain forbidden. Add a regression for both cases. The fresh receipt
must report these deliberate refusals separately; it must not claim zero network
attempts. No new connection or port access is authorized by this accounting fix.

Original helper logs also expose a real concurrent backfill transaction defect;
follow RYAN-STARTUP-BACKFILL-TRANSACTION-REPAIR-BRIEF-2026-09-09.md independently.
The two declaration-driven capture exceptions are expected injected scenarios;
the source-watch transaction exceptions are not. A changed product needs a new
package seal before the final bundled C22 observation. Retain candidate-package-02
and its old package hash as historical evidence.
