# Literal-token tail appendix to the completed static inventory

Run04 completed the reviewed tail-reporting inventory with measured reader
exit 0 and unchanged reader SHA256
`67e9edd6c3f6845a8dd3fd21b0b471793b57db0222c56379c0dfce9fcf07c9e5`.
The root integrator also reported outer exec exit 0. This appendix preserves
the 14-payload proposal, its 17/0 synthetic result, the exact root launcher,
run04 receipt and four launch records. It does not supersede the completed
run03 inventory or its 80-payload proof.

The saved-receipt comparison completed with real process exit 0. After
removing only `started_utc`, `elapsed_seconds`, and the two newly added pickle
fields `identifier_string_tail_samples` and `string_tail_sample_limit`,
every remaining inventory fact is equal between run03 and run04. This includes
the artifact/member identities, ZIP inventory, original first-64 samples,
GLOBAL references, opcode counts, status, exit and nonexecution flags.
The comparison does not import or run either reader and can open only its
three explicitly named saved JSON receipts.

| Identity | SHA256 |
|---|---|
| Whole 17,719,103-byte artifact | `0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea` |
| 21,882-byte data.pkl member | `5f9180875a42f5279496ecddcde3939caac3b257f66037d338d3865c16a02bf4` |
| Raw baseline run03 receipt | `703df7add11e0d9bd0f50eac6e20da0e0477479ae46f749b5eacfd532cb51b5d` |
| Raw run04 receipt | `9dddabcb9237e9163b333ca316194705a6fe544ca5db0fad807f3fd9e938f64e` |
| Canonical remaining inventory facts | `9e2b7f9ae5a523cb5b8a7108d23208f3b86eec00a051147d34eafdb4daa043fb` |

The new field contains 64 matching literal-token occurrences, in opcode order
and including duplicates. The longest observed token is 42 characters; the
unchanged regex limit is 96. The following line breaks are for readability
only and imply no associations:

```text
key flags allow_objects flags_root resolver_cache key_type element_type _parent
_content _val eps weight_decay amsgrad initial_lr params lr_schedulers
T_0 T_i T_mult eta_min base_lrs last_epoch _step_count verbose
T_cur _get_lr_called_within_step _last_lr hparams_name kwargs hyper_parameters sample_rate num_channels
sincnet stride sample_rate lstm hidden_size num_layers bidirectional monolithic
dropout batch_first linear pyannote.audio versions torch architecture module
pyannote.audio.models.segmentation.PyanNet class PyanNet introspection min_num_samples min_num_frames inc_num_samples inc_num_frames
dimension specifications problem resolution duration warm_up classes permutation_invariant
```

These are literal observations, not verified dictionary keys/values,
configuration assignments, tensor descriptors or resolved classes. In
particular, `PyanNet` and the module-looking string do not establish checkpoint
architecture/configuration or authorize construction of that class. Numeric
values and nonmatching strings are not represented by this token sample;
its position and proximity cannot establish pickle object associations.
The separate fixed-loader proposal still needs reviewed evidence for those
associations. No object, tensor or model execution occurred in run04.

The original 80-payload inventory seal remains
`60e3f77ba1244e2044b29f1c67facb917b24cc769f6fb4cb08c18c2f4415ee46`.
The original 14-payload tail-proposal seal remains
`c29b54144a6669db46bf9dd966a396914447192ab2a2276187a2af8cbe90e818`.
Both were verified unchanged. The initial 31/2 synthetic failure, run01/run02
refusals and all later scoped results remain historical evidence in the
original inventory proof; this appendix changes none of their statuses.

All appendix work used saved receipts/source only, without reopening/copying
the checkpoint, modifying a reader, or performing an additional inventory.
It materializes scratch evidence only while the root's product tree runs.
No tracked source/test/docs change, model/provider execution, installation,
staging, commit or push occurred.

After documentary edits are permitted, the root can copy this complete
directory to a fresh `docs/library/proof/vad-static-metadata-tail-2026-09-13`
target. Its `.gitattributes` contains `* -text`. Verify every copied outer
payload and the nested 14-payload seal; verify the copied baseline receipt
against the existing 80-payload proof. Confirm Git text attributes are unset
and staged blob bytes match the manifest before a documentary commit. This
is a later-copy plan, not an action performed by this task.
