# Retired-owner recovery source review — 2026-09-13

No blocking source defect found in the frozen probe, observer, recovery connection or ten proposed controls. This is a source-only verdict. No Python module, test, native function, support file, model, journal or converted output was executed or accessed.

Reviewed files are under `_scratch/windows-retired-owner-recovery-proposal01`:

| File | SHA-256 |
| --- | --- |
| generated_adapter_flow.py | 622f730bb2ae5ddc4494382e24bd1957731571ba1eda9022d9e8943b9e102c21 |
| generated_journal_setup.py | e6a0b9aab01c1ee4f8da948bd76b420c709d10b79b094026493384a2fe89d9d6 |
| durable_lifecycle.py | ef1519262dc0762c96d86582e211e8c2d9dfcbf93d8a3a03b0a6fc4dba5de352 |
| test_retired_owner_recovery.py | 1da9c5f8eefdad3ae4f2b22d8b632b242a2cb27296bbec6e6dd96c24da687f0c |
| PREQUALIFICATION-REPAIR01.md | dbd5f41a0a477c202782c49cadb679df1b12df575c676b98d3d0dd6231503d8d |

The exact probe is armed before lease/start. It raises its retained KeyboardInterrupt only after the completion witness is consumed and teardown checks succeed; the controller recognizes that same object after both contexts unwind. Other exceptions propagate. The three confirmed frames and journal gate remain retained during quarantine.

The repair at adapter lines 135–137 checks confirmation bytes, write revision and both poison flags before clear I/O. Manager and service attempts bind the same retired owner, worker, record, token and journal state. The close observer runs before handle closure while the manager attempt remains registered. Successful completion subsequently requires the actual closed handle, removed gate and RELEASED manager record. The old owner stays revoked. A late manager-publication refusal retains the blocked record without recreating an already released gate.

I read all ten test bodies and their generated fixture, traced their exception expectations to the declaring sources, and checked the manager/service/journal paths plus relevant lifecycle retirement code. The controls reach the actual manager, probe and observer with fake process, pipe and identity operations. They do not invoke the full `controller_retired_recovery_flow` or measure native interruption. Neither the planned qualifier nor the forthcoming native derivative is accepted by this review.

The data-only check 402da3 exited 0 and pinned 18 text inputs. Eleven inherited driver/observer definitions match the preserved before text after explicitly trimming terminal CR/LF only. The repair diff adds only the three prewrite checks and changes one new, unexecuted observer expectation to its declared RuntimeError. No accepted assertion was altered. Full hashes and the ten source case names are in CHECK-ACTUAL.json.

One initial source-search command failed at PowerShell parsing because it used shell brace expansion; corrected named reads completed. The no-index diff exit 1 denotes source differences. Neither event was a candidate test attempt. Runtime author confirmed these core hashes frozen before this verdict.
