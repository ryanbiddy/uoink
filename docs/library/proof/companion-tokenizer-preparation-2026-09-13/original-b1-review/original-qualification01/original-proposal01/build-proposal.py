"""Generate inert source proposals from exact local input bytes; no execution."""
from pathlib import Path
import ast
import difflib
import hashlib
import json
import sys


def deny(event, args):
    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system"}:
        raise RuntimeError("text proposal forbids network and child processes")


sys.addaudithook(deny)
root = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
out = root / "_scratch/runtime-asset-guard-proposal01"
inputs = out / "inputs"
inputs.mkdir(exist_ok=True)
paths = [
    "whisper_runner.py",
    "tests/test_installer_dependency_lock.py",
    "tests/test_packaged_decoder_loader.py",
    "tests/test_podcast_background_jobs.py",
    "tests/test_podcast_watch.py",
    "tests/test_podcast_workflow_truth.py",
    "tests/test_phase6_evaluation.py",
    "docs/library/PHASE6-CONTRACT-2026-09-08.md",
    "docs/library/RELEASE-OWNER-DECISIONS-2026-09-12.md",
    "installer/staging/python/Lib/site-packages/faster_whisper/transcribe.py",
    "installer/staging/python/Lib/site-packages/faster_whisper/utils.py",
    "installer/staging/python/Lib/site-packages/huggingface_hub/_snapshot_download.py",
]
records = []
for relative in paths:
    data = (root / relative).read_bytes()
    target = inputs / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == data, "recorded input changed: " + relative
    else:
        target.write_bytes(data)
    records.append({"source": str(root / relative), "saved_file": "inputs/" + relative,
                    "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
(out / "input-bindings.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


def replace_once(text, old, new):
    assert text.count(old) == 1, old[:120]
    return text.replace(old, new, 1)


def write_proposal(before, after, relative, label):
    ast.parse(after, filename=relative)  # Parse only: no compile/import/exec.
    (out / (label + ".py.txt")).write_text(after, encoding="utf-8")
    patch = "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile="a/" + relative, tofile="b/" + relative))
    (out / (label + ".patch.txt")).write_text(patch, encoding="utf-8")


original = (inputs / "whisper_runner.py").read_text(encoding="utf-8-sig")
proposed = replace_once(original, "import inspect\n", "import inspect\nimport re\n")
start = proposed.index("def is_model_downloaded(")
end = proposed.index("def _runtime_device(", start)
helpers = (out / "runner-helpers.py.txt").read_text(encoding="utf-8")
proposed = proposed[:start] + helpers + "\n\n" + proposed[end:]
old_start = proposed.index("    model_path = _model_dir(data_root, model_size)", proposed.index("def transcribe_audio("))
old_end = proposed.index("    # whisperx exposes", old_start)
proposed = proposed[:old_start] + proposed[old_end:]
proposed = replace_once(proposed, "    try:\n        import whisperx  # type: ignore\n", "    model_path = _prepare_model_snapshot(\n        data_root, model_size, consent_given=consent_given)\n    try:\n        import whisperx  # type: ignore\n")
proposed = replace_once(proposed,
    "        model = whisperx.load_model(model_size, device=device,\n                                      compute_type=_compute_type(device),\n                                      download_root=str(model_path))",
    "        if _checked_model_snapshot(data_root, model_size, model_path) is None:\n            raise RuntimeError('Local ASR snapshot changed before model construction')\n        model = whisperx.load_model(str(model_path), device=device,\n                                      compute_type=_compute_type(device),\n                                      download_root=str(_model_cache_root(data_root, model_size)),\n                                      local_files_only=True)")
proposed = replace_once(proposed,
    "    `consent_given` must be True for first-time model downloads. The\n    flag is verified before the load_model call -- on first use the\n    model dir is empty, and we refuse without consent. The dashboard\n    consent dialog records the user's opt-in and re-issues the call.",
    "    Missing or incomplete ASR caches require explicit download consent.\n    Resolution and minimum-file checks precede model construction. The\n    execution call receives a local snapshot and local_files_only=True;\n    this does not qualify the separate VAD loader or artifact integrity.")
write_proposal(original, proposed, "whisper_runner.py", "product-A")

fw_path = "installer/staging/python/Lib/site-packages/faster_whisper/transcribe.py"
original = (inputs / fw_path).read_text(encoding="utf-8-sig")
proposed = replace_once(original,
    "        self.model = ctranslate2.models.Whisper(\n",
    "        tokenizer_file = os.path.join(model_path, 'tokenizer.json')\n        prepared_tokenizer = None\n        if tokenizer_bytes:\n            prepared_tokenizer = tokenizers.Tokenizer.from_buffer(tokenizer_bytes)\n        elif os.path.isfile(tokenizer_file):\n            prepared_tokenizer = tokenizers.Tokenizer.from_file(tokenizer_file)\n        elif local_files_only:\n            raise FileNotFoundError('Local Whisper snapshot is missing tokenizer.json')\n\n        self.model = ctranslate2.models.Whisper(\n")
proposed = replace_once(proposed,
    "        tokenizer_file = os.path.join(model_path, \"tokenizer.json\")\n        if tokenizer_bytes:\n            self.hf_tokenizer = tokenizers.Tokenizer.from_buffer(tokenizer_bytes)\n        elif os.path.isfile(tokenizer_file):\n            self.hf_tokenizer = tokenizers.Tokenizer.from_file(tokenizer_file)\n        else:\n",
    "        if prepared_tokenizer is not None:\n            self.hf_tokenizer = prepared_tokenizer\n        else:\n")
write_proposal(original, proposed, "faster_whisper/transcribe.py", "companion-B")
print(json.dumps({"input_files": len(records), "source_proposals_parsed": 2,
                  "product_functions_executed": 0, "tests_run": 0, "network_requests": 0}))
