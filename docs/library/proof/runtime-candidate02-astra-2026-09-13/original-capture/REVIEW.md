# Candidate02 metadata closure, 2026-09-13

The missing public dependency metadata is collected. The reference graph still
fails. This result is sufficient to start the bounded WhisperX compatibility
proposal; it does not authorize a dependency installation or model execution.

The collector made nine HTTPS requests: four PyPI JSON responses and five exact
wheel METADATA responses. All returned HTTP 200; there were zero retrieval
failures. Each new METADATA payload matches its published metadata SHA256.
Only four previously uncaptured package names were queried, below the ten-name
limit. No wheel, source archive, binary, model or media file was downloaded.

| Newly selected dependency | Exact proposed version | Why it is included |
|---|---|---|
| hf-xet | 1.6.0 | Hub 1.31 requires >=1.5.2,<2 on Windows AMD64. |
| typer | 0.27.2 | Transformers 5.17 requires typer. |
| annotated-doc | 0.0.5 | Typer requires >=0.0.2. |
| shellingham | 1.5.4 | Typer requires >=1.3.0. |

Tokenizers 0.23.2's existing published Windows ABI3 wheel record was reused;
only its missing exact METADATA was fetched. New versions were selected as the
highest stable, non-yanked compatible wheel satisfying their incoming
requirements. These are proposed pins, not installed packages or advisory
clearance. Existing unrelated pins and requested extras were retained.

The committed checker ran once, offline, with socket and subprocess refusal.
Its actual exit was 1: **FAIL, 144 selections, 282 active edges, zero missing
targets, five conflicts, two wheel failures, one incomplete-evidence item and
zero manifest errors.** Source SHA256:
706d864e622102d5ee4435c3de8c150620b69b1070926f1f63cd780461e66c29.

The five conflicts all belong to unchanged WhisperX 3.8.6: Hub <1, Torch and
TorchAudio ~=2.8.0, torchvision ~=0.23.0, and TorchCodec >=0.6,<0.8. No proposed
derivative METADATA was substituted. antlr4-python3-runtime 4.9.3 and
proxy-tools 0.1.0 retain the two known source-only wheel failures. The current
NLTK pin remains 3.10.3+uoink.pathsec1; its accepted local wheel is absent from
PyPI, so this public-wheel checker reports incomplete evidence. It was not
silently replaced with upstream 3.10.3. Its separate accepted local-wheel proof
remains applicable to that artifact, without turning this graph into a pass.

Raw results and the actual exit are in graph01/result.json and
graph01/execution.json. graph01/stdout.txt and stderr.txt preserve the original
process outputs. retrievals.json retains each URL, UTC start/end time, status,
byte count and hash; responses/ preserves exact response bytes. The separate
evidence/ directory combines byte-identical retained payloads with the nine new
public text payloads and has its own manifest. selection-diff.json records seven
reference-version changes, four additions, no removed pins, and preserved extras.

All 304 original manifest entries were verified before copying and again after
collection, with zero differences. The production lock and validator were read
only. No accepted test, production dependency, source file, installed artifact,
website or marketing state changed. No product/model test count is claimed.

Next source work is specific: review and patch WhisperX's five constraints with
the actual changed API call sites, the unsafe default VAD loader, incomplete
cache consent and tokenizer/download fallback paths. Preserve current evidence
while preparing an exact derivative, frozen-test proposal and isolated
qualification protocol for Ryan. Refresh advisory coverage before considering
the selected runtime for release; this task performed no new vulnerability scan.
