# Runtime candidate02: close missing metadata

Authorization: parent assignment on 2026-09-13. Prepare only public software
metadata for the exact reference stack: Torch 2.13.0, TorchAudio 2.11.0,
torchvision 0.28.0, TorchCodec 0.16.0, Transformers 5.17.0,
Hugging Face Hub 1.31.0 and tokenizers 0.23.2. Preserve all other production
pins initially, including the accepted local NLTK version and WhisperX 3.8.6.
The unreviewed WhisperX derivative remains a proposal; do not fabricate or
substitute its METADATA to remove actual conflicts.

Fresh output: _scratch/runtime-candidate02-metadata. Refuse an existing output
root. Copy the original capture into an independently hash-checked working
evidence directory; never change the original 304-file manifest or payloads.
Use retained package JSON and exact wheel METADATA whenever present.

Fetch only missing JSON and PEP 658 METADATA text over HTTPS from pypi.org
and files.pythonhosted.org, with timeouts, size limits and host/path checks.
No wheel/sdist/binary body, build hook, dependency installation, model/media
file, checkpoint or runtime execution is allowed. Fetch tokenizers 0.23.2
METADATA, select exact non-yanked Windows/Python-compatible hf-xet and typer
versions, then follow their newly required transitive metadata. Limit new
package scope to ten; report any remainder. Preserve exact response bytes,
URLs, UTC times, status/errors and hashes, including failed requests. No
silent retry, guessed metadata or fallback to downloading archives.

Run the committed check_runtime_graph.py only through an isolated Python
interpreter with socket and subprocess audit refusal. Use a scratch selection
and scratch evidence manifest. Preserve raw report, stdout, stderr and actual
exit. Keep all genuine conflicts, missing targets, missing local-artifact
metadata and existing source-only-wheel limits visible. Do not call a failed
graph accepted or replace any production graph.

Acceptance for this task is an auditable reduction of missing public metadata,
an exact proposed pin list for newly required targets, and a truthful graph
result. This does not approve source changes, frozen-test edits, model
qualification, package installation or release. No live index, port 5179,
credentials, provider API, commits, push, website or marketing activity.
