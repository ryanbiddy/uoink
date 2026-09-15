# Lifecycle and completion metadata qualified with inert ports

Both copies pass59 cases and29 nested subtests, with zero failures or skips.
Author577e68 and independent8fd760 return outer/native0. Root993295 verifies
identical complete case objects and five child hashes, all ten guards, unchanged
nine inputs/three controls and exact17-file outputs per run. All46 historical
lifecycle cases remain in their original order and pass alongside the13 new
metadata cases. Neither observation was repeated for documentation.

Independent passive checks5181e9 and6b354b verify each run; pair checka39b40
agrees with the root comparison. Verdictbfefbbe8 and the original reviewer
parser failures/corrections are preserved. Those were passive checker errors;
no subject failure or rerun occurred.

Lifecycle source22b66293 adds immutable completion metadata after natural EOF.
The caller must obtain it inside the live session before stream close. A single
serial operation covers retrieval and publication. Retrieval happens outside
the lifecycle lock; the trusted controller's exact-object registry lookup and
final session/permit/worker/cursor checks happen under it. Cancellation, closure,
substitution and revocation prevent new publication. Getter/issuance failures
preserve the original error and retain uncertain ownership.

The new tests use a fixed inert backend language independent of the request.
No English fallback is accepted. They cover empty/nonempty completion, closed
or incomplete streams, fabricated/malformed info, unavailable ports, revocation,
identity substitution, serial refusal and cleanup errors. Inline hooks select
interleavings; these are not operating-system concurrency or IPC measurements.

Source review found one new-fixture defect before execution: registry issuance
ran outside its required lock. Proposal02 adds that lock and a fixture assertion,
preserving lifecycle source and all13 case bodies. Original01, verdictaf448cd9,
the exact repair diff and passivecaca11 remain intact. The original46 helper,
case and expected-list block is copied unchanged; fixed wrappers only adapt its
names to the reviewed result recorder. No accepted assertion or fixture changed.

Root's first passive checker failed at e37b46 because it used the wrong field
name for the historical expected-list schema. The source was not executed.
Checker02 corrects that lookup and explicitly validates the schema/count;78a6da
then verifies all three complete forward/reverse deltas. Final pin checkadaef0
preceded admission46320de. Confirmation source check37bb92 preceded605c8c0;
only five launcher labels and their control pin differ between the two copies.

The guard retains twelve metadata and twenty-five registry traps, closes all
content reads before candidate compilation, and permits only five fixed child
texts. Both runs report zero denials, heavy imports, incidental output or stderr.
Source preparation PINS3ab4293c and independent PINSa1e3abec are preserved with
the exact actual tool objects and full results.

The real backend completion response, authenticated transport and controller
registry remain unimplemented. The WhisperX caller still needs migration.
No real detected-language, native cleanup, model, PCM/filter or production
qualification follows. Production remains71d3e70; current package/install,
complete-tree, security and market gates are unchanged. D1/D2 remain complete
and no artifact access was needed.
