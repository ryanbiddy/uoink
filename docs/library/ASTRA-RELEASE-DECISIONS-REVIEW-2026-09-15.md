# Review of Ryan's final test dispositions

Ryan's September 15 decisions are recorded at `d7d8c1c`. This review admits one
Controller10 rerun and the named AT6 marker. It admits no other test edits or
runtime work.

AT6 records a missing exit status in an old receipt. A new run cannot recover
that observation. The only change is a `pytest.mark.xfail(strict=True)` decorator
on `test_as7_c21_at6_receipt_records_process_exit_status`, with Ryan's disclosed
historical-gap reason. The function body and retained receipt stay unchanged.
An unexpected pass remains a suite failure because the marker is strict. The
old complete-tree failure remains a historical failure; it is not a new pass.

Controller10's approved patch has SHA256
`f1c8950dfbe84ddbeb5838cdc518a25a2c5eaed2011802ea8dab7e1c25aa4e8a`.
It selects the existing `SessionClosed` exception for `wrong_permit` at line128
and `active` at line300. It does not broaden global `REFUSALS`, change fault
inputs or remove retention, cleanup, ordering or message checks. The original
8-pass/2-fail result and the two branches' unexecuted later assertions remain
recorded in the September 14 failure proof.

The corrected test is SHA256
`d54dc156a30d41608b349eaec6c9c56f242ff2d65db895ab828745a3e6cf830a`.
The other eight modules, qualifier and ten-case selection are unchanged.
The fresh launcher changes only five run-label literals; the brief, protocol
and source map record the single-run limit and revised test binding. PINS is
`488a1a4223e7885fe108a3bb375512306291681fcb45018c0e0e8a658940e39b`.
Root checks the actual diff and all bindings before admission.

Verdict: approve these exact changes within Ryan's authorization. Invoke the
fresh Controller10 copy once, record the full result, and freeze whether it
passes or fails. No confirmation run, native compatibility run, model loading,
runtime migration or D3/D4 follows. Production tests and packaging are separate.

Observed result: actual3ac275 returns outer/child0 with10 passed,0 failed,0
skipped and104 passing subtests. Root24cbdb verifies exact ordered cases, all
ten guards,11 child hashes, unchanged15 inputs/3 controls and23 output files.
The two formerly unreachable branches now complete their retained assertions.
Controller10 is frozen. No native or model execution occurred.
