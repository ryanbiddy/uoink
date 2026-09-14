# Passive result-review preparation

This helper is unexecuted. Root will supply both completed actual-tool JSON
filenames after the runs. It expects each supplied file to be the retained
final exec/poll object with an actual exit_code, not a reconstructed completion.
Initial and intermediate tool objects must also remain preserved separately.

I authored the qualification instrument. This follow-up checks recorded
results and byte bindings; it does not constitute an independent instrument
review. The independent instrument verdict is bound in SOURCE-BINDINGS.json,
and root independently reads and evaluates the complete outcomes.

check_results.ps1 takes two root-supplied actual filenames directly under
_scratch. It is restricted to the two fixed preparation/run directories and
their JSON/log/pinned-source records. It checks both actual outer exits, Python
exit receipts, all95 ordered case/subtest objects, the ten reported guards,
empty stderr/denials/heavy imports,25 child hashes,29 parent input pairs and
three control pairs. It requires the37 expected success-run files and compares
the two complete case arrays. Subtest totals are measured from receipts, not
predicted here. Initial/read failures and failed qualification remain failures.

The checker writes no files and invokes no subject. Its future exact exec tool
object must be saved immediately outside the admitted inputs, including any
failure. Receipt timing is recorded elapsed time, not a hard deadline. Reported
guard validity and source identity do not imply OS sandboxing, malicious-code
containment, Windows worker observations or model/runtime acceptance.

No completed actual is selected or assumed now; both bindings remain pending.
No admission, candidate run or result inspection occurred during preparation.
