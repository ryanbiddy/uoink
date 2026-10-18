# Runtime candidate02 is a complete metadata selection, still incompatible

Astra independently reproduces the agent's metadata result: 144 selected
versions, 282 active dependency edges, zero missing targets and exit one / FAIL.
Five unchanged WhisperX constraints conflict with the proposed versions. Two
existing source-only distributions lack public wheels, and the accepted local
NLTK version has no public PyPI release record. No item is suppressed.

The proposed changes are Torch 2.13.0, TorchAudio 2.11.0, torchvision 0.28.0,
TorchCodec 0.16.0, Transformers 5.17.0, Hub 1.31.0 and tokenizers 0.23.2, plus
four newly required packages. Production pins remain unchanged. This reference
selection supports the next source/API review; it is not an accepted runtime,
binary compatibility result, fresh vulnerability clearance or model result.

Nine public JSON/METADATA requests succeeded. No wheel, binary, source archive,
model or media was downloaded in that collection. The 342-payload source seal
and nine retrieval hashes are verified. Available exact METADATA bytes match
their published hashes. The two actual offline checker executions agree,
including the five conflicts, two wheel failures and local-NLTK evidence gap.

Astra initially suspected omitted root extras. Its correction preflight stopped
at the original-lock assertion before writing a selection or running a checker.
The suspicion was wrong: Lightning requests fsspec[http], MCP requests
pyjwt[crypto], and the original graph already propagates both. The unexecuted
proposal and its failed reader preflight are retained; no graph02 measurement
exists. Independent verification used the original selection unchanged.

Next, prepare the actual WhisperX source compatibility and safe-loader proposal,
refresh candidate advisory records, and present exact model/fixture changes and
an isolated qualification protocol for Ryan. The current unsafe VAD path and
cache/download boundaries are not cleared by dependency metadata. Website and
marketing remain paused.
