# Static default-VAD checkpoint inventory: final interpretation

The reviewed metadata reader completed `run03` with measured reader exit 0
and unchanged source hash. The root integrator also reported outer exec exit
0. This closes the bounded static inventory scope. It does not approve the
default VAD loader, a model-stack migration, inference, conversion or release.

This outer proof was assembled only from existing source, synthetic results,
launch records and receipts. The checkpoint was not reopened or copied here.
No objects, tensors or models were loaded in the recorded inventory.

## Artifact and reader identity

The single allowlisted artifact was
`installer/staging/python/Lib/site-packages/whisperx/assets/pytorch_model.bin`.
All three actual inspection receipts record 17,719,103 bytes and whole-file
SHA256:
`0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea`.

The run03 reader SHA256 is:
`f27b91e610284e26975038ff6826f2190758b1d4c53a402db3c2d0386cc4d40d`.
Its exact launcher used the existing Python executable with `-I -S -B`.
The actual inspection required the recorded whole-file digest before
directory parsing, with no CLI/environment hash override or fallback.

The sole inspected pickle member, `archive/data.pkl`, is 21,882 bytes with
SHA256:
`5f9180875a42f5279496ecddcde3939caac3b257f66037d338d3865c16a02bf4`.
The raw receipt, reader, invocation and all hashes remain in this proof.
Matching an observed digest binds these bytes; it does not establish origin,
authorship, distribution integrity or trustworthiness.

## Archive and opcode observations

The receipt reports ZIP64 end records, 131 members, an 8,011-byte central
directory at byte offset 17,710,994, and 17,695,880 advertised uncompressed
bytes. Every listed member has stored compression method 0. The largest
advertised member is 5,521,408 bytes. Member names comprise `archive/data.pkl`,
129 names under `archive/data/` with numeric suffixes, and `archive/version`.
Those 129 names are not an established tensor count or shape description.
The two bytes in `archive/version` were not interpreted.

Only `data.pkl` received payload-size/CRC validation and opcode parsing.
Other members' CRC values are directory metadata, not separately verified
payload CRCs. Their opaque bytes participated in the whole-file hash; no
storage member was extracted or decoded into a tensor.

`pickletools` parsed 6,107 opcodes, with one declared protocol value 2 and
STOP at the exact end. The recorded execution-related opcode counts are:

| Opcode | Count |
|---|---:|
| GLOBAL | 17 |
| BINPERSID | 160 |
| REDUCE | 327 |
| BUILD | 9 |
| NEWOBJ | 9 |

These are parsed instruction names, not operations the reader executed.
Persistent IDs, reduction arguments, pickle stack semantics and object
construction were not resolved or validated. The full opcode histogram is
retained in `run03/run03.json`.

All 17 GLOBAL literals fit the 64-entry capture limit without truncation:

| Pickle byte offset | Literal reference |
|---:|---|
| 104 | `collections OrderedDict` |
| 168 | `torch._utils _rebuild_tensor_v2` |
| 219 | `torch FloatStorage` |
| 19190 | `omegaconf.listconfig ListConfig` |
| 19247 | `omegaconf.base ContainerMetadata` |
| 19318 | `typing Any` |
| 19356 | `__builtin__ list` |
| 19503 | `collections defaultdict` |
| 19533 | `__builtin__ dict` |
| 19586 | `__builtin__ long` |
| 19681 | `omegaconf.nodes AnyNode` |
| 19730 | `omegaconf.base Metadata` |
| 21019 | `torch.torch_version TorchVersion` |
| 21266 | `pyannote.audio.core.model Introspection` |
| 21489 | `pyannote.audio.core.task Specifications` |
| 21566 | `pyannote.audio.core.task Problem` |
| 21639 | `pyannote.audio.core.task Resolution` |

The reader imported none of those references and did not turn this list into
an allowlist. Their presence cannot establish a fixed model class, compatible
architecture, configuration, tensor schema, metadata meaning or safe loader.

The receipt contains 64 identifier-like string samples, reaching that sample
limit. They include tokens such as `state_dict`, `sincnet`, `lstm` and
`classifier.weight`. They were not interpreted as keys, values, verified
layers or model identity. Later strings may be absent. The suggested
last-32-token addition arrived after qualification and was not implemented;
no tail sample or complete metadata coverage is claimed.

## Instrument history and exact outcomes

| Stage | Outcome | Measured process exit |
|---|---|---:|
| static-preflight01 | 31 passed, 2 failed | 1 |
| static-preflight02 | 36 passed, 0 failed | 0 |
| run01 | Refused before pickle inventory | 2 |
| static-reporting-preflight01 | 45 passed, 0 failed | 0 |
| run02 | Refused before pickle inventory | 2 |
| static-compatibility-preflight01 | 89 passed, 0 failed | 0 |
| run03 | Bounded static inventory completed | 0 |

