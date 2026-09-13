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
