# Astra source-accuracy addendum to Gemini correction 371ebc24

Accept the supported corrected conclusions with this addendum. The raw Gemini
report still contains three material source-account errors; it should not stand
alone as an exact trace. These are documentary corrections, not newly observed
product defects or reasons to relabel the retained qualifications.

The unchanged report is 38,567 bytes, 327 lines, SHA-256
`f17d009e5daaeb397ec655598f269fa67cc0e634e7c77ae28cf7756de00102cb`.
S-identifiers below resolve through the committed
`docs/library/proof/worker-journal-council-correction-brief-2026-09-13/CORRECTION-INPUTS.json`,
SHA-256 `f095e168acba3e4c28fb9678a326730de0eaac37cc2d7b9dc6f4666d98b9e36e`.
All 33 current text/JSON inputs match that map's byte lengths and hashes.

| Report location | Source correction |
|---|---|
| Line 191: create_suspended establishes the channel handshake. | S39 generated_adapter_flow.py:211–227 validates the adapter startup, then delegates. S40 generated_worker_flow.py:132–148 creates the suspended worker and constructs channel/handshake **objects**. The private bootstrap, challenge, ready response and read-set adoption execute later in finish_start at S40:161–178, after resume. The adapter policy exchange follows at S39:229–241. Object construction is not a completed handshake. |
| Line 192: bind_worker journals the worker under token._lock. | S32 snapshot_reservations.py:347–352 takes the token lock to validate state, retain the worker and mark the operation pending. Observation, frame construction and append_confirmed occur **outside** that state lock at353–357. The lock is reacquired at358–362 for publication checks/state changes. S33 reservation_file_port.py:55–78 supplies a separate journal lock around append/flush/readback. |
| Lines 182 and324: direct stream access is prevented/enforced by architecture and streams are not exposed. | S46 API-AND-INTEGRATION.md:39–41 states a trusted private-caller limitation: pending/revision and gate ownership must exclude another operation; arbitrary concurrent direct calls are unsupported. It does not prove technical prevention of those calls. S31 windows_reservation_port.py:301–307 returns the journal to its trusted caller. Describe the supported call discipline, not enforcement against arbitrary in-process access. No new wrapper or product rule follows. |

Three smaller wording limits also apply. At line141, call `_transition` a
module-level replay validator; it updates the supplied generation set at S32:87,
so “pure function” is too strong. Line145's generated sync callback checks that
the manager state lock is not held (S35:650–670); this is not a measurement of
physical disk latency or all thread schedules. At line217, the initial
AdmissionRefusal path calls `stack.close()` **before** raising AssetConsentRequired
when consent is absent (S37:145–150); cleanup failure can therefore take precedence.

The material Group1 ownership correction is accurate. S12
owned_generation_protocol.py:339–346 retains constructor inputs, assigns the
built product to `b._product`, then attempts registry registration. The injected
registration failure in S14 connection_cases.py:122–141 leaves
`b._factory._completed.vad is b._product`, while `b.registry._product is None`;
retained model/factory references are checked separately. Constructor and
registration faults are the stated KeyboardInterrupt instances. The first-error
and uncertain-revocation checks match S14:143–173 and S12:398–425. The two protocol
versions, fake tensor/storage description, seventeen exact names, six no-worker
fault assignments, exception classes and separate completion/reconciliation
callbacks now match the cited passages.

Literal/data checks in TEXT-AND-RECEIPT-CHECKS.json confirm the exact seventeen
report identifiers, the S51 twenty-line patch after Markdown indentation/newline
normalization, and equal ordered case objects between each pair of saved runs:

| Retained receipts | Main cases | Nested subtests |
|---|---:|---:|
| S20 / S24 | 17 passed each | None |
| S48 original failure | 63 passed / 2 failed | 27 passed / 6 failed |
| S60 / S64 corrected | 65 passed each | 33 passed each |

The report now distinguishes case, launcher and outer-tool intervals correctly.
These are saved measurements, not executions by this reviewer. Their scope stays
generated/fake services; no inference, physical journal or recovery credit is
added. Later evidence is outside this frozen correction target.

I read the complete report and the mapped source passages needed to check its
claims, not every line of all 33 source files. The report's asserted 6,422-line
display coverage remains worker-reported pending root's event review. Catalog
membership, hashes, requested ranges and completed-view metadata do not
independently establish that every line was displayed or understood. This review
performed no tests, candidate imports, native calls, model/asset/binary access,
network requests or source edits. No further Gemini loop or broader test suite is
required by these documentary corrections.
