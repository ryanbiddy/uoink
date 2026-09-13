# Partition exit contract

`partition_exit_contract.py` is a pure validator. It imports only standard-library
collections, math, regular expressions and XML parsing. It performs no file I/O,
pytest import, process query or product operation. The caller supplies parsed
membership, phase reports, session receipt, verifier results, outer verifier exit
and XML text to `validate_partition`. A `PartitionContractError` means incomplete
or inconsistent qualification, not a newly invented product failure.

The result counts each selected node once and retains every failed phase. A
call failure plus teardown error remains one case with status `error`, two failed
phases and two JUnit elements. Raw JUnit totals are retained separately. Actual
pytest exit, session exit and outer verifier exit must agree with the failed
phase reports. This rejects a shutdown failure after green reports. A failed
test run with complete consistent receipts remains `FAIL` and exit 1.

The contract requires complete ordered phase reports, exact unambiguous node to
JUnit identities, and the existing `--runxfail` policy. It rejects unexplained
duplicate XML elements, missing phases, abnormal exits, count disagreement and
xfail receipts. The helper follows the installed pytest JUnit shape, including
separate call/teardown failure elements and its raw suite counter adjustment for
other teardown errors. Both raw totals and normalized case counts are returned.

Parent owns runner/sealer wiring and actual inert smoke execution. This task
owns only this helper, new synthetic unit cases, this report and the guarded
launcher. The first planned label is `partition-exit-unit01`. Source snapshots,
exact commands and every execution result will remain under its launch/run
directories. No existing instrument, product source or accepted test is edited.

`partition-exit-unit01` completed with 51 passed in 0.20 s, verifier and pytest
exit 0. Review then found that the helper described a `--runxfail` contract
without requiring the flag in the actual command, and a malformed trailing
`-m` could escape as IndexError. The next draft explicitly requires `--runxfail`
and checks that `-m` has an argument. Its inert command fixture now includes the
required flag, and two new negative cases cover those boundaries. These are
instrument corrections, not product fixes; no earlier result is reclassified.
The first draft remains in `partition-exit-unit01-launch`. The authorized next
unit label is `partition-exit-unit02`.

`partition-exit-unit02` passed 53 cases in 0.17 s, verifier and pytest exit 0.
Both runs used `run_partition_exit_contract01.ps1 -Label <label>`; their
`-launch/command.json` files retain exact native commands, and their run folders
retain verifier results, logs and XML. The helper has no changes after unit02.

`partition-exit-receipt-review01` then validated existing receipts without
rerunning any test. Reader exit was 0, with all five expectations met:

- Original inert pipeline: one pass, one failure, six phase reports; still FAIL.
- Double-failure smoke: one pass and one error across two unique cases, retaining
  both failed phases and all three JUnit elements; still FAIL.
- Shutdown smoke: refused because actual pytest exit 1 disagrees with the
  session receipt's exit 0. Its passing case is not promoted to qualification.
- Archived tree08 main: all 2,727 cases and 8,180 reports accepted as recorded,
  with 2,673 passed, 51 failed and three skipped; still FAIL.
- Archived tree08 media: two passed, six reports, exit 0; still PASS.

The reader source, normalized summary and actual reader exit are retained in
`partition-exit-receipt-review01`. These are receipt-validation results, not new
product measurements. The earlier product and smoke evidence remains untouched.

Final read-only inspection of the parent's runner/sealer wiring found the two
reported issues addressed: both tested partitions pass the same contract, the
sealer recomputes and compares the complete normalized records, and raw pytest
exits are checked before complete aggregation. The observer still preserves
pytest outcomes separately. No full-tree run is authorized by this review.
