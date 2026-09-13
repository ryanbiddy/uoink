# Independent review of the VAD metadata mapping and fixed factory

2026-09-13. Astra source and safe-JSON review found no remaining actionable mismatch in the scoped mapping or inert factory proposal. This supports retaining the proposal for the next gated design step. It does not approve a model, converter, runtime import, installation or release.

The review binds these files under `_scratch/vad-selected-metadata-map01`:

| File | SHA-256 |
| --- | --- |
| fixed-factory.proposal.txt | `69136c1f7d5cd7bf283e3634dff730c9fd951a314a80b0fa134208f3d1c1820b` |
| manifest.proposal02.json | `7198c7f63558feaac2f80814e61e77d91fd45316615b6aa6cad4d498742bed37` |
| mapping.json | `b6ef4d932556a24e46661e5600e50b386f3243a3aeeb19fa0dad592e439fd5ca` |
| supplement01.json | `aebde1776b44adda8c52e4cdc7d50204ef31ff20f231c842d746eb745d872999` |
| EVIDENCE-REPORT.md | `a836f6ab24246e10b263ece7296763bfd4b5dfa50b5f0f6a88161d51b7761a82` |
| tensor-table02.md | `884277d8eeaf16f900c45e32fb5a347512bda70caa72698e3c29bfc38d3cccbb` |

The sole model-derived input inspected was the existing 190,182-byte JSON receipt, SHA-256 `60b0078f3367bf80b8ed526d681850c47b0caae09f4fbd8da3de0883f927247d`. Its strict artifact outcome remains cycle refusal, reader exit 2. The selected closure remains partial and untrusted.

Independent PowerShell checks against that JSON reconciled every one of the 54 distinct state keys, reducer and persistent-operand records, six argument associations, hooks, shape/stride/offset declarations, advertised member records and manifest schema references. They also compared 178 retained configuration/state-metadata nodes to the original receipt. Arithmetic independently confirmed row-major strides and complete, nonoverlapping ranges in all 23 declared storage groups. Storage 16 has 32 views covering 1,380,352 elements. The distinct total is 1,472,999 elements and 5,891,996 advertised bytes. These reporting checks exited 0 with no mismatches; they did not inspect storage bytes or establish tensor values.

The source review covered the fixed PyanNet constructor/build path, SincNet and filterbank parameter/buffer declarations, Specifications and enum mapping, Model assignment/activation, Torch LSTM shape/name rules, and the VAD/Inference/WhisperX instance-injection route. All 12 relevant original source/lock bindings and three additional source-copy hashes matched. The proposed schema agrees with 52 parameter entries and two persistent buffers. The exact built-in string-key check precedes set comparison. Table02 clearly labels repeated whole-storage lengths and supplies per-view offsets and products; the original table and aggregate shared-view observations remain unchanged.

Recorded four-layer, bidirectional, 128-unit configuration and dropout 0.5 remain distinct from current-source defaults. Explicit `bias=True`, `proj_size=0`, the two absent Specifications fields mapped to `None`, omitted legacy BUILD metadata, CPU/F32 policy and inference settings are correctly labeled proposed bridge or caller choices. The constructor, `build()` once, strict load and injected model instance have no source-visible need for checkpoint-selected imports or a pretrained-loader fallback. Runtime execution could still reveal compatibility defects.

The proposal retains the required open gates: authenticated model provenance and redistribution rights; serialization protocol and byte order; an approved conversion or authoritative plain export; real artifact bytes/hash and trust anchor; native format/header/allocation checks; acceptance of the bridge and storage-sharing change; a qualified import/dependency stack; numerical, end-to-end and installed receipts. Four-byte declarations, a CUDA location string and present-day FloatStorage source do not resolve original byte order or encoding. Staged Torch 2.8 source does not qualify the separate candidate02 Torch 2.13 reference. Empty hook tags and omitted metadata are symbolic observations, not evaluated legacy objects.

No checkpoint, storage member, wheel or runtime binary was read in this review. No model module, factory, mapper or converter was executed; no tensor was constructed. No product tests or acceptance outcomes changed. No additional blocker beyond the documented gates was identified.