The root reported outer exec exit 1 for run01/run02, separately from each
launcher's measured reader exit 2. Neither refusal is a failed model run or
a passed artifact check. Later success does not relabel either refusal or
the initial 31/2 synthetic failure.

The first synthetic run found one setup defect and one reader defect.
Windows ZipFile normalized a backslash name before inspection; the repaired
setup injected the unsafe bytes into both ZIP headers. The behavior assertion
stayed unchanged. A forged short deflate length could conceal longer inflated
data; the repaired reader now requires bounded exact output, completed stream,
no compressed tail and CRC agreement. It also bounds the actual directory
entry count before ZipFile allocation. The failed source/setup, documented
repairs and exact diffs remain preserved.

Run01's refusal omitted the header values needed to distinguish an unsupported
version from a split archive. The reporting-only repair added bounded numeric
context without changing predicates. Its 45 checks passed. Run02 then recorded
needed version 0, made version 0, disk 0, stored method and flags 2056 for the
first entry. The approved compatibility exception permits that exact field
combination; it still refuses every other low version and altered required
field. All name/size/span/CRC/opcode rules remain active.

The original 45-case reporting harness is immutable historical evidence. Its
three AST checks required reporting-only equality and are superseded only in
scope for the intentional compatibility change. The new harness kept all 42
parser/reporting behavior cases unchanged, added 35 compatibility/retained-rule
cases and 10 digest cases, and added two static checks requiring exactly the
authorized gate/hash delta. This is the basis of the separate 89-case result.
No product acceptance fixture or assertion was changed.

## Retained bounds and limitations

| Reader resource or rule | Limit |
|---|---:|
| Whole allowlisted file | 256 MiB |
| Central directory, checked before ZipFile allocation | 2 MiB |
| Members, advertised and actual | 256 |
| One advertised uncompressed member | 256 MiB |
| Sum of advertised uncompressed sizes | 512 MiB |
| Member name | 256 UTF-8 bytes |
| One local/central extra field | 8 KiB |
| One member comment | 1 KiB |
| Pickle compressed and uncompressed payload | 2 MiB each |
| Pickle expansion ratio | 100 |
| Parsed opcodes | 250,000 |
| GLOBAL samples | 64, at most 160 characters each |
| Identifier samples | 64, at most 96 characters each |
| JSON receipt | 256 KiB |
| Cooperative elapsed-time budget | 30 seconds |

The reader permits stored/deflated compression only; it rejects encryption,
unsupported flags, split archives, unsafe/duplicate names, overlapping member
extents, ambiguous pickle members and trailing pickle bytes. Protocols above
5 are unsupported, with at most eight protocol declarations. ZIP64 end-record
size is bounded to 44 through 256 bytes. Standard needed versions 10 through
45 remain permitted; version 0 requires the exact stored-entry exception.

Observed path/reparse and identity checks require quiescent staging; they do
not create an atomic snapshot against a hostile concurrent writer. The time
budget is cooperative and cannot interrupt a stalled filesystem call. This
inventory does not establish complete ZIP/pickle semantics, storage CRCs,
tensor contents/shapes, provenance, native-library behavior, model quality,
safe conversion or release readiness.

The separate safe-loader proposal must specify reviewed fixed code, compatible
artifact/configuration and dependencies, a bounded data-loading or conversion
protocol, and the required isolated verification. It cannot use these literal
tokens as permission to execute checkpoint-selected classes. The runtime
security/owner decisions remain in force; no model-stack or speaker-gate
approval follows from this proof.

## Preservation and later documentary copy

`preparation-and-qualification` contains all 69 compatibility-seal payloads
and its manifest, including the original 47- and 27-payload seals and failed
or refused stages. `run03` adds the successful receipt, exact root launcher
and four launch records. Original prior seals were verified unchanged.
The outer manifest covers every payload; `.gitattributes` specifies `* -text`.

After the root's running full tree finishes and documentary changes are
permitted, the root can copy this entire outer directory byte-for-byte to
`docs/library/proof/vad-static-inventory-2026-09-13`, requiring a fresh target.
Before staging, verify every outer manifest length/hash and each nested seal,
and confirm `git check-attr text` reports `unset` for copied proof payloads.
After staging, compare Git index blob bytes against the manifest, including
the outer manifest itself against its separately reported hash. Keep the
original raw files and measured outcomes unchanged. This plan is not a copy,
staging, commit or push action; this task materialized scratch evidence only.
