# Generated reservation source and receipt verdict

The reviewed generated reservation unit passes its bounded source contracts.
The author run and independent copy each report **42 passed, 0 failed, 0 skipped**.
All 42 ordered case objects match, including 20 passing subtest observations
within those cases. These are two observations of the same suite, not 84 distinct
requirements. I read the source and raw receipts; I did not execute either run.

| Observation | Author | Independent |
|---|---|---|
| Actual tool | 70b48e, exit 0 | fd86f5, exit 0 |
| Test seconds | 0.015010600007371977 | 0.01539840002078563 |
| Launcher seconds | 0.3211884 | 0.3244666 |
| Tool seconds | 0.6327037 | 0.6363255 |
| Native / qualification exits | 0 / 0 | 0 / 0 |
| Raw stdout bytes / stderr bytes | 18,685 / 0 | 18,684 / 0 |
| Raw stdout SHA-256 | 3c00ef1460e16915bc3bdec28616a05d974f6dabe06591f3da66b26fb88ffbc0 | 9016f3db5510da6acdf4ae697163cb048c3d64be9869da81c43f358b784cf94c |

Both runs retain all 16 source/input bindings and three control checks, with all
10 final guard fields true. Content reads closed before cases; 12 metadata traps
and 25 baseline winreg callable traps remained installed. There were no audit or
registry denials, heavy imports, or captured test output. I independently compared
the original/copied input hashes and complete ordered raw case objects using
read-only data operations. The original 23 test method bodies are unchanged;
19 methods were added before the first execution.

The fixed 16-entry PINS digest is
`e7efffb823d3af09b22133909e2ff58f85ff4c62305c00d9106c3789356da0bf`.
The relevant implementation bindings are:

- Journal port: `708554378ab8a8e6c4477e637c999256665cbd2855b94c6fa3c2d04a19d3a224`.
- Reservation service: `e80ae881fa4af9cc7d1a3e4a06624f5b19abe4de09aec3844e8a541449335b98`.
- Durable connection: `fb2c783b05e8af1a34dcd8da00a7c43bf5234eb36827ef02b43c8493a0c8cf46`.
- Unchanged lifecycle: `a80514aac6b1e75b9b872052852fa993a23cd5273b6bed4ffb4eef7404cb69dd`.
- Tests: `f7e832ecd72341567f7049d91cee571cbd8eb2885e0d0532c0d7bd5a53d25bcd`.

The final source preserves physical-key exclusion, writes reservation/binding
before create/resume, retains uncertain ownership, and separates ordinary
completion from explicit fresh reconciliation. Pre-execution review corrected
missing/None gate admission, stale checks outside locks, ordinary quarantine
clearing, skipped worker stop after revoke errors, unpublished-worker cleanup,
already-cleared recovery, repeated exit, and semantic-token replacement. Exact
drafts and all five correction notes remain in the author proposal. None of those
reviews is a failed test measurement; the first executed label was reservation01.

No remaining actionable source issue was identified within this generated unit.
This is not native recovery or runtime acceptance. BytesIO, fake ownership and
trusted injected callbacks do not establish Windows file exclusion, filesystem
durability, actual scheduling, process-restart quiescence, or model behavior.
Poisoned/corrupt/absent journals remain held. Real gate/journal/observer services,
adapter migration, and generated Windows failure/restart observations are next.
The prior 46 lifecycle cases were not rerun here. No installed, release, website,
or marketing readiness claim follows.
