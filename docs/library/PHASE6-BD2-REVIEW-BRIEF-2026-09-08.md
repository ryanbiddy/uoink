# BD-2 review plan and additional ownership probe

Review `00fe216`, the combined BC-3a3/3b/3c candidate, against BD and BD-0.
The integrator ran every BC-3a3 suite in both worktree and checkout: each has
155 passes and 11 unchanged omitted-ticket failures. Those failures remain
under the existing Ryan fixture ruling.

Source inspection found that both owning callers read inputs before acquiring
their publication ticket. The first two new probes in
`tests/library_work_astra/test_phase6_bd2_acceptance.py` produced one failure
and one pass (9.48 seconds; `_scratch/bd2-owning`). The capture owner overwrote
a completed newer publication. The podcast probe passed because its stale
target had already been published and appeared in the ledger history. That
control does not test a never-published input.

Add a separate podcast case with an unseen transcript A before the competing
publication B. Preserve both existing probes and their result. Run that new
case alone; do not relabel the earlier control as a failed test. Neither probe
uses live data, a model or a source fetch.

After reviewing the new result, write the BD-2 dispositions and any bounded
repair brief. Run the BD brief's remaining regression and Phase 3 suites on
the repaired candidate; S21 remains explicitly excluded under the handoff.
The prior navigation study and player observation remain retained evidence.
Speaker material and frozen-helper changes still require Ryan's ruling.
